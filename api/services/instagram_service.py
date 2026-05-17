import requests
import time
import os
import mimetypes
import uuid
from io import BytesIO
from urllib.parse import urlparse
from api.tracking import track_api_call


UPLOAD_POST_BASE_URL = "https://api.upload-post.com/api"
MAX_INSTAGRAM_CAROUSEL_ITEMS = 10

def publicar_post(imagen_url: str, caption: str, access_token: str, account_id: str) -> dict:
    try:
        url_create = f"https://graph.facebook.com/v19.0/{account_id}/media"
        payload = {
            "image_url": imagen_url,
            "caption": caption,
            "access_token": access_token
        }
        res = requests.post(url_create, data=payload)
        res_data = res.json()
        
        if "id" not in res_data:
            return {"success": False, "error": str(res_data)}
            
        creation_id = res_data["id"]
        
        time.sleep(2) # Dar tiempo a IG para procesar la descarga
        
        url_publish = f"https://graph.facebook.com/v19.0/{account_id}/media_publish"
        payload_publish = {
            "creation_id": creation_id,
            "access_token": access_token
        }
        
        res_pub = requests.post(url_publish, data=payload_publish)
        pub_data = res_pub.json()
        
        if "id" not in pub_data:
            return {"success": False, "error": str(pub_data)}
            
        return {
            "success": True, 
            "post_id": pub_data["id"], 
            "permalink": f"https://instagram.com/p/{pub_data['id']}/" 
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def publicar_story(imagen_url: str, access_token: str, account_id: str) -> dict:
    try:
        url_create = f"https://graph.facebook.com/v19.0/{account_id}/media"
        payload = {
            "image_url": imagen_url,
            "media_type": "STORIES",
            "access_token": access_token
        }
        res = requests.post(url_create, data=payload)
        res_data = res.json()
        
        if "id" not in res_data:
            return {"success": False, "error": str(res_data)}
            
        creation_id = res_data["id"]
        time.sleep(2)
        
        url_publish = f"https://graph.facebook.com/v19.0/{account_id}/media_publish"
        payload_publish = {
            "creation_id": creation_id,
            "access_token": access_token
        }
        res_pub = requests.post(url_publish, data=payload_publish)
        pub_data = res_pub.json()
        
        if "id" not in pub_data:
            return {"success": False, "error": str(pub_data)}
            
        return {"success": True, "post_id": pub_data["id"], "permalink": ""}
    except Exception as e:
        return {"success": False, "error": str(e)}

def publicar_carrusel(imagenes_urls: list, caption: str, access_token: str, account_id: str) -> dict:
    try:
        url_create = f"https://graph.facebook.com/v19.0/{account_id}/media"
        children_ids = []
        
        for img in imagenes_urls:
            payload = {
                "image_url": img,
                "is_carousel_item": "true",
                "access_token": access_token
            }
            res = requests.post(url_create, data=payload)
            data = res.json()
            if "id" in data:
                children_ids.append(data["id"])
            else:
                return {"success": False, "error": f"Fallo crear item carrusel: {str(data)}"}
                
        payload_carousel = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
            "caption": caption,
            "access_token": access_token
        }
        
        time.sleep(3)
        res_carousel = requests.post(url_create, data=payload_carousel)
        carousel_data = res_carousel.json()
        
        if "id" not in carousel_data:
            return {"success": False, "error": str(carousel_data)}
            
        creation_id = carousel_data["id"]
        
        url_publish = f"https://graph.facebook.com/v19.0/{account_id}/media_publish"
        payload_publish = {
            "creation_id": creation_id,
            "access_token": access_token
        }
        time.sleep(2)
        res_pub = requests.post(url_publish, data=payload_publish)
        pub_data = res_pub.json()
        
        if "id" not in pub_data:
            return {"success": False, "error": str(pub_data)}
            
        return {"success": True, "post_id": pub_data["id"], "permalink": f"https://instagram.com/p/{pub_data['id']}/"}
    except Exception as e:
        return {"success": False, "error": f"Error publicando el carrusel: {str(e)}"}


# ─────────────────────────────────────────────────────────────────────────────
# Upload Post API — publicación multimedia (imagen, video, carrusel, PDF/doc)
# Documentación: https://api.upload-post.com
# ─────────────────────────────────────────────────────────────────────────────

