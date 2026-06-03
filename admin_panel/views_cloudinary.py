import base64
import io
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import cloudinary.api
import cloudinary.exceptions
import cloudinary.uploader
from django.core.cache import cache
from django.db import close_old_connections
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from admin_panel.auth import is_admin_request
from api.models import APIKey, Servicio
from api.services.almacenamiento import AlmacenamientoCloudinary, UMBRAL_BYTES_MINIMO


NEAR_FULL_PERCENT = 90
NEAR_FULL_FREE_BYTES = 500 * 1024 * 1024
DEFAULT_TOTAL_BYTES = 25 * 1024 * 1024 * 1024
MAX_PARALLEL_TESTS = 4

# Transparent 1x1 PNG. We upload and delete it to prove the account can write.
HEALTHCHECK_PIXEL = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _check_admin(request):
    return is_admin_request(request)


def _cloudinary_service():
    return Servicio.objects.filter(nombre__iexact="cloudinary").first()


def _mask_api_key(key_value):
    creds = AlmacenamientoCloudinary._parse_cloudinary_url(key_value)
    raw_key = (creds or {}).get("api_key") or key_value or ""
    if len(raw_key) <= 10:
        return raw_key[:4] + "..." if raw_key else ""
    return f"{raw_key[:6]}...{raw_key[-4:]}"


def _classify_cloudinary_error(exc):
    text = str(exc or "").lower()
    if any(token in text for token in ("rate limit", "too many requests", "429", "420")):
        return "ERROR_TEMPORAL"
    if any(token in text for token in ("invalid api key", "invalid signature", "unauthorized", "authentication", "401")):
        return "INVALIDA"
    if any(token in text for token in ("quota", "storage limit", "insufficient storage", "over plan", "usage limit", "exceeded")):
        return "LLENA"
    if any(token in text for token in ("timeout", "timed out", "connection", "temporarily", "503", "502")):
        return "ERROR_TEMPORAL"
    return "ERROR_TEMPORAL"


def _normalize_usage_response(usage):
    storage = usage.get("storage") or {}
    used = int(storage.get("usage") or 0)
    total = int(storage.get("limit") or 0) or DEFAULT_TOTAL_BYTES
    free = max(total - used, 0)
    percent = round((used / total) * 100, 2) if total else 0
    return used, total, free, percent


def _status_from_usage(used, total, free, percent):
    if total and (percent >= 100 or free < UMBRAL_BYTES_MINIMO):
        return "LLENA"
    if percent >= NEAR_FULL_PERCENT or free < NEAR_FULL_FREE_BYTES:
        return "CASI_LLENA"
    return "OK"


def _run_upload_probe(creds, key_id):
    public_id = f"leadbook/_healthchecks/cloudinary_probe_{key_id}_{uuid.uuid4().hex[:8]}"
    image_stream = io.BytesIO(base64.b64decode(HEALTHCHECK_PIXEL))
    cloudinary.uploader.upload(
        image_stream,
        public_id=public_id,
        resource_type="image",
        type="upload",
        overwrite=True,
        invalidate=True,
        **creds,
    )
    cloudinary.uploader.destroy(
        public_id,
        resource_type="image",
        type="upload",
        invalidate=True,
        **creds,
    )


def _update_key_health(key, result):
    now = timezone.now()
    status_value = result.get("status") or "ERROR_TEMPORAL"
    key.cloudinary_total_bytes = result.get("total_bytes")
    key.cloudinary_used_bytes = result.get("used_bytes")
    key.cloudinary_free_bytes = result.get("free_bytes")
    key.cloudinary_usage_percent = result.get("usage_percent")
    key.cloudinary_status = status_value
    key.cloudinary_error = result.get("error")
    key.cloudinary_upload_probe_ok = result.get("upload_probe_ok")
    key.cloudinary_last_tested_at = now
    key.last_health_check = now
    key.last_health_status = status_value in ("OK", "CASI_LLENA")

    if status_value == "INVALIDA":
        key.status = "dead"
        key.error_count = (key.error_count or 0) + 1
    elif status_value == "LLENA":
        key.status = "exhausted"
    elif status_value in ("OK", "CASI_LLENA") and key.status in ("available", "active", "assigned", "in_bundle", "exhausted", "dead"):
        key.status = "available"
        key.error_count = 0
    elif status_value == "ERROR_TEMPORAL":
        key.error_count = (key.error_count or 0) + 1

    key.save(update_fields=[
        "cloudinary_total_bytes",
        "cloudinary_used_bytes",
        "cloudinary_free_bytes",
        "cloudinary_usage_percent",
        "cloudinary_status",
        "cloudinary_error",
        "cloudinary_upload_probe_ok",
        "cloudinary_last_tested_at",
        "last_health_check",
        "last_health_status",
        "status",
        "error_count",
    ])
    cache.delete(f"cld_stats_{key.id}")
    cache.delete(f"cloudinary_stats_{key.id}")


