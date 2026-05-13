from rest_framework import serializers
from .models import (
    GeneratedAsset, Agent, ComercialAgentProfile,
    AgentMediaAsset, UserContentPreference,
    BrandTemplate, BrandTemplateRevision,
    TerminosCondiciones, PoliticaPrivacidad
)
import re


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Agent
        fields = ('email', 'password', 'nombre', 'telefono', 'agencia')

    def create(self, validated_data):
        user = Agent.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            nombre=validated_data['nombre'],
            telefono=validated_data.get('telefono', ''),
            agencia=validated_data.get('agencia', '')
        )
        return user


class GeneratedAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedAsset
        fields = '__all__'


class TerminosCondicionesSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminosCondiciones
        fields = ['id', 'titulo', 'contenido', 'version', 'fecha_actualizacion']


class PoliticaPrivacidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoliticaPrivacidad
        fields = ['id', 'titulo', 'contenido', 'version', 'fecha_actualizacion']


class AgentMediaAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMediaAsset
        fields = [
            'id', 'kind', 'cloud_name', 'public_id', 'resource_type', 'secure_url',
            'bytes', 'format', 'folder', 'original_filename', 'version', 'is_active', 'uploaded_at',
        ]
        read_only_fields = fields


class ComercialAgentProfileSerializer(serializers.ModelSerializer):
    foto_asset = serializers.SerializerMethodField()

    class Meta:
        model = ComercialAgentProfile
        fields = [
            'id',
            'nombre',
            'rol',
            'email',
            'telefono_e164',
            'foto_url',
            'foto_asset',
            'is_default',
            'activo',
            'creado_en',
            'updated_at',
        ]
        read_only_fields = ['id', 'creado_en', 'updated_at']

    def get_foto_asset(self, obj):
        asset = obj.media_assets.filter(kind='agent_photo', is_active=True).order_by('-uploaded_at').first()
        return AgentMediaAssetSerializer(asset).data if asset else None

    def validate_telefono_e164(self, value):
        if value in (None, ''):
            return None

        phone = str(value).strip().replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            phone = f'+{phone}'

        import re
        if not re.match(r'^\+[1-9]\d{6,14}$', phone):
            raise serializers.ValidationError('telefono_e164 debe estar en formato E.164 (ej: +5491123456789).')

        return phone


class UserContentPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserContentPreference
        fields = ['hashtags', 'emoji_density', 'use_emojis', 'tone', 'updated_at']
        read_only_fields = ['updated_at']

    def validate_hashtags(self, value):
        if value in (None, ''):
            return []
        if isinstance(value, str):
            raw_items = re.split(r'[\s,]+', value)
        elif isinstance(value, list):
            raw_items = value
        else:
            raise serializers.ValidationError('hashtags debe ser lista o texto.')

        cleaned = []
        for item in raw_items:
            tag = str(item or '').strip()
            if not tag:
                continue
            tag = tag if tag.startswith('#') else f'#{tag}'
            tag = re.sub(r'[^#\wÁÉÍÓÚÜÑáéíóúüñ]', '', tag)
            if len(tag) > 1 and tag not in cleaned:
                cleaned.append(tag[:50])
        return cleaned[:20]

    def validate_emoji_density(self, value):
        if value not in {'none', 'low', 'medium', 'high'}:
            raise serializers.ValidationError('emoji_density invalido.')
        return value


ALLOWED_FONTS = {
    'Playfair Display',
    'Bebas Neue',
    'Inter',
    'DM Sans',
    'Space Mono',
    'Cormorant Garamond',
    'Oswald',
    'Source Sans 3',
    'Source Serif 4',
    'Libre Baskerville',
    'Lato',
    'Space Grotesk',
}