def _get_upload_post_api_key(api_key=None, agente=None):
    """
    Resuelve la API key de Upload Post en orden de prioridad:
    1. api_key pasado como argumento (bundle del pool o override)
    2. Key del pool/bundle asignado al agente
    3. Key global del .env (UPLOADPOST_API_KEY)
    Retorna (api_key_str, error_str) — si hay error, api_key_str es None.
    """
    # 1. Argumento directo
    if api_key:
        return api_key, None

    # 2. Buscar via pool_manager si hay agente
    if agente is not None:
        try:
            from api.pool_manager import get_api_key
            key_from_pool = get_api_key(agente, 'uploadpost')
            if key_from_pool:
                return key_from_pool, None
        except Exception as e:
            print(f"[UploadPost] Advertencia al buscar key en pool: {e}")

    # 3. Fallback: key global del entorno
    try:
        from django.conf import settings
        global_key = (
            getattr(settings, 'UPLOADPOST_API_KEY', '')
            or os.environ.get('UPLOADPOST_API_KEY', '')
            or os.environ.get('UPLOAD_POST_API_KEY', '')
        )
    except Exception:
        global_key = (
            os.environ.get('UPLOADPOST_API_KEY', '')
            or os.environ.get('UPLOAD_POST_API_KEY', '')
        )

    if global_key:
        return global_key, None

    return None, (
        "No hay UPLOADPOST_API_KEY configurada. "
        "Configurá la variable de entorno UPLOADPOST_API_KEY o asigná un bundle al usuario."
    )


def publicar_post_upload_api(imagen_url: str, caption: str, api_key: str = None, agente=None) -> dict:
    """Publica una imagen usando Upload Post API (compatibilidad hacia atrás)"""
    return publicar_media_upload_api(
        media_type='image',
        caption=caption,
        image_url=imagen_url,
        api_key=api_key,
        agente=agente,
    )


