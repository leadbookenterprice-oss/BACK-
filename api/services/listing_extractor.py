import ipaddress
import json
import logging
import re
import socket
import uuid
from html import escape as html_escape
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from lxml import html


logger = logging.getLogger(__name__)


MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 4
MAX_IMAGE_URLS = 30
DEFAULT_TIMEOUT = (5, 12)
USER_AGENT = 'LeadBookExtractor/1.0 (+https://leadbook.com.ar)'
LOW_CONFIDENCE_THRESHOLD = 0.42
RETRYABLE_ACTIONS = {'blocked', 'manual_review'}


class ExtractorError(Exception):
    def __init__(self, message, *, status_code=400, warnings=None, required_action=None, extraction_status=None):
        super().__init__(message)
        self.status_code = status_code
        self.warnings = warnings or []
        self.required_action = required_action
        self.extraction_status = extraction_status


class _FetchedHtml:
    def __init__(self, content, url, headers=None):
        self.content = content
        self.url = url
        self.headers = headers or {}


def _attempt(mode, status, reason=''):
    return {'mode': mode, 'status': status, 'reason': _clean_text(reason) or ''}


def extract_listing_from_url(url, *, pais=None, idioma=None, source_hint=None, pasted_html=None, pasted_text=None, use_playwright=None, use_unlocker=None):
    safe_url = _validate_url(url)
    source = source_hint or urlparse(safe_url).netloc.lower()
    extraction_id = uuid.uuid4().hex
    warnings = []
    attempts = []

    logger.info('[EXTRACTOR] start url=%s source_hint=%s', safe_url, source_hint or '')
    if pasted_html or pasted_text:
        document = _document_from_pasted_content(pasted_html=pasted_html, pasted_text=pasted_text)
        result = _extract_from_document(
            document,
            safe_url,
            pais=pais,
            idioma=idioma,
            source=source,
            mode='manual',
            warnings=warnings,
            extraction_id=extraction_id,
        )
        result['attempts'] = [_attempt('manual', 'success' if result.get('ok') else result.get('required_action') or 'needs_input')]
        logger.info('[EXTRACTOR] manual url=%s confidence=%.2f photos=%s', safe_url, result['confidence'], len(result['media_candidates']))
        return result

    result = None
    static_error = None
    try:
        response = _fetch_html(safe_url)
    except ExtractorError as exc:
        static_error = exc
        if not _can_retry_after_error(exc):
            logger.warning('[EXTRACTOR] fail url=%s reason=%s', safe_url, str(exc))
            raise
        logger.info('[EXTRACTOR] static %s url=%s reason=%s', exc.required_action or 'failed', safe_url, str(exc))
        attempts.append(_attempt('static', exc.required_action or 'failed', str(exc)))
        result = _empty_result(
                extraction_id=extraction_id,
                source=source,
                final_url=safe_url,
                warnings=list(exc.warnings or []) + [str(exc)],
                required_action=exc.required_action or 'manual_review',
                status_value=exc.extraction_status or 'needs_input',
                mode='static',
        )
    except Exception as exc:
        logger.warning('[EXTRACTOR] fail url=%s reason=%s', safe_url, exc)
        raise ExtractorError('No se pudo descargar la URL.', status_code=502) from exc
    else:
        result = _extract_from_html_response(
            response,
            safe_url,
            pais=pais,
            idioma=idioma,
            source=source,
            mode='static',
            warnings=warnings,
            extraction_id=extraction_id,
        )
        static_status = 'success' if result.get('ok') else (result.get('required_action') or result.get('status') or 'failed')
        if static_status == 'blocked':
            logger.info('[EXTRACTOR] static blocked url=%s reason=page_content', safe_url)
        attempts.append(_attempt('static', static_status, '; '.join(result.get('warnings') or [])))

    if _should_try_playwright(result) and _playwright_enabled(use_playwright):
        logger.info('[EXTRACTOR] playwright start url=%s', safe_url)
        try:
            rendered_html, rendered_final_url = _render_html_with_playwright(safe_url)
            rendered_response = _FetchedHtml(
                rendered_html.encode('utf-8', errors='ignore') if isinstance(rendered_html, str) else rendered_html,
                rendered_final_url or safe_url,
            )
            rendered_result = _extract_from_html_response(
                rendered_response,
                safe_url,
                pais=pais,
                idioma=idioma,
                source=source,
                mode='playwright',
                warnings=[],
                extraction_id=extraction_id,
            )
            rendered_status = 'success' if rendered_result.get('ok') else (rendered_result.get('required_action') or rendered_result.get('status') or 'failed')
            attempts.append(_attempt('playwright', rendered_status, '; '.join(rendered_result.get('warnings') or [])))
            logger.info('[EXTRACTOR] playwright %s url=%s confidence=%.2f photos=%s', rendered_status, safe_url, rendered_result.get('confidence') or 0, len(rendered_result.get('media_candidates') or []))
            if _result_quality(rendered_result) > _result_quality(result):
                rendered_result['warnings'] = _dedupe_text((result.get('warnings') or []) + (rendered_result.get('warnings') or []))
                result = rendered_result
            else:
                result['warnings'] = _dedupe_text((result.get('warnings') or []) + ['Se intento render JS, pero no mejoro la extraccion.'])
        except Exception as exc:
            logger.warning('[EXTRACTOR] playwright fail url=%s reason=%s', safe_url, exc)
            attempts.append(_attempt('playwright', 'fail', str(exc)))
            result['warnings'] = _dedupe_text((result.get('warnings') or []) + ['No se pudo renderizar la pagina dinamica; podes pegar HTML/texto si falta informacion.'])
    elif _should_try_playwright(result):
        logger.info('[EXTRACTOR] playwright disabled url=%s', safe_url)
        attempts.append(_attempt('playwright', 'disabled', 'IMPORT_URL_PLAYWRIGHT_ENABLED=false'))

    if _should_try_unlocker(result) and _unlocker_requested(use_unlocker):
        logger.info('[EXTRACTOR] unlocker start url=%s', safe_url)
        try:
            unlocked_response = _fetch_html_with_unlocker(safe_url)
            unlocked_result = _extract_from_html_response(
                unlocked_response,
                safe_url,
                pais=pais,
                idioma=idioma,
                source=source,
                mode='unlocker',
                warnings=[],
                extraction_id=extraction_id,
            )
            unlocked_status = 'success' if unlocked_result.get('ok') else (unlocked_result.get('required_action') or unlocked_result.get('status') or 'failed')
            attempts.append(_attempt('unlocker', unlocked_status, '; '.join(unlocked_result.get('warnings') or [])))
            logger.info('[EXTRACTOR] unlocker %s url=%s confidence=%.2f photos=%s', unlocked_status, safe_url, unlocked_result.get('confidence') or 0, len(unlocked_result.get('media_candidates') or []))
            if _result_quality(unlocked_result) > _result_quality(result):
                unlocked_result['warnings'] = _dedupe_text((result.get('warnings') or []) + (unlocked_result.get('warnings') or []))
                result = unlocked_result
            else:
                result['warnings'] = _dedupe_text((result.get('warnings') or []) + ['El proveedor anti-bot respondio, pero no mejoro la extraccion.'])
        except Exception as exc:
            logger.warning('[EXTRACTOR] unlocker fail url=%s reason=%s', safe_url, exc)
            status_label = 'not_configured' if _is_unlocker_config_error(exc) else 'fail'
            attempts.append(_attempt('unlocker', status_label, str(exc)))
            result['warnings'] = _dedupe_text((result.get('warnings') or []) + ['No se pudo desbloquear automaticamente la pagina; podes pegar texto/HTML o cargar manualmente.'])
    elif _should_try_unlocker(result):
        logger.info('[EXTRACTOR] unlocker disabled url=%s', safe_url)
        attempts.append(_attempt('unlocker', 'disabled', 'IMPORT_URL_UNLOCKER_ENABLED=false'))

    if not result.get('ok') and result.get('required_action') in RETRYABLE_ACTIONS:
        result['required_action'] = 'manual_review'
        result['status'] = 'needs_input'
    if static_error and not result.get('ok'):
        result['warnings'] = _dedupe_text((result.get('warnings') or []) + ['La extraccion automatica no pudo completar esta pagina.'])
    result['attempts'] = attempts

    logger.info(
        '[EXTRACTOR] success url=%s source=%s mode=%s confidence=%.2f photos=%s required_action=%s',
        safe_url,
        source,
        result.get('mode'),
        result.get('confidence') or 0,
        len(result.get('media_candidates') or []),
        result.get('required_action'),
    )
    return result