def _validate_hex_color(value, field_name):
    if not isinstance(value, str) or not re.match(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', value.strip()):
        raise serializers.ValidationError(f'{field_name} debe ser un color HEX valido (ej: #0d47a1).')
    return value.strip()


class BrandTemplateRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandTemplateRevision
        fields = [
            'id', 'template', 'revision', 'tokens_json', 'gemini_instructions',
            'preview_html', 'status', 'created_by', 'created_at', 'notes',
        ]
        read_only_fields = ['id', 'template', 'revision', 'created_by', 'created_at']

    def validate_tokens_json(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('tokens_json debe ser un objeto JSON.')

        palette = value.get('palette') or {}
        for key in ('primary', 'secondary', 'accent', 'background', 'text'):
            if key not in palette:
                raise serializers.ValidationError(f'palette.{key} es requerido.')
            palette[key] = _validate_hex_color(palette[key], f'palette.{key}')

        typography = value.get('typography') or {}
        for key in ('display', 'body', 'mono'):
            font_value = typography.get(key)
            if font_value not in ALLOWED_FONTS:
                raise serializers.ValidationError(f'typography.{key} debe estar en la allowlist de fuentes.')

        google_fonts = typography.get('google_fonts') or []
        if not isinstance(google_fonts, list) or not google_fonts:
            raise serializers.ValidationError('typography.google_fonts debe ser una lista no vacia.')
        for font_name in google_fonts:
            if font_name not in ALLOWED_FONTS:
                raise serializers.ValidationError('typography.google_fonts contiene una fuente no permitida.')

        emoji = value.get('emoji') or {}
        for key in ('headline', 'price', 'location', 'cta'):
            symbol = str(emoji.get(key, '')).strip()
            if not symbol:
                raise serializers.ValidationError(f'emoji.{key} es requerido.')
            if len(symbol) > 6:
                raise serializers.ValidationError(f'emoji.{key} es demasiado largo.')

        copy = value.get('copy') or {}
        if copy.get('tone') not in {'premium', 'profesional', 'lujo', 'minimal'}:
            raise serializers.ValidationError('copy.tone invalido.')
        if copy.get('emoji_density') not in {'none', 'low', 'medium', 'high'}:
            raise serializers.ValidationError('copy.emoji_density invalido.')
        if copy.get('cta_style') not in {'whatsapp_direct', 'soft', 'strong'}:
            raise serializers.ValidationError('copy.cta_style invalido.')
        hashtags = copy.get('hashtags') or []
        if isinstance(hashtags, str):
            hashtags = re.split(r'[\s,]+', hashtags)
        if not isinstance(hashtags, list):
            raise serializers.ValidationError('copy.hashtags debe ser lista o texto.')
        copy['hashtags'] = [
            (str(tag).strip() if str(tag).strip().startswith('#') else f"#{str(tag).strip()}")[:50]
            for tag in hashtags
            if str(tag or '').strip()
        ][:20]

        layout = value.get('layout') or {}
        if layout.get('logo_position') not in {'top_left', 'top_right'}:
            raise serializers.ValidationError('layout.logo_position invalido.')
        if layout.get('agent_block_position') not in {'bottom_left', 'bottom_right'}:
            raise serializers.ValidationError('layout.agent_block_position invalido.')
        if layout.get('qr_position') not in {'bottom_left', 'bottom_right'}:
            raise serializers.ValidationError('layout.qr_position invalido.')

        layout.setdefault('style', 'tech_modern')
        layout.setdefault('density', 'comfortable')
        layout.setdefault('border_radius', 'medium')
        layout.setdefault('image_treatment', 'normal')

        value['schema_version'] = 1
        value['palette'] = palette
        value['typography'] = typography
        value['emoji'] = emoji
        value['copy'] = copy
        value['layout'] = layout
        return value


class BrandTemplateSerializer(serializers.ModelSerializer):
    published_revision = serializers.SerializerMethodField()

    class Meta:
        model = BrandTemplate
        fields = [
            'id',
            'owner',
            'name',
            'slug',
            'description',
            'base_template_id',
            'is_default',
            'is_active',
            'created_at',
            'updated_at',
            'published_revision',
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at', 'published_revision']

    def get_published_revision(self, obj):
        published = obj.revisions.filter(status='published').order_by('-revision').first()
        if not published:
            return None
        return {
            'id': published.id,
            'revision': published.revision,
            'tokens_json': published.tokens_json,
            'gemini_instructions': published.gemini_instructions or '',
            'preview_html': published.preview_html or '',
            'created_at': published.created_at,
        }
