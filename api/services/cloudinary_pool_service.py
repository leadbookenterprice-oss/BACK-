from urllib.parse import urlparse

import cloudinary.api
from django.core.cache import cache

from api.models import APIKey


MIN_FREE_BYTES = 50 * 1024 * 1024
DEFAULT_TOTAL_BYTES = 25 * 1024 * 1024 * 1024


class CloudinaryPoolService:
    @staticmethod
    def parse_cloudinary_url(url):
        if not url or not url.startswith('cloudinary://'):
            return None
        parsed = urlparse(url)
        return {
            'api_key': parsed.username,
            'api_secret': parsed.password,
            'cloud_name': parsed.hostname,
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
                api_secret=creds['api_secret'],
            )
            used = int(res.get('storage', {}).get('usage', 0) or 0)
            limit = int(res.get('storage', {}).get('limit', 0) or 0) or DEFAULT_TOTAL_BYTES
            return {'total_bytes': limit, 'used_bytes': used, 'free_bytes': limit - used}
        except Exception as e:
            return {'total_bytes': 0, 'used_bytes': 0, 'free_bytes': 0, 'error': str(e)}

    @staticmethod
    def get_all_keys():
        return APIKey.objects.filter(
            servicio__nombre__iexact='cloudinary',
            status__in=['available', 'active', 'assigned', 'in_bundle'],
        ).order_by('id')

    @classmethod
    def get_best_credentials(cls):
        """
        Devuelve la primera cuenta utilizable en orden de carga.
        Si no hay pool disponible, devuelve None para usar el fallback global.
        """
        keys = cls.get_all_keys()
        if not keys.exists():
            return None

        for key in keys:
            cache_key = f"cloudinary_stats_{key.id}"
            stats = cache.get(cache_key)
            if stats is None:
                stats = cls.get_stats_for_key(key)
                cache.set(cache_key, stats, 3600)

            if not stats.get('error') and stats.get('free_bytes', 0) >= MIN_FREE_BYTES:
                return cls.parse_cloudinary_url(key.api_key)

        return None