def _extract_from_document(document, final_url, *, pais=None, idioma=None, source='', mode='static', warnings=None, extraction_id=''):
    warnings = list(warnings or [])
    body_text = _clean_text(' '.join(document.xpath('//body//text()[normalize-space()]'))) or ''
    required_action = _detect_required_action(body_text)

    structured_data = _extract_structured_data(document, final_url)
    meta_data = _extract_meta_data(document, final_url)
    fallback_data = _extract_semistructured_data(document, final_url)

    data = _merge_data(structured_data, meta_data, fallback_data)
    if pais and not data.get('pais'):
        data['pais'] = _clean_text(pais)
    if idioma:
        data['idioma'] = _clean_text(idioma)

    data = _normalize_data(data)
    used_structured = bool(_meaningful_fields(structured_data))
    used_fallback = not used_structured
    if used_fallback:
        warnings.append('No se encontraron datos estructurados confiables; se uso extraccion semiestructurada.')
    if not data.get('fotos'):
        warnings.append('No se detectaron fotos publicas en la URL.')

    meaningful = _meaningful_fields(data)
    confidence = _confidence_score(data, structured=used_structured)
    ok = confidence >= 0.25 and bool(meaningful)
    if required_action:
        ok = False
        warnings.append('La pagina parece requerir una accion manual antes de poder importarla.')
    if not ok:
        warnings.append('No se pudo extraer suficiente informacion de la pagina.')

    action = required_action or ('manual_review' if not ok else 'none')
    status_value = 'ready' if ok and action == 'none' else ('needs_input' if action != 'none' else ('partial' if meaningful else 'needs_input'))
    return {
        'ok': ok,
        'extraction_id': extraction_id or uuid.uuid4().hex,
        'status': status_value,
        'source': source,
        'mode': mode,
        'confidence': confidence,
        'data': data,
        'media_candidates': data.get('fotos') or [],
        'warnings': _dedupe_text(warnings),
        'required_action': action,
        'final_url': final_url,
    }


