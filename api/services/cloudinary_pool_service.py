from api.models import APIKey
import cloudinary.api
from urllib.parse import urlparse
from django.core.cache import cache
import random

class CloudinaryPoolService:
    @staticmethod
    def parse_cloudinary_url(url):
        if not url or not url.startswith('cloudinary://'):
            return None
        parsed = urlparse(url)
        return {
            'api_key': parsed.username,
            'api_secret': parsed.password,
            'cloud_name': parsed.hostname
        }

    @staticmethod
    def get_stats_for_key(key_obj):
        creds = CloudinaryPoolService.parse_cloudinary_url(key_obj.api_key)
        if not creds:
            return {'total_bytes': 0, 'used_bytes': 0, 'free_bytes': 0, 'error': 'Invalid URL'}
            
        try:
            res = cloudinary.api.usage(
                cloud_name=creds['cloud_name'],
                api_key=creds['api_key'],
                api_secret=creds['api_secret']
            )
            used = res.get('storage', {}).get('usage', 0)
            limit = res.get('storage', {}).get('limit', 0)
            return {'total_bytes': limit, 'used_bytes': used, 'free_bytes': limit - used}
        except Exception as e:
            return {'total_bytes': 0, 'used_bytes': 0, 'free_bytes': 0, 'error': str(e)}

    @staticmethod
    def get_all_keys():
        return APIKey.objects.filter(servicio='cloudinary', status='available')

    @classmethod
    def get_best_credentials(cls):
        """
        Devuelve las credenciales de la cuenta Cloudinary con más espacio libre.
        Usa caché de 1 hora para evitar colapsar la API de Cloudinary.
        Si no hay keys en el pool, devuelve None (para que el sistema use la config global).
        """
        keys = cls.get_all_keys()
        if not keys.exists():
            return None
            
        best_creds = None
        max_free = -1
        
        for k in keys:
            cache_key = f"cloudinary_stats_{k.id}"
            stats = cache.get(cache_key)
            
            if stats is None:
                stats = cls.get_stats_for_key(k)
                # Cachear por 1 hora
                cache.set(cache_key, stats, 3600)
                
            if stats['free_bytes'] > max_free:
                max_free = stats['free_bytes']
                best_creds = cls.parse_cloudinary_url(k.api_key)
                
        # Si falló la consulta o todas están llenas, devolvemos una al azar para evitar errores duros
        if not best_creds:
            random_key = random.choice(keys)
            return cls.parse_cloudinary_url(random_key.api_key)
            
        return best_creds