def _recommendation_for_status(status_value):
    return {
        "OK": "usable",
        "CASI_LLENA": "usable_near_limit",
        "LLENA": "skip_full",
        "INVALIDA": "fix_credentials",
        "ERROR_TEMPORAL": "retry_later",
    }.get(status_value, "not_tested")


def _serialize_key(key):
    status_value = key.cloudinary_status or "SIN_TEST"
    return {
        "id": key.id,
        "cloud_name": key.label or (AlmacenamientoCloudinary._parse_cloudinary_url(key.api_key) or {}).get("cloud_name") or "Sin nombre",
        "api_key_masked": _mask_api_key(key.api_key),
        "status": key.status,
        "activa": key.status == "available",
        "health_ok": status_value in ("OK", "CASI_LLENA"),
        "cloudinary_status": status_value,
        "used_bytes": key.cloudinary_used_bytes or 0,
        "total_bytes": key.cloudinary_total_bytes or 0,
        "free_bytes": key.cloudinary_free_bytes or 0,
        "usage_percent": key.cloudinary_usage_percent,
        "upload_probe_ok": key.cloudinary_upload_probe_ok,
        "last_tested_at": key.cloudinary_last_tested_at.isoformat() if key.cloudinary_last_tested_at else None,
        "error": key.cloudinary_error,
        "recommendation": _recommendation_for_status(status_value),
    }


def _summary_from_keys(keys):
    summary = {
        "total": len(keys),
        "ok": 0,
        "near_full": 0,
        "full": 0,
        "invalid": 0,
        "temporary_error": 0,
        "untested": 0,
    }
    for key in keys:
        status_value = key.cloudinary_status or "SIN_TEST"
        if status_value == "OK":
            summary["ok"] += 1
        elif status_value == "CASI_LLENA":
            summary["near_full"] += 1
        elif status_value == "LLENA":
            summary["full"] += 1
        elif status_value == "INVALIDA":
            summary["invalid"] += 1
        elif status_value == "ERROR_TEMPORAL":
            summary["temporary_error"] += 1
        else:
            summary["untested"] += 1
    return summary