def _empty_result(*, extraction_id, source, final_url, warnings, required_action, status_value='needs_input', mode='static'):
    return {
        'ok': False,
        'extraction_id': extraction_id,
        'status': status_value,
        'source': source,
        'mode': mode,
        'confidence': 0,
        'data': {},
        'media_candidates': [],
        'warnings': _dedupe_text(warnings),
        'required_action': required_action,
        'final_url': final_url,
    }


def _extract_from_html_response(response, fallback_url, *, pais=None, idioma=None, source='', mode='static', warnings=None, extraction_id=''):
    final_url = getattr(response, 'url', None) or fallback_url
    try:
        document = html.fromstring(response.content)
    except Exception as exc:
        logger.warning('[EXTRACTOR] fail url=%s mode=%s reason=parse_error:%s', fallback_url, mode, exc)
        raise ExtractorError('No se pudo interpretar el HTML de la propiedad.', status_code=422) from exc

    return _extract_from_document(
        document,
        final_url,
        pais=pais,
        idioma=idioma,
        source=source,
        mode=mode,
        warnings=warnings,
        extraction_id=extraction_id,
    )


def _can_retry_after_error(exc):
    return getattr(exc, 'required_action', None) in RETRYABLE_ACTIONS


def _validate_url(value):
    url = str(value or '').strip()
    if not url:
        raise ExtractorError('URL requerida.', status_code=400)
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ExtractorError('URL invalida. Usa http o https.', status_code=400)
    _assert_public_host(parsed.hostname)
    return url


def _assert_public_host(hostname):
    if not hostname:
        raise ExtractorError('Host invalido.', status_code=400)
    host = hostname.strip().strip('[]')
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            ips = [ipaddress.ip_address(item[4][0]) for item in infos]
        except Exception as exc:
            raise ExtractorError('No se pudo resolver el host de la URL.', status_code=400) from exc
    for ip in ips:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ExtractorError('URL bloqueada por seguridad.', status_code=400)


