"""
Almacenamiento Cloudinary — LeadBook
=====================================
Gestión centralizada de todos los archivos del sistema.
Rota automáticamente entre cuentas Cloudinary cuando una se llena.
Nunca pierde referencias a archivos ya subidos.
"""

import logging
import io
from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader
import cloudinary.api
from django.core.cache import cache
from django.conf import settings

from api.models import APIKey

logger = logging.getLogger(__name__)

# ─── Tipos de asset soportados ────────────────────────────────────────────────
TIPO_PDF      = 'pdf'
TIPO_PDF_COVER = 'pdf_cover'
TIPO_POST     = 'post'
TIPO_STORY    = 'story'
TIPO_CARRUSEL = 'carrusel'
TIPO_EMAIL    = 'email'
TIPO_VIDEO    = 'video'
TIPO_AUDIO    = 'audio'
TIPO_AVATAR   = 'avatar'
TIPO_FOTO_PROPIEDAD = 'foto_propiedad'

# Umbral de espacio libre mínimo antes de considerar una cuenta "llena" (bytes)
UMBRAL_BYTES_MINIMO = 50 * 1024 * 1024  # 50 MB

# Cache TTL para stats de cada cuenta (segundos)
STATS_TTL = 3600  # 1 hora


class AlmacenamientoCloudinary:
    """
    Servicio unificado de almacenamiento. Actúa como capa de abstracción sobre
    todas las cuentas Cloudinary del pool. Decide automáticamente en qué cuenta
    guardar cada nuevo archivo, basándose en el espacio libre disponible.

    Reglas:
    - Los archivos se agrupan bajo el ID del usuario y el tipo.
    - Si hay una cuenta en el pool que tiene espacio, la usa.
    - Si todas están llenas, usa la cuenta global del .env como fallback.
    - El public_id es determinístico: tipo + user_id + listado_id (si aplica).
      Esto permite idempotencia: no se re-sube si ya existe.
    """

    # ── Resolución de credenciales ────────────────────────────────────────────

    @staticmethod
    def _parse_cloudinary_url(url: str) -> dict | None:
        """Parsea cloudinary://api_key:api_secret@cloud_name → dict de credenciales."""
        if not url or not url.startswith('cloudinary://'):
            return None
        parsed = urlparse(url)
        return {
            'api_key': parsed.username,
            'api_secret': parsed.password,
            'cloud_name': parsed.hostname,
        }

    @staticmethod
    def _get_pool_keys():
        """Devuelve todos los APIKey de tipo 'cloudinary' con status válido."""
        return APIKey.objects.filter(
            servicio__nombre__iexact='cloudinary', 
            status__in=['available', 'active', 'assigned', 'in_bundle']
        )

    @classmethod
    def _get_stats(cls, key_obj) -> dict:
        """Consulta uso de almacenamiento de una cuenta (con caché 1h)."""
        cache_key = f'cld_stats_{key_obj.id}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        creds = cls._parse_cloudinary_url(key_obj.api_key)
        if not creds:
            return {'free_bytes': 0, 'error': 'URL inválida'}

        try:
            res = cloudinary.api.usage(
                cloud_name=creds['cloud_name'],
                api_key=creds['api_key'],
                api_secret=creds['api_secret'],
            )
            used = res.get('storage', {}).get('usage', 0)
            limit = res.get('storage', {}).get('limit', 0)
            if limit == 0:
                limit = 25 * 1024 * 1024 * 1024  # 25GB por defecto para cuentas nuevas (basadas en créditos)
            stats = {'free_bytes': limit - used, 'used_bytes': used, 'total_bytes': limit}
        except Exception as e:
            logger.warning(f'[Almacenamiento] No se pudo consultar stats de {key_obj.id}: {e}')
            stats = {'free_bytes': 0, 'error': str(e)}

        cache.set(cache_key, stats, STATS_TTL)
        return stats

    @classmethod
    def _invalidate_stats_cache(cls, key_id):
        """Invalida el caché de stats después de subir un archivo."""
        cache.delete(f'cld_stats_{key_id}')

    @classmethod
    def get_mejor_cuenta(cls) -> tuple[dict | None, int | None]:
        """
        Devuelve (credenciales_dict, key_id) de la cuenta con más espacio libre.
        Filtra las que tienen menos de UMBRAL_BYTES_MINIMO disponibles.
        Retorna (None, None) si no hay cuentas en el pool (usará config global).
        """
        keys = cls._get_pool_keys()
        if not keys.exists():
            return None, None

        mejor_creds = None
        mejor_key_id = None
        max_libre = -1

        for k in keys:
            stats = cls._get_stats(k)
            libre = stats.get('free_bytes', 0)
            if libre > max_libre:
                max_libre = libre
                mejor_creds = cls._parse_cloudinary_url(k.api_key)
                mejor_key_id = k.id

        if not mejor_creds:
            # Todas están casi llenas o el pool está vacío → fallback global
            logger.warning('[Almacenamiento] Todas las cuentas del pool están llenas o vacías. Usando config global.')
            return None, None

        return mejor_creds, mejor_key_id

    @classmethod
    def get_cuentas_ordenadas(cls) -> list[tuple[dict | None, int | None]]:
        """Devuelve cuentas del pool ordenadas por espacio libre y fallback global al final."""
        cuentas = []
        for k in cls._get_pool_keys():
            creds = cls._parse_cloudinary_url(k.api_key)
            if not creds:
                continue
            stats = cls._get_stats(k)
            cuentas.append((stats.get('free_bytes', 0), creds, k.id))
        cuentas.sort(key=lambda row: row[0], reverse=True)
        ordered = [(creds, key_id) for _, creds, key_id in cuentas]

        global_creds = {
            'cloud_name': getattr(settings, 'CLOUDINARY_CLOUD_NAME', '') or getattr(settings, 'CLOUDINARY_CLOUD', ''),
            'api_key': getattr(settings, 'CLOUDINARY_API_KEY', ''),
            'api_secret': getattr(settings, 'CLOUDINARY_API_SECRET', ''),
        }
        if all(global_creds.values()):
            ordered.append((global_creds, None))
        if not ordered:
            ordered.append((None, None))
        return ordered

    # ── Subida de archivos ────────────────────────────────────────────────────

    @classmethod
    def subir(
        cls,
        contenido,               # bytes, BytesIO o path local
        tipo: str,               # TIPO_PDF, TIPO_POST, etc.
        user_id: int,
        listado_id: int | None = None,
        sufijo: str = '',        # ej: "_slide_0" para carrusel
        return_metadata: bool = False,
    ) -> str | None:
        """
        Sube un archivo al Almacenamiento Cloudinary.

        - Selecciona la cuenta con más espacio del pool.
        - Si no hay pool, usa la config global del .env.
        - Devuelve la secure_url del archivo subido, o None si falla.
        """
        # Construir public_id determinístico pero con un hash único para evitar caches de permisos (401)
        import uuid
        unique_hash = uuid.uuid4().hex[:6]

        if isinstance(contenido, (bytes, bytearray, memoryview)):
            contenido = io.BytesIO(bytes(contenido))

        # Lógica especial para listados/fotos de propiedades
        if tipo == TIPO_FOTO_PROPIEDAD:
            base_id = f'leadbook/listados/usuario_{user_id}'
            if listado_id:
                public_id = f'{base_id}/listado_{listado_id}/foto_{unique_hash}{sufijo}'
            else:
                public_id = f'{base_id}/temp/foto_{unique_hash}{sufijo}'
        else:
            base_id = f'leadbook/{tipo}s/user_{user_id}'
            if listado_id:
                public_id = f'{base_id}/listado_{listado_id}_{unique_hash}{sufijo}'
            else:
                public_id = f'{base_id}/{tipo}_{uuid.uuid4().hex[:12]}{sufijo}'
            
            if tipo == TIPO_PDF:
                public_id += '.pdf'

        last_error = None
        for creds, key_id in cls.get_cuentas_ordenadas():
            extra_creds = creds if creds else {}
            try:
                if hasattr(contenido, 'read'):
                    contenido.seek(0)

                upload_params = {
                    'public_id': public_id,
                    'type': 'upload',
                    'overwrite': True,
                    'invalidate': True,
                    **extra_creds,
                }
                if tipo == TIPO_PDF:
                    upload_params['resource_type'] = 'raw'
                    upload_params['access_mode'] = 'public'
                else:
                    upload_params['resource_type'] = 'auto'

                resultado = cloudinary.uploader.upload(contenido, **upload_params)
                resource_type_result = resultado.get('resource_type', 'auto')

                from cloudinary.utils import cloudinary_url
                if tipo == TIPO_PDF:
                    url, _ = cloudinary_url(public_id, resource_type='raw', type='upload', secure=True, **extra_creds)
                else:
                    url, _ = cloudinary_url(public_id, resource_type=resource_type_result, type='upload', sign_url=True, secure=True, **extra_creds)

                if key_id:
                    cls._invalidate_stats_cache(key_id)

                cloud_name_result = (creds or {}).get('cloud_name') or resultado.get('cloud_name') or ''
                if not cloud_name_result and url:
                    parsed_url = urlparse(url)
                    parts = parsed_url.path.strip('/').split('/')
                    if parsed_url.netloc.endswith('res.cloudinary.com') and parts:
                        cloud_name_result = parts[0]

                metadata = {
                    'url': url,
                    'secure_url': resultado.get('secure_url') or url,
                    'cloud_name': cloud_name_result,
                    'cloudinary_account': cloud_name_result,
                    'public_id': resultado.get('public_id') or public_id,
                    'resource_type': resultado.get('resource_type') or resource_type_result,
                    'width': resultado.get('width') or 0,
                    'height': resultado.get('height') or 0,
                    'bytes': resultado.get('bytes') or 0,
                    'format': resultado.get('format') or '',
                    'folder': resultado.get('folder') or '',
                    'original_filename': resultado.get('original_filename') or '',
                    'version': str(resultado.get('version') or ''),
                    'storage_key_id': key_id,
                }
                logger.info(f'[Almacenamiento] ✓ {tipo} subido para user {user_id}: {url}')
                return metadata if return_metadata else url
            except cloudinary.exceptions.Error as e:
                last_error = e
                if 'already exists' in str(e).lower() or '409' in str(e):
                    existing = cls._get_existing_url(public_id, 'auto', extra_creds)
                    if existing:
                        if return_metadata:
                            return {
                                'url': existing,
                                'secure_url': existing,
                                'cloud_name': (creds or {}).get('cloud_name') or '',
                                'cloudinary_account': (creds or {}).get('cloud_name') or '',
                                'public_id': public_id,
                                'resource_type': 'image',
                                'width': 0,
                                'height': 0,
                                'bytes': 0,
                                'format': '',
                                'storage_key_id': key_id,
                            }
                        return existing
                logger.warning(f'[Almacenamiento] Cuenta Cloudinary falló para {tipo}, probando siguiente: {e}')
            except Exception as e:
                last_error = e
                logger.warning(f'[Almacenamiento] Error subiendo {tipo}, probando siguiente cuenta: {e}')
        logger.error(f'[Almacenamiento] Error final subiendo {tipo}: {last_error}')
        return None

    @staticmethod
    def _get_existing_url(public_id: str, resource_type: str, creds: dict) -> str | None:
        """Recupera la URL de un archivo que ya existe en Cloudinary."""
        try:
            info = cloudinary.api.resource(public_id, resource_type=resource_type, **creds)
            return info.get('secure_url')
        except Exception as e:
            logger.warning(f'[Almacenamiento] No se pudo recuperar URL existente: {e}')
            return None

    # ── Métodos de alto nivel por tipo de asset ───────────────────────────────

    @classmethod
    def guardar_pdf(cls, pdf_bytes: bytes, user_id: int, listado_id: int | None = None) -> str | None:
        return cls.subir(pdf_bytes, TIPO_PDF, user_id, listado_id)

    @classmethod
    def guardar_pdf_cover(cls, imagen_stream, user_id: int, listado_id: int | None = None) -> str | None:
        return cls.subir(imagen_stream, TIPO_PDF_COVER, user_id, listado_id)

    @classmethod
    def guardar_post(cls, imagen_stream, user_id: int, listado_id: int | None = None) -> str | None:
        return cls.subir(imagen_stream, TIPO_POST, user_id, listado_id)

    @classmethod
    def guardar_story(cls, imagen_stream, user_id: int, listado_id: int | None = None) -> str | None:
        return cls.subir(imagen_stream, TIPO_STORY, user_id, listado_id)

    @classmethod
    def guardar_slide_carrusel(cls, imagen_stream, user_id: int, listado_id: int | None = None, indice: int = 0) -> str | None:
        return cls.subir(imagen_stream, TIPO_CARRUSEL, user_id, listado_id, sufijo=f'_slide_{indice}')

    @classmethod
    def guardar_video(cls, video_path_o_bytes, user_id: int, listado_id: int | None = None) -> str | None:
        return cls.subir(video_path_o_bytes, TIPO_VIDEO, user_id, listado_id)

    @classmethod
    def guardar_audio(cls, audio_bytes_o_path, user_id: int, listado_id: int | None = None, sufijo: str = '') -> str | None:
        return cls.subir(audio_bytes_o_path, TIPO_AUDIO, user_id, listado_id, sufijo=sufijo)

    @classmethod
    def guardar_avatar(cls, imagen, user_id: int) -> str | None:
        return cls.subir(imagen, TIPO_AVATAR, user_id)

    @classmethod
    def guardar_avatar_metadata(cls, imagen, user_id: int) -> dict | None:
        return cls.subir(imagen, TIPO_AVATAR, user_id, return_metadata=True)

    @classmethod
    def guardar_foto_propiedad(cls, base64_str: str, user_id: int, listado_id: int | None = None, tipo_foto: str = 'portada', indice: int = 0) -> dict | None:
        if not base64_str:
            return None
        
        try:
            import base64
            if ',' in base64_str:
                header, data = base64_str.split(',', 1)
            else:
                data = base64_str
                
            image_bytes = base64.b64decode(data)
            metadata = cls.subir(
                io.BytesIO(image_bytes),
                TIPO_FOTO_PROPIEDAD,
                user_id=user_id,
                listado_id=listado_id,
                sufijo=f'_{tipo_foto}_{indice}',
                return_metadata=True,
            )
            if not metadata:
                return None

            return {
                **metadata,
                "url": metadata.get("url") or metadata.get("secure_url"),
                "secure_url": metadata.get("secure_url") or metadata.get("url"),
                "cloudinary_account": metadata.get("cloudinary_account") or metadata.get("cloud_name", ""),
                "resource_type": metadata.get("resource_type") or "image",
                "role": tipo_foto,
                "order": 0 if tipo_foto == 'portada' else indice + 1,
            }
            
        except Exception as e:
            logger.error(f'[Almacenamiento] Error guardando foto de propiedad: {e}')
            return None

    @classmethod
    def guardar_foto_propiedad_file(
        cls,
        file_obj,
        user_id: int,
        listado_id: int | None = None,
        tipo_foto: str = 'portada',
        indice: int = 0,
    ) -> dict | None:
        if not file_obj:
            return None
        try:
            metadata = cls.subir(
                file_obj,
                TIPO_FOTO_PROPIEDAD,
                user_id=user_id,
                listado_id=listado_id,
                sufijo=f'_{tipo_foto}_{indice}',
                return_metadata=True,
            )
            if not metadata:
                return None
            return {
                **metadata,
                "url": metadata.get("url") or metadata.get("secure_url"),
                "secure_url": metadata.get("secure_url") or metadata.get("url"),
                "cloudinary_account": metadata.get("cloudinary_account") or metadata.get("cloud_name", ""),
                "resource_type": metadata.get("resource_type") or "image",
                "role": tipo_foto,
                "order": 0 if tipo_foto == 'portada' else indice + 1,
            }
        except Exception as exc:
            logger.error(f'[Almacenamiento] Error guardando foto de propiedad (file): {exc}')
            return None

    @classmethod
    def obtener_url_foto(cls, foto_dict: dict) -> str | None:
        """
        Recibe un diccionario {"cloudinary_account": "...", "public_id": "..."}
        Retorna la url_firmada
        """
        if not foto_dict or not isinstance(foto_dict, dict):
            return None
            
        direct_url = foto_dict.get('url') or foto_dict.get('secure_url')
        if isinstance(direct_url, str) and direct_url.strip():
            return direct_url.strip()

        cloud_name = foto_dict.get('cloudinary_account') or foto_dict.get('cloud_name')
        public_id = foto_dict.get('public_id')
        if not cloud_name or not public_id:
            return None
            
        keys = cls._get_pool_keys()
        creds = None
        for k in keys:
            c = cls._parse_cloudinary_url(k.api_key)
            if c and c.get('cloud_name') == cloud_name:
                creds = c
                break
                
        if not creds:
            creds = {
                'cloud_name': getattr(settings, 'CLOUDINARY_CLOUD_NAME', ''),
                'api_key': getattr(settings, 'CLOUDINARY_API_KEY', ''),
                'api_secret': getattr(settings, 'CLOUDINARY_API_SECRET', ''),
            }

        try:
            from cloudinary.utils import cloudinary_url
            url_params = {
                'resource_type': foto_dict.get('resource_type') or 'image',
                'type': 'upload',
                'secure': True,
            }
            if creds and all(creds.get(k) for k in ('cloud_name', 'api_key', 'api_secret')):
                url_params.update(creds)
                url_params['sign_url'] = True
            else:
                url_params['cloud_name'] = cloud_name
            url, _ = cloudinary_url(public_id, **url_params)
            return url
        except Exception as e:
            logger.error(f'[Almacenamiento] Error firmando url foto: {e}')
            if cloud_name:
                return f'https://res.cloudinary.com/{cloud_name}/image/upload/{public_id}'
            return None

    # ── Estado del pool ───────────────────────────────────────────────────────

    @classmethod
    def estado_pool(cls) -> list[dict]:
        """
        Devuelve el estado de todas las cuentas del pool.
        Útil para el admin dashboard.
        """
        keys = cls._get_pool_keys()
        resultado = []
        for k in keys:
            stats = cls._get_stats(k)
            creds = cls._parse_cloudinary_url(k.api_key) or {}
            resultado.append({
                'key_id': k.id,
                'cloud_name': creds.get('cloud_name', '?'),
                'libre_gb': round(stats.get('free_bytes', 0) / (1024**3), 2),
                'usado_gb': round(stats.get('used_bytes', 0) / (1024**3), 2),
                'total_gb': round(stats.get('total_bytes', 0) / (1024**3), 2),
                'disponible': stats.get('free_bytes', 0) >= UMBRAL_BYTES_MINIMO,
                'error': stats.get('error'),
            })
        return resultado
