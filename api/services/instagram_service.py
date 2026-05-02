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


# ---- Upload Post API (alternativa a Graph API) ----

@track_api_call(service='uploadpost')
def publicar_post_upload_api(imagen_url: str, caption: str, api_key: str = None, agente=None) -> dict:
    """Publica en Instagram usando Upload Post API (https://api.upload-post.com)"""
    if not api_key:
        # Soporta tanto UPLOADPOST_API_KEY (convención del proyecto) como UPLOAD_POST_API_KEY (legacy)
        try:
            from django.conf import settings
            api_key = (
                getattr(settings, 'UPLOADPOST_API_KEY', '')
                or os.environ.get('UPLOADPOST_API_KEY', '')
                or os.environ.get('UPLOAD_POST_API_KEY', '')
            )
        except Exception:
            api_key = (
                os.environ.get('UPLOADPOST_API_KEY', '')
                or os.environ.get('UPLOAD_POST_API_KEY', '')
            )

    if not api_key:
        return {"success": False, "error": "No hay UPLOADPOST_API_KEY configurada"}

    try:
        response = requests.post(
            'https://api.upload-post.com/api/uploadposts/posts',
            headers={
                'Authorization': f'Apikey {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'image_url': imagen_url,
                'caption': caption,
                'post_type': 'feed'
            },
            timeout=30
        )

        if response.status_code in (200, 201):
            return {"success": True, "post_id": response.json().get('id')}
        else:
            return {"success": False, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}