def _fetch_html(url):
    session = requests.Session()
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        _validate_url(current_url)
        response = session.get(
            current_url,
            headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml'},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get('Location')
            if not location:
                raise ExtractorError('Redirect sin destino.', status_code=502)
            current_url = urljoin(current_url, location)
            continue

        if response.status_code == 401:
            raise ExtractorError(
                'La pagina requiere iniciar sesion para ver la publicacion.',
                status_code=200,
                required_action='login_required',
                extraction_status='needs_input',
            )
        if response.status_code in {403, 429}:
            raise ExtractorError(
                'La pagina bloqueo la extraccion automatica.',
                status_code=200,
                required_action='blocked',
                extraction_status='needs_input',
            )
        response.raise_for_status()
        content_type = (response.headers.get('Content-Type') or '').lower()
        if 'html' not in content_type and 'text/plain' not in content_type and content_type:
            raise ExtractorError('La URL no devolvio HTML.', status_code=415)

        content = response.raw.read(MAX_HTML_BYTES + 1, decode_content=True)
        if len(content) > MAX_HTML_BYTES:
            raise ExtractorError('HTML demasiado grande para extraer de forma segura.', status_code=413)
        response._content = content
        return response

    raise ExtractorError('Demasiados redirects al descargar la URL.', status_code=400)


def _fetch_html_with_unlocker(url):
    provider = str(getattr(settings, 'IMPORT_URL_UNLOCKER_PROVIDER', 'brightdata') or '').strip().lower()
    if provider != 'brightdata':
        raise ExtractorError('Proveedor anti-bot no soportado.', status_code=500, required_action='manual_review')

    token = str(getattr(settings, 'BRIGHTDATA_UNLOCKER_TOKEN', '') or '').strip()
    zone = str(getattr(settings, 'BRIGHTDATA_UNLOCKER_ZONE', '') or '').strip()
    if not token or not zone:
        raise ExtractorError('Proveedor anti-bot no configurado.', status_code=500, required_action='manual_review')

    timeout_ms = int(getattr(settings, 'IMPORT_URL_UNLOCKER_TIMEOUT_MS', 45000) or 45000)
    response = requests.post(
        'https://api.brightdata.com/request',
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json={
            'zone': zone,
            'url': url,
            'format': 'raw',
            'method': 'GET',
        },
        timeout=max(1, timeout_ms / 1000),
    )
    if response.status_code in {401, 403}:
        raise ExtractorError('Credenciales anti-bot invalidas o sin acceso.', status_code=502, required_action='manual_review')
    response.raise_for_status()

    payload = None
    body = response.text
    if 'json' in (response.headers.get('Content-Type') or '').lower():
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExtractorError('El proveedor anti-bot devolvio una respuesta invalida.', status_code=502, required_action='manual_review') from exc
    else:
        try:
            candidate = response.json()
            payload = candidate if isinstance(candidate, dict) else None
        except ValueError:
            payload = None

    target_status = int((payload or {}).get('status_code') or response.status_code or 0)
    if target_status == 401:
        raise ExtractorError('La pagina requiere iniciar sesion para ver la publicacion.', status_code=200, required_action='login_required')
    if target_status in {403, 429}:
        raise ExtractorError('La pagina siguio bloqueando la extraccion automatica.', status_code=200, required_action='blocked')
    if target_status >= 400:
        raise ExtractorError('El proveedor anti-bot no pudo leer la URL.', status_code=502, required_action='manual_review')

    if payload and payload.get('body') not in (None, ''):
        body = payload.get('body')
    if body in (None, ''):
        raise ExtractorError('El proveedor anti-bot no devolvio HTML util.', status_code=502, required_action='manual_review')
    if not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False)
    content = body.encode('utf-8', errors='ignore')
    if len(content) > MAX_HTML_BYTES:
        raise ExtractorError('HTML desbloqueado demasiado grande para extraer de forma segura.', status_code=413)

    return _FetchedHtml(content, url, headers=(payload or {}).get('headers') or {})


def _document_from_pasted_content(*, pasted_html=None, pasted_text=None):
    if pasted_html:
        raw = str(pasted_html)
    else:
        raw = f'<html><body><p>{html_escape(str(pasted_text or ""))}</p></body></html>'
    encoded = raw.encode('utf-8', errors='ignore')
    if len(encoded) > MAX_HTML_BYTES:
        raise ExtractorError('El contenido pegado es demasiado grande para extraer de forma segura.', status_code=413)
    try:
        return html.fromstring(encoded)
    except Exception as exc:
        raise ExtractorError('No se pudo interpretar el HTML/texto pegado.', status_code=422) from exc


def _playwright_enabled(value=None):
    if value is not None:
        return bool(value)
    return bool(getattr(settings, 'IMPORT_URL_PLAYWRIGHT_ENABLED', False))


def _unlocker_requested(value=None):
    enabled = bool(value) if value is not None else bool(getattr(settings, 'IMPORT_URL_UNLOCKER_ENABLED', False))
    if not enabled:
        return False
    provider = str(getattr(settings, 'IMPORT_URL_UNLOCKER_PROVIDER', 'brightdata') or '').strip().lower()
    if provider != 'brightdata':
        return True
    return True


def _is_unlocker_config_error(exc):
    reason = _strip_accents(str(exc or '')).lower()
    return 'no configurado' in reason or 'credenciales' in reason or 'proveedor anti-bot no soportado' in reason


def _should_try_playwright(result):
    if not result or result.get('required_action') not in (None, 'none', 'manual_review', 'blocked'):
        return False
    data = result.get('data') or {}
    return (
        (result.get('confidence') or 0) < LOW_CONFIDENCE_THRESHOLD
        or not data.get('fotos')
        or len(_meaningful_fields(data)) < 3
    )