@track_api_call(service='uploadpost')
def publicar_media_upload_api(
    media_type: str,          # 'image' | 'story' | 'carousel' | 'video' | 'document'
    caption: str,
    image_url: str = None,    # Para media_type='image'
    video_url: str = None,    # Para media_type='video'
    images: list = None,      # Para media_type='carousel' (lista de URLs)
    document_url: str = None, # Para media_type='document' (PDF) — solo LinkedIn
    platforms: list = None,   # ['instagram','facebook','youtube'] o None (todas)
    scheduled_at: str = None, # ISO 8601 string, ej: "2024-06-01T15:00:00Z"
    request_id: str = None,
    batch_id: str = None,
    api_key: str = None,
    agente=None,
) -> dict:
    """
    Publica contenido multimedia en redes sociales via Upload Post API.
    
    Tipos soportados para Instagram por Upload Post:
      - 'image'    → imagen simple de feed
      - 'story'    → historia de Instagram
      - 'carousel' → carrusel de imágenes

    Requiere que el usuario haya conectado sus redes via conexiones_init().
    """
    resolved_key, error = _get_upload_post_api_key(api_key, agente)
    if error:
        print(f"[UploadPost] Error de configuración: {error}")
        return {"success": False, "error": error}

    # Construir username del usuario en Upload Post
    username = None
    if agente is not None:
        username = f"leadbook_{agente.id}"

    # Validar que hay contenido según el tipo
    TIPOS_VALIDOS = ('image', 'story', 'video', 'carousel', 'document')
    if media_type not in TIPOS_VALIDOS:
        return {
            "success": False,
            "error": f"Tipo de media inválido: '{media_type}'. Debe ser uno de: {', '.join(TIPOS_VALIDOS)}"
        }

    if media_type == 'image' and not image_url:
        return {"success": False, "error": "Se requiere 'image_url' para publicar una imagen."}
    if media_type == 'story' and not image_url:
        return {"success": False, "error": "Se requiere 'image_url' para publicar una story."}
    if media_type == 'video' and not video_url:
        return {"success": False, "error": "Se requiere 'video_url' para publicar un video."}
    if media_type == 'carousel' and not images:
        return {"success": False, "error": "Se requiere 'images' (lista de URLs) para publicar un carrusel."}
    if media_type == 'document' and not document_url:
        return {"success": False, "error": "Se requiere 'document_url' para publicar un documento/PDF."}

    if media_type in ('video', 'document'):
        return {
            "success": False,
            "error": "Este flujo de publicación automática soporta por ahora post, story y carrusel de Instagram."
        }

    platforms = platforms or ['instagram']
    if isinstance(platforms, str):
        platforms = [platforms]

    request_id = request_id or f"leadbook-{getattr(agente, 'id', 'anon')}-{media_type}-{uuid.uuid4().hex[:12]}"
    uploadpost_media_type = 'STORIES' if media_type == 'story' else 'IMAGE'
    media_urls = [image_url] if media_type in ('image', 'story') else (images if isinstance(images, list) else [images])
    media_urls = [str(url).strip() for url in media_urls if str(url or '').strip()]
    original_media_count = len(media_urls)
    truncated_media_count = 0

    if not media_urls:
        return {"success": False, "error": "No hay URLs públicas válidas para publicar."}

    if media_type == 'carousel' and original_media_count > MAX_INSTAGRAM_CAROUSEL_ITEMS:
        media_urls = media_urls[:MAX_INSTAGRAM_CAROUSEL_ITEMS]
        truncated_media_count = original_media_count - len(media_urls)

    form_data = [
        ('user', username or ''),
        ('media_type', uploadpost_media_type),
        ('async_upload', 'true'),
        ('request_id', request_id),
    ]
    for platform in platforms:
        form_data.append(('platform[]', platform))
    if scheduled_at:
        form_data.append(('scheduled_date', scheduled_at))

    # Instagram usa title/instagram_title como caption. Stories no aceptan caption por API.
    if media_type != 'story' and caption:
        form_data.append(('title', caption))
        form_data.append(('instagram_title', caption))

    print(f"[UploadPost] Publicando {media_type} | username={username} | plataformas={platforms} | request_id={request_id}")

    try:
        files = _download_uploadpost_media_files(media_urls)
        response = requests.post(
            f'{UPLOAD_POST_BASE_URL}/upload_photos',
            headers={
                'Authorization': f'Apikey {resolved_key}',
                'Idempotency-Key': request_id,
            },
            data=form_data,
            files=files,
            timeout=90,
        )

        print(f"[UploadPost] Response status={response.status_code}")
        data = _safe_json(response)

        if response.status_code in (200, 201, 202):
            instagram_result = (data.get('results') or {}).get('instagram') if isinstance(data, dict) else None
            platform_failed = isinstance(instagram_result, dict) and instagram_result.get('success') is False
            if platform_failed:
                return {
                    "success": False,
                    "error": instagram_result.get('error') or instagram_result.get('message') or 'Instagram rechazó la publicación.',
                    "request_id": data.get('request_id') or request_id,
                    "upload_response": data,
                    "media_type": media_type,
                    "uploadpost_media_type": uploadpost_media_type,
                    "media_count": len(media_urls),
                    "original_media_count": original_media_count,
                    "truncated_media_count": truncated_media_count,
                }

            result = {
                "success": True,
                "request_id": data.get('request_id') or request_id,
                "job_id": data.get('job_id'),
                "status": data.get('status') or ('queued' if data.get('request_id') else 'completed'),
                "platforms": platforms,
                "results": data.get('results'),
                "post_url": instagram_result.get('url') if isinstance(instagram_result, dict) else None,
                "scheduled_at": scheduled_at,
                "media_type": media_type,
                "uploadpost_media_type": uploadpost_media_type,
                "media_count": len(media_urls),
                "original_media_count": original_media_count,
                "truncated_media_count": truncated_media_count,
                "upload_response": data,
            }
            if truncated_media_count:
                result["warning"] = (
                    f"Instagram permite hasta {MAX_INSTAGRAM_CAROUSEL_ITEMS} imágenes por carrusel; "
                    f"se enviaron las primeras {MAX_INSTAGRAM_CAROUSEL_ITEMS} de {original_media_count}."
                )
            return result
        else:
            error_text = _response_error_text(response, data)
            print(f"[UploadPost] Error HTTP {response.status_code}: {error_text}")
            is_limit_error = _is_uploadpost_limit_error(response.status_code, error_text)
            if is_limit_error and agente:
                _mark_uploadpost_key_exhausted(agente)
                return {
                    "success": False,
                    "error": "Llegaste al límite mensual de tu API de UploadPost."
                }

            return {
                "success": False,
                "error": f"Error de Upload Post ({response.status_code}): {error_text}"
            }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Timeout al conectar con Upload Post API. Intentá de nuevo."}
    except Exception as e:
        print(f"[UploadPost] Exception: {e}")
        return {"success": False, "error": str(e)}


def _safe_json(response):
    try:
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {"raw": parsed}
    except Exception:
        return {}


def _response_error_text(response, data=None):
    data = data if isinstance(data, dict) else {}
    if data:
        return str(data.get('message') or data.get('error') or data)[:500]
    return response.text[:500]


def _is_uploadpost_limit_error(status_code, error_text):
    text = str(error_text or '').lower()
    return status_code == 429 or 'limit' in text or 'quota' in text or 'too many' in text


def _mark_uploadpost_key_exhausted(agente):
    try:
        from api.pool_manager import get_api_key
        from api.models import APIKey
        key_str = get_api_key(agente, 'uploadpost')
        if not key_str:
            return
        key = APIKey.objects.filter(api_key=key_str).first()
        if not key:
            return
        key.status = 'exhausted'
        key.requests_this_month = key.google_monthly_limit or max(key.requests_this_month, key.google_daily_limit or 10)
        key.save(update_fields=['status', 'requests_this_month', 'updated_at'])
    except Exception as exc:
        print(f"Error marcando UploadPost key como agotada: {exc}")


