import requests
import time
import os
from api.tracking import track_api_call

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


@track_api_call(service='uploadpost')
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
    media_type: str,          # 'image' | 'video' | 'carousel' | 'document'
    caption: str,
    image_url: str = None,    # Para media_type='image'
    video_url: str = None,    # Para media_type='video'
    images: list = None,      # Para media_type='carousel' (lista de URLs)
    document_url: str = None, # Para media_type='document' (PDF) — solo LinkedIn
    platforms: list = None,   # ['instagram','facebook','youtube'] o None (todas)
    scheduled_at: str = None, # ISO 8601 string, ej: "2024-06-01T15:00:00Z"
    api_key: str = None,
    agente=None,
) -> dict:
    """
    Publica contenido multimedia en redes sociales via Upload Post API.
    
    Tipos soportados:
      - 'image'    → imagen simple (Instagram, Facebook)
      - 'video'    → video (Instagram, Facebook, YouTube)
      - 'carousel' → carrusel de imágenes (Instagram, Facebook)
      - 'document' → PDF o documento (LinkedIn, Facebook)
    
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
    TIPOS_VALIDOS = ('image', 'video', 'carousel', 'document')
    if media_type not in TIPOS_VALIDOS:
        return {
            "success": False,
            "error": f"Tipo de media inválido: '{media_type}'. Debe ser uno de: {', '.join(TIPOS_VALIDOS)}"
        }

    if media_type == 'image' and not image_url:
        return {"success": False, "error": "Se requiere 'image_url' para publicar una imagen."}
    if media_type == 'video' and not video_url:
        return {"success": False, "error": "Se requiere 'video_url' para publicar un video."}
    if media_type == 'carousel' and not images:
        return {"success": False, "error": "Se requiere 'images' (lista de URLs) para publicar un carrusel."}
    if media_type == 'document' and not document_url:
        return {"success": False, "error": "Se requiere 'document_url' para publicar un documento/PDF."}

    # Construir payload
    payload = {
        "caption": caption,
        "media_type": media_type,
    }

    if username:
        payload["username"] = username
    if platforms:
        payload["platforms"] = platforms
    if scheduled_at:
        payload["scheduled_at"] = scheduled_at

    if media_type == 'image':
        payload["image_url"] = image_url
    elif media_type == 'video':
        payload["video_url"] = video_url
    elif media_type == 'carousel':
        payload["images"] = images if isinstance(images, list) else [images]
    elif media_type == 'document':
        payload["document_url"] = document_url

    print(f"[UploadPost] Publicando {media_type} | username={username} | plataformas={platforms}")

    try:
        response = requests.post(
            'https://api.upload-post.com/api/uploadposts/posts',
            headers={
                'Authorization': f'Apikey {resolved_key}',
                'Content-Type': 'application/json'
            },
            json=payload,
            timeout=30
        )

        print(f"[UploadPost] Response status={response.status_code}")

        if response.status_code in (200, 201):
            data = response.json()
            return {
                "success": True,
                "post_id": data.get('id') or data.get('post_id'),
                "status": data.get('status', 'published'),
                "platforms": data.get('platforms', platforms),
                "scheduled_at": scheduled_at,
            }
        else:
            error_text = response.text[:500]
            print(f"[UploadPost] Error HTTP {response.status_code}: {error_text}")
            
            # --- MANEJO DE LIMITES REALES ---
            is_limit_error = response.status_code == 429 or 'limit' in error_text.lower() or 'quota' in error_text.lower()
            if is_limit_error and agente:
                try:
                    from api.pool_manager import get_api_key
                    from api.models import APIKey
                    key_str = get_api_key(agente, 'uploadpost')
                    if key_str:
                        k = APIKey.objects.filter(api_key=key_str).first()
                        if k:
                            k.status = 'exhausted'
                            # Forzamos el límite al máximo para que la UI marque 100% gastado
                            k.requests_this_month = k.google_monthly_limit or 10
                            k.save()
                except Exception as e:
                    print(f"Error marcando UploadPost key como agotada: {e}")
                    
                return {
                    "success": False,
                    "error": "Llegaste al límite mensual de tu API de UploadPost."
                }
            # --------------------------------
            
            return {
                "success": False,
                "error": f"Error de Upload Post ({response.status_code}): {error_text}"
            }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Timeout al conectar con Upload Post API (>30s). Intentá de nuevo."}
    except Exception as e:
        print(f"[UploadPost] Exception: {e}")
        return {"success": False, "error": str(e)}


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
        resp = requests.get(
            "https://api.upload-post.com/api/uploadposts/users",
            headers={"Authorization": f"Apikey {resolved_key}"},
            timeout=10
        )
        if resp.status_code != 200:
            return {"success": False, "error": f"HTTP {resp.status_code}", "redes": []}

        usuarios = resp.json()
        if not isinstance(usuarios, list):
            usuarios = usuarios.get('users', usuarios.get('data', []))
        if not isinstance(usuarios, list):
            usuarios = []

        perfil = next((u for u in usuarios if u.get("username") == username), None)
        if not perfil:
            return {"success": True, "redes": [], "conectado": False}

        redes = perfil.get("accounts", [])
        return {"success": True, "redes": redes, "conectado": len(redes) > 0}
    except Exception as e:
        return {"success": False, "error": str(e), "redes": []}