def _test_key_by_id(key_id, include_probe=True):
    close_old_connections()
    try:
        key = APIKey.objects.select_related("servicio").get(pk=key_id, servicio__nombre__iexact="cloudinary")
        creds = AlmacenamientoCloudinary._parse_cloudinary_url(key.api_key)
        if not creds or not all(creds.get(part) for part in ("cloud_name", "api_key", "api_secret")):
            result = {
                "id": key.id,
                "cloud_name": key.label or "Sin nombre",
                "status": "INVALIDA",
                "health_ok": False,
                "used_bytes": 0,
                "total_bytes": 0,
                "free_bytes": 0,
                "usage_percent": 0,
                "upload_probe_ok": False,
                "error": "Credenciales Cloudinary incompletas o URL invalida",
                "recommendation": "fix_credentials",
            }
            _update_key_health(key, result)
            return result

        try:
            usage = cloudinary.api.usage(**creds)
            used, total, free, percent = _normalize_usage_response(usage)
            status_value = _status_from_usage(used, total, free, percent)
            upload_probe_ok = None
            probe_error = None

            if include_probe and status_value != "LLENA":
                try:
                    _run_upload_probe(creds, key.id)
                    upload_probe_ok = True
                except Exception as probe_exc:
                    upload_probe_ok = False
                    probe_status = _classify_cloudinary_error(probe_exc)
                    status_value = probe_status if probe_status in ("LLENA", "INVALIDA") else "ERROR_TEMPORAL"
                    probe_error = str(probe_exc)

            result = {
                "id": key.id,
                "cloud_name": creds.get("cloud_name") or key.label or "Sin nombre",
                "status": status_value,
                "health_ok": status_value in ("OK", "CASI_LLENA"),
                "used_bytes": used,
                "total_bytes": total,
                "free_bytes": free,
                "usage_percent": percent,
                "upload_probe_ok": upload_probe_ok,
                "error": probe_error,
                "recommendation": _recommendation_for_status(status_value),
            }
        except Exception as exc:
            status_value = _classify_cloudinary_error(exc)
            result = {
                "id": key.id,
                "cloud_name": creds.get("cloud_name") or key.label or "Sin nombre",
                "status": status_value,
                "health_ok": False,
                "used_bytes": key.cloudinary_used_bytes or 0,
                "total_bytes": key.cloudinary_total_bytes or 0,
                "free_bytes": key.cloudinary_free_bytes or 0,
                "usage_percent": key.cloudinary_usage_percent or 0,
                "upload_probe_ok": False,
                "error": str(exc),
                "recommendation": _recommendation_for_status(status_value),
            }

        _update_key_health(key, result)
        return result
    finally:
        close_old_connections()


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_cloudinary_stats(request):
    if not _check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    servicio = _cloudinary_service()
    if not servicio:
        return Response({"total_cuentas": 0, "total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "summary": {}})
    keys = list(APIKey.objects.filter(servicio=servicio).order_by("id"))
    total = sum(k.cloudinary_total_bytes or 0 for k in keys)
    used = sum(k.cloudinary_used_bytes or 0 for k in keys)
    free = max(total - used, 0) if total else sum(k.cloudinary_free_bytes or 0 for k in keys)
    return Response({
        "total_cuentas": len(keys),
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "summary": _summary_from_keys(keys),
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_cloudinary_keys(request):
    if not _check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    servicio = _cloudinary_service()
    if not servicio:
        return Response({"keys": [], "summary": _summary_from_keys([])})
    keys = list(APIKey.objects.filter(servicio=servicio).order_by("id"))
    return Response({"keys": [_serialize_key(k) for k in keys], "summary": _summary_from_keys(keys)})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_cloudinary_keys_add(request):
    if not _check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    cn = (request.data.get("cloud_name") or "").strip()
    ak = (request.data.get("api_key") or "").strip()
    asec = (request.data.get("api_secret") or "").strip()
    if not (cn and ak and asec):
        return Response({"error": "Faltan credenciales"}, status=400)
    servicio = _cloudinary_service()
    if not servicio:
        return Response({"error": "Servicio cloudinary no existe en DB"}, status=400)
    url = f"cloudinary://{ak}:{asec}@{cn}"
    key = APIKey.objects.create(servicio=servicio, api_key=url, label=cn, status="available", cloudinary_status="SIN_TEST")
    return Response({"success": True, "key": _serialize_key(key)}, status=201)


@api_view(["DELETE"])
@permission_classes([AllowAny])
def admin_cloudinary_keys_delete(request, pk):
    if not _check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    servicio = _cloudinary_service()
    if servicio:
        APIKey.objects.filter(pk=pk, servicio=servicio).delete()
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_cloudinary_keys_test(request, pk):
    if not _check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    include_probe = request.data.get("include_probe", True) is not False
    try:
        result = _test_key_by_id(pk, include_probe=include_probe)
    except APIKey.DoesNotExist:
        return Response({"error": "Cuenta Cloudinary no encontrada"}, status=404)
    return Response(result)


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_cloudinary_keys_test_all(request):
    if not _check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    servicio = _cloudinary_service()
    if not servicio:
        return Response({"summary": _summary_from_keys([]), "results": []})

    include_probe = request.data.get("include_probe", True) is not False
    key_ids = list(APIKey.objects.filter(servicio=servicio).order_by("id").values_list("id", flat=True))
    results = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_TESTS) as executor:
        futures = [executor.submit(_test_key_by_id, key_id, include_probe) for key_id in key_ids]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({
                    "id": None,
                    "cloud_name": "desconocida",
                    "status": "ERROR_TEMPORAL",
                    "health_ok": False,
                    "used_bytes": 0,
                    "total_bytes": 0,
                    "free_bytes": 0,
                    "usage_percent": 0,
                    "upload_probe_ok": False,
                    "error": str(exc),
                    "recommendation": "retry_later",
                })

    results.sort(key=lambda item: item.get("id") or 0)
    keys = list(APIKey.objects.filter(servicio=servicio).order_by("id"))
    return Response({"summary": _summary_from_keys(keys), "results": results})