def _guess_upload_filename(url, content_type, index):
    parsed_name = os.path.basename(urlparse(url).path or '')
    parsed_name = parsed_name.split('?')[0]
    if parsed_name and '.' in parsed_name:
        return parsed_name
    extension = mimetypes.guess_extension((content_type or '').split(';')[0].strip()) or '.jpg'
    if extension == '.jpe':
        extension = '.jpg'
    return f'leadbook-{index + 1}{extension}'


def _download_uploadpost_media_files(urls):
    files = []
    for index, url in enumerate(urls):
        if not url.startswith(('http://', 'https://')):
            raise ValueError('Upload Post requiere URLs públicas http/https para descargar la imagen generada.')

        response = requests.get(url, timeout=30, headers={'User-Agent': 'LeadBook/1.0'})
        response.raise_for_status()
        content_type = (response.headers.get('Content-Type') or 'image/jpeg').split(';')[0].strip()
        filename = _guess_upload_filename(url, content_type, index)
        files.append(('photos[]', (filename, BytesIO(response.content), content_type)))
    return files


def consultar_uploadpost_status(request_id=None, job_id=None, api_key=None, agente=None):
    resolved_key, error = _get_upload_post_api_key(api_key, agente)
    if error:
        return {"success": False, "error": error}
    if not request_id and not job_id:
        return {"success": False, "error": "Se requiere request_id o job_id."}

    params = {}
    if request_id:
        params['request_id'] = request_id
    if job_id:
        params['job_id'] = job_id

    try:
        response = requests.get(
            f'{UPLOAD_POST_BASE_URL}/uploadposts/status',
            headers={'Authorization': f'Apikey {resolved_key}'},
            params=params,
            timeout=20,
        )
        data = _safe_json(response)
        if response.status_code == 200:
            payload = dict(data)
            payload['success'] = True
            status_value = _extract_uploadpost_status(payload)
            if status_value:
                payload['status'] = status_value
            return payload
        return {"success": False, "error": _response_error_text(response, data), "status_code": response.status_code}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _extract_uploadpost_status(data):
    if not isinstance(data, dict):
        return None
    for value in (
        data.get('status'),
        data.get('state'),
        data.get('job_status'),
        (data.get('job') or {}).get('status') if isinstance(data.get('job'), dict) else None,
        (data.get('result') or {}).get('status') if isinstance(data.get('result'), dict) else None,
    ):
        if value:
            return str(value).lower()
    return None


def get_upload_post_accounts(agente) -> dict:
    """
    Devuelve las redes sociales conectadas del agente en Upload Post.
    Útil para validar qué plataformas están disponibles antes de publicar.
    """
    resolved_key, error = _get_upload_post_api_key(agente=agente)
    if error:
        return {"success": False, "error": error, "redes": []}

    username = f"leadbook_{agente.id}"
    try:
        profile = None
        resp = requests.get(
            f"{UPLOAD_POST_BASE_URL}/uploadposts/users/{username}",
            headers={"Authorization": f"Apikey {resolved_key}"},
            timeout=10
        )
        if resp.status_code == 200:
            profile = resp.json()

        if not profile:
            list_resp = requests.get(
                f"{UPLOAD_POST_BASE_URL}/uploadposts/users",
                headers={"Authorization": f"Apikey {resolved_key}"},
                timeout=10
            )
            if list_resp.status_code == 200:
                raw_users = list_resp.json()
                if isinstance(raw_users, dict):
                    users = raw_users.get('users') or raw_users.get('data') or raw_users.get('results') or []
                elif isinstance(raw_users, list):
                    users = raw_users
                else:
                    users = []
                profile = next((item for item in users if isinstance(item, dict) and item.get('username') == username), None)

        if not profile:
            return {"success": True, "redes": [], "conectado": False}

        perfil = profile.get('profile') if isinstance(profile, dict) and profile.get('profile') else profile
        social_accounts = perfil.get('social_accounts', {}) if isinstance(perfil, dict) else {}
        redes = []
        if isinstance(social_accounts, dict):
            for platform, data in social_accounts.items():
                if not data:
                    continue
                if isinstance(data, dict) and data.get('reauth_required') is True:
                    continue
                account_username = (
                    data.get('handle') or data.get('display_name') or data.get('username') or ''
                    if isinstance(data, dict)
                    else str(data)
                )
                redes.append({
                    "platform": platform,
                    "username": account_username,
                    "status": "connected",
                })
        if not redes and isinstance(perfil, dict) and isinstance(perfil.get('accounts'), list):
            for account in perfil.get('accounts'):
                if not isinstance(account, dict):
                    continue
                platform = account.get('platform') or account.get('provider') or account.get('type')
                if not platform:
                    continue
                redes.append({
                    "platform": platform,
                    "username": account.get('handle') or account.get('display_name') or account.get('username') or '',
                    "status": account.get('status') or 'connected',
                })
        return {"success": True, "redes": redes, "conectado": len(redes) > 0}
    except Exception as e:
        return {"success": False, "error": str(e), "redes": []}