def _should_try_unlocker(result):
    if not result or result.get('required_action') not in (None, 'none', 'manual_review', 'blocked'):
        return False
    data = result.get('data') or {}
    return (
        not result.get('ok')
        or (result.get('confidence') or 0) < LOW_CONFIDENCE_THRESHOLD
        or not data.get('fotos')
        or len(_meaningful_fields(data)) < 3
    )


def _result_quality(result):
    data = result.get('data') or {}
    return (result.get('confidence') or 0) + min(0.20, len(result.get('media_candidates') or []) * 0.01) + len(_meaningful_fields(data)) * 0.01


def _render_html_with_playwright(url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent=USER_AGENT,
                viewport={'width': 1440, 'height': 1200},
                locale='es-AR',
            )
            page.goto(url, wait_until='domcontentloaded', timeout=15000)
            try:
                page.wait_for_load_state('networkidle', timeout=5000)
            except Exception:
                pass
            final_url = page.url or url
            _validate_url(final_url)
            content = page.content()
            if len(content.encode('utf-8', errors='ignore')) > MAX_HTML_BYTES:
                raise ExtractorError('HTML renderizado demasiado grande para extraer de forma segura.', status_code=413)
            return content, final_url
        finally:
            browser.close()


def _detect_required_action(text):
    source = _strip_accents(text or '').lower()
    if not source:
        return None
    if any(token in source for token in ('captcha', 'cloudflare', 'access denied', 'acceso denegado', 'robot check', 'verifica que eres humano', 'verify you are human')):
        return 'blocked'
    if any(token in source for token in ('iniciar sesion', 'inicia sesion', 'sign in', 'log in', 'login required', 'registrate para ver', 'create an account')):
        return 'login_required'
    if any(token in source for token in ('contenido no disponible', 'publicacion no disponible', 'listing unavailable')):
        return 'manual_review'
    return None


def _extract_structured_data(document, base_url):
    items = []
    for script in document.xpath('//script[@type="application/ld+json"]/text()'):
        raw = script.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        items.extend(_flatten_jsonld(parsed))

    best = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = _jsonld_type(item)
        if not _looks_like_listing(item, item_type):
            continue
        candidate = _map_jsonld_item(item, base_url)
        if len(_meaningful_fields(candidate)) > len(_meaningful_fields(best)):
            best = candidate
    return best


def _flatten_jsonld(value):
    found = []
    if isinstance(value, list):
        for item in value:
            found.extend(_flatten_jsonld(item))
    elif isinstance(value, dict):
        found.append(value)
        graph = value.get('@graph')
        if isinstance(graph, list):
            for item in graph:
                found.extend(_flatten_jsonld(item))
    return found


def _jsonld_type(item):
    raw = item.get('@type') or item.get('type') or ''
    if isinstance(raw, list):
        return ' '.join(str(part) for part in raw).lower()
    return str(raw).lower()


def _looks_like_listing(item, item_type):
    type_tokens = ('realestate', 'residence', 'apartment', 'house', 'product', 'offer', 'place', 'accommodation')
    if any(token in item_type for token in type_tokens):
        return True
    return bool(item.get('offers') or item.get('address') or item.get('floorSize'))


def _map_jsonld_item(item, base_url):
    offers = item.get('offers')
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}

    address = item.get('address')
    if not isinstance(address, dict):
        address = {}

    data = {
        'titulo': _first_text(item, 'name', 'headline', 'title'),
        'descripcion': _first_text(item, 'description', 'disambiguatingDescription'),
        'precio': _first_text(item, 'price') or _first_text(offers, 'price', 'lowPrice'),
        'moneda': _first_text(item, 'priceCurrency') or _first_text(offers, 'priceCurrency'),
        'ciudad': _first_text(address, 'addressLocality'),
        'direccion': _first_text(address, 'streetAddress'),
        'recamaras': _number_from_any(item.get('numberOfBedrooms') or item.get('numberOfRooms')),
        'banos': _number_from_any(item.get('numberOfBathroomsTotal') or item.get('numberOfBathrooms')),
        'superficie_total': _surface_from_any(item.get('floorSize') or item.get('size')),
        'amenidades': _amenities_from_jsonld(item.get('amenityFeature')),
        'fotos': _images_from_any(item.get('image') or item.get('photo'), base_url),
    }
    if address.get('addressRegion') and not data.get('ciudad'):
        data['ciudad'] = _clean_text(address.get('addressRegion'))
    if item.get('@type'):
        data['tipo_propiedad'] = _infer_property_type(str(item.get('@type')))
    return data


def _extract_meta_data(document, base_url):
    meta = {}
    for node in document.xpath('//meta[@content]'):
        key = (node.get('property') or node.get('name') or '').strip().lower()
        content = _clean_text(node.get('content'))
        if key and content and key not in meta:
            meta[key] = content

    title = meta.get('og:title') or meta.get('twitter:title') or _first_xpath_text(document, '//title/text()')
    description = meta.get('og:description') or meta.get('description') or meta.get('twitter:description')
    price = meta.get('product:price:amount') or meta.get('og:price:amount')
    currency = meta.get('product:price:currency') or meta.get('og:price:currency')
    images = []
    for key, value in meta.items():
        if key in {'og:image', 'og:image:secure_url', 'twitter:image'} or key.startswith('og:image'):
            images.extend(_images_from_any(value, base_url))
    images.extend(_images_from_document(document, base_url))

    return {
        'titulo': title,
        'descripcion': description,
        'precio': price,
        'moneda': currency,
        'fotos': images,
    }


def _extract_semistructured_data(document, base_url):
    text = _clean_text(' '.join(document.xpath('//body//text()[normalize-space()]')))
    title = _first_xpath_text(document, '//h1/text()') or _first_xpath_text(document, '//title/text()')
    description = _first_long_paragraph(document)
    price, currency = _extract_price(text)
    surface_total = _regex_number(text, r'(\d+(?:[\.,]\d+)?)\s*(?:m2|m²|metros\s+cuadrados)')
    surface_covered = _regex_number(text, r'(?:cubierta|construida)\D{0,24}(\d+(?:[\.,]\d+)?)\s*(?:m2|m²)')
    return {
        'titulo': title,
        'descripcion': description,
        'precio': price,
        'moneda': currency,
        'operacion': _infer_operation(text),
        'tipo_propiedad': _infer_property_type(text),
        'recamaras': _regex_number(text, r'(\d+(?:[\.,]\d+)?)\s*(?:hab|habitaciones|dormitorios|recamaras|recámaras)'),
        'banos': _regex_number(text, r'(\d+(?:[\.,]\d+)?)\s*(?:baño|baños|bano|banos|bathrooms|baÃ±o|baÃ±os)'),
        'superficie_total': surface_total,
        'superficie_cubierta': surface_covered,
        'estacionamientos': _regex_number(text, r'(\d+)\s*(?:cocheras|cochera|estacionamientos|garages|garage)'),
        'amenidades': _extract_amenities(text),
        'fotos': _images_from_document(document, base_url),
    }


def _merge_data(*sources):
    merged = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key == 'fotos':
                merged[key] = _dedupe_urls((merged.get(key) or []) + (value or []))
            elif key == 'amenidades':
                merged[key] = _dedupe_text((merged.get(key) or []) + (value or []))
            elif value not in (None, '', [], {}):
                merged.setdefault(key, value)
    return merged


def _normalize_data(data):
    normalized = {
        'titulo': _clean_text(data.get('titulo')),
        'descripcion': _clean_text(data.get('descripcion')),
        'precio': _clean_price(data.get('precio')),
        'moneda': _normalize_currency(data.get('moneda'), data.get('precio')),
        'operacion': data.get('operacion') or _infer_operation(' '.join(str(data.get(k) or '') for k in ('titulo', 'descripcion'))),
        'tipo_propiedad': data.get('tipo_propiedad') or _infer_property_type(' '.join(str(data.get(k) or '') for k in ('titulo', 'descripcion'))),
        'ciudad': _clean_text(data.get('ciudad')),
        'direccion': _clean_text(data.get('direccion')),
        'recamaras': _number_from_any(data.get('recamaras')),
        'banos': _number_from_any(data.get('banos')),
        'superficie_total': _number_from_any(data.get('superficie_total')),
        'superficie_cubierta': _number_from_any(data.get('superficie_cubierta')),
        'estacionamientos': _number_from_any(data.get('estacionamientos')),
        'amenidades': _dedupe_text(data.get('amenidades') or [])[:20],
        'fotos': _rank_image_urls(_dedupe_urls(data.get('fotos') or []))[:MAX_IMAGE_URLS],
    }
    return {key: value for key, value in normalized.items() if value not in (None, '', [], {})}


def _confidence_score(data, *, structured=False):
    score = 0.4 if structured else 0.22
    weights = {
        'titulo': 0.08,
        'descripcion': 0.10,
        'precio': 0.10,
        'ciudad': 0.06,
        'direccion': 0.06,
        'recamaras': 0.05,
        'banos': 0.05,
        'superficie_total': 0.05,
        'tipo_propiedad': 0.04,
    }
    for key, weight in weights.items():
        if data.get(key) not in (None, '', [], {}):
            score += weight
    if data.get('fotos'):
        score += min(0.14, len(data['fotos']) * 0.02)
    return round(min(score, 0.95 if structured else 0.72), 2)


def _meaningful_fields(data):
    if not isinstance(data, dict):
        return []
    ignored = {'moneda'}
    return [key for key, value in data.items() if key not in ignored and value not in (None, '', [], {})]


def _first_text(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, '', [], {}):
            return _clean_text(value)
    return None


def _first_xpath_text(document, query):
    values = document.xpath(query)
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return None


def _first_long_paragraph(document):
    for value in document.xpath('//p/text()'):
        cleaned = _clean_text(value)
        if len(cleaned) >= 80:
            return cleaned[:2000]
    return None


def _clean_text(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return re.sub(r'\s+', ' ', str(value)).strip()


def _clean_price(value):
    if value in (None, ''):
        return None
    raw = str(value)
    match = re.search(r'(\d[\d\.,]*)', raw)
    return match.group(1).replace(' ', '') if match else _clean_text(raw)


def _normalize_currency(value, price_text=None):
    raw = str(value or '').strip().upper()
    if raw in {'US$', 'U$S', 'USD'}:
        return 'USD'
    if raw in {'AR$', 'ARS'}:
        return 'ARS'
    if raw in {'MX$', 'MXN'}:
        return 'MXN'
    if raw in {'COP'}:
        return 'COP'
    if raw in {'EUR', '€'}:
        return 'EUR'
    text = str(price_text or '').upper()
    if any(token in text for token in ('USD', 'US$', 'U$S')):
        return 'USD'
    if '€' in text or 'EUR' in text:
        return 'EUR'
    if '$' in text:
        return 'USD'
    return raw or None


def _number_from_any(value):
    if value in (None, ''):
        return None
    if isinstance(value, dict):
        value = value.get('value') or value.get('amount') or value.get('name')
    match = re.search(r'\d+(?:[\.,]\d+)?', str(value))
    if not match:
        return None
    number = match.group(0).replace(',', '.')
    parsed = float(number)
    return int(parsed) if parsed.is_integer() else parsed


def _surface_from_any(value):
    if isinstance(value, dict):
        return _number_from_any(value.get('value') or value.get('amount') or value.get('name'))
    return _number_from_any(value)


def _regex_number(text, pattern):
    match = re.search(pattern, text or '', flags=re.IGNORECASE)
    return _number_from_any(match.group(1)) if match else None


def _extract_price(text):
    patterns = [
        r'(USD|US\$|U\$S|ARS|MXN|COP|EUR|€|\$)\s*([\d\.,]+)',
        r'([\d\.,]+)\s*(USD|US\$|U\$S|ARS|MXN|COP|EUR|€)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text or '', flags=re.IGNORECASE)
        if match:
            first, second = match.group(1), match.group(2)
            if re.search(r'\d', first):
                return first, _normalize_currency(second)
            return second, _normalize_currency(first)
    return None, None


def _infer_operation(text):
    source = _strip_accents(text or '').lower()
    if any(token in source for token in ('alquiler', 'renta', 'rent')):
        return 'alquiler'
    if any(token in source for token in ('venta', 'sale', 'vende')):
        return 'venta'
    if 'temporario' in source or 'vacacional' in source:
        return 'temporario'
    return None


def _infer_property_type(text):
    source = _strip_accents(text or '').lower()
    candidates = [
        ('departamento', ('departamento', 'depto', 'apartment', 'apartamento')),
        ('casa', ('casa', 'house', 'chalet')),
        ('oficina', ('oficina', 'office')),
        ('local', ('local', 'retail')),
        ('terreno', ('terreno', 'lote', 'land')),
        ('ph', ('ph',)),
    ]
    for label, tokens in candidates:
        if any(token in source for token in tokens):
            return label
    return None


def _extract_amenities(text):
    source = _strip_accents(text or '').lower()
    amenity_tokens = {
        'piscina': ('piscina', 'pileta', 'pool'),
        'gimnasio': ('gimnasio', 'gym'),
        'parrilla': ('parrilla', 'asador'),
        'balcon': ('balcon', 'balcón'),
        'terraza': ('terraza',),
        'seguridad': ('seguridad', 'vigilancia'),
        'sum': ('sum', 'salon de usos multiples'),
        'jardin': ('jardin', 'jardín'),
        'cochera': ('cochera', 'garage', 'estacionamiento'),
    }
    return [label for label, tokens in amenity_tokens.items() if any(token in source for token in tokens)]


def _amenities_from_jsonld(value):
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    amenities = []
    for item in items:
        if isinstance(item, dict):
            name = item.get('name') or item.get('value')
        else:
            name = item
        cleaned = _clean_text(name)
        if cleaned:
            amenities.append(cleaned)
    return amenities


def _images_from_document(document, base_url):
    images = []
    for node in document.xpath('//img'):
        value = node.get('src') or node.get('data-src') or node.get('data-original') or node.get('data-lazy-src')
        srcset = node.get('srcset') or node.get('data-srcset')
        if srcset:
            images.extend(_images_from_srcset(srcset, base_url))
        images.extend(_images_from_any(value, base_url))
    for node in document.xpath('//source'):
        srcset = node.get('srcset') or node.get('data-srcset')
        if srcset:
            images.extend(_images_from_srcset(srcset, base_url))
    images.extend(_images_from_scripts(document, base_url))
    return _dedupe_urls(images)


def _images_from_scripts(document, base_url):
    images = []
    for node in document.xpath('//script/text()'):
        raw = str(node or '').strip()
        if not raw:
            continue
        unescaped = raw.replace('\\/', '/')
        images.extend(_image_urls_from_text(unescaped, base_url))
        if raw[:1] in {'{', '['}:
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            images.extend(_images_from_json_value(parsed, base_url))
    return _dedupe_urls(images)


def _images_from_json_value(value, base_url):
    images = []
    if isinstance(value, dict):
        for item in value.values():
            images.extend(_images_from_json_value(item, base_url))
    elif isinstance(value, list):
        for item in value:
            images.extend(_images_from_json_value(item, base_url))
    elif isinstance(value, str):
        images.extend(_image_urls_from_text(value.replace('\\/', '/'), base_url))
    return images


def _image_urls_from_text(value, base_url):
    if not value:
        return []
    pattern = r'((?:https?:)?//[^"\'<>\s\\]+?\.(?:jpe?g|png|webp|avif|heic|heif)(?:\?[^"\'<>\s\\]*)?|/[^"\'<>\s\\]+?\.(?:jpe?g|png|webp|avif|heic|heif)(?:\?[^"\'<>\s\\]*)?)'
    return _dedupe_urls(
        url
        for url in (_absolute_media_url(match, base_url) for match in re.findall(pattern, str(value), flags=re.IGNORECASE))
        if url
    )


def _images_from_srcset(srcset, base_url):
    images = []
    for candidate in str(srcset or '').split(','):
        value = candidate.strip().split(' ')[0]
        images.extend(_images_from_any(value, base_url))
    return images


def _images_from_any(value, base_url):
    images = []
    if not value:
        return images
    if isinstance(value, str):
        images.append(value)
    elif isinstance(value, dict):
        images.extend(_images_from_any(value.get('url') or value.get('contentUrl'), base_url))
    elif isinstance(value, list):
        for item in value:
            images.extend(_images_from_any(item, base_url))
    return [_absolute_media_url(item, base_url) for item in images if _absolute_media_url(item, base_url)]


def _absolute_media_url(value, base_url):
    url = _clean_text(value)
    if not url or url.lower().startswith('data:'):
        return None
    absolute = urljoin(base_url, url)
    parsed = urlparse(absolute)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return absolute


def _dedupe_urls(values):
    seen = set()
    result = []
    for value in values or []:
        cleaned = _clean_text(value)
        if not cleaned or cleaned.lower().startswith('data:'):
            continue
        key = cleaned.split('#')[0]
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _rank_image_urls(values):
    ranked = []
    for index, value in enumerate(values or []):
        ranked.append((_image_quality_score(value), -index, value))
    ranked.sort(reverse=True)
    return [value for _score, _index, value in ranked]


def _image_quality_score(value):
    raw = str(value or '').lower()
    score = 20
    if any(ext in raw for ext in ('.jpg', '.jpeg', '.png', '.webp', '.avif', '.heic', '.heif')):
        score += 8
    if any(token in raw for token in ('hero', 'gallery', 'photo', 'image', 'listing', 'property', 'upload')):
        score += 6
    if re.search(r'(?:^|[^\d])(?:1[0-9]{3}|2[0-9]{3}|3[0-9]{3})[x_\-](?:[6-9][0-9]{2}|1[0-9]{3}|2[0-9]{3})', raw):
        score += 8
    if any(token in raw for token in ('logo', 'icon', 'avatar', 'profile', 'sprite', 'favicon', 'placeholder', 'map')):
        score -= 18
    if raw.endswith('.svg'):
        score -= 20
    return score


def _dedupe_text(values):
    seen = set()
    result = []
    for value in values or []:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        key = _strip_accents(cleaned).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _strip_accents(value):
    import unicodedata
    return ''.join(ch for ch in unicodedata.normalize('NFD', str(value)) if unicodedata.category(ch) != 'Mn')
