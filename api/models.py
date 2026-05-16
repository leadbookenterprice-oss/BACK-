# =============================================================================
# api/models.py — LeadBook v2.0
# Schema reescrito desde cero. Limpio, robusto, escalable.
# Resuelve: duplicados, dead code, race conditions, seguridad, compliance.
# =============================================================================

from django.db import models, transaction
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta


# ══════════════════════════════════════════════════════════════════════════════
# USUARIO
# ══════════════════════════════════════════════════════════════════════════════

class AgentManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

    def get_queryset(self):
        # Soft delete: por defecto solo devuelve usuarios no eliminados
        return super().get_queryset().filter(eliminado_en__isnull=True)

    def all_including_deleted(self):
        return super().get_queryset()


class Agent(AbstractBaseUser, PermissionsMixin):
    """
    Usuario principal del sistema.

    DECISIONES DE DISEÑO:
    - plan_nombre es LA ÚNICA fuente de verdad del plan (eliminado campo 'plan')
    - is_active es EL ÚNICO campo de estado activo (eliminado campo 'activo')
    - eliminado_en para soft delete — nunca se borra un usuario de la DB
    - meta_access_token: marcar con EncryptedTextField en producción
    - agentes_asociados removido — reemplazado por tabla AgentAssociation
    """
    PLANES = [
        ('free',     'Free'),
        ('starter',  'Starter'),
        ('pro',      'Pro'),
        ('scale',    'Scale'),
        ('business', 'Business'),
    ]

    # Identidad
    email                  = models.EmailField(unique=True)
    nombre                 = models.CharField(max_length=255)
    telefono               = models.CharField(max_length=50, null=True, blank=True)
    agencia                = models.CharField(max_length=255, null=True, blank=True)
    logo_url               = models.TextField(null=True, blank=True)
    nombre_inmobiliaria    = models.CharField(max_length=255, null=True, blank=True)
    nicho                  = models.CharField(max_length=100, null=True, blank=True)
    pais                   = models.CharField(max_length=100, null=True, blank=True)
    nacionalidad           = models.CharField(max_length=100, null=True, blank=True)
    sitio_web              = models.URLField(max_length=255, null=True, blank=True)
    bio                    = models.TextField(null=True, blank=True)

    # Plan — UN SOLO campo, fuente de verdad
    plan_nombre            = models.CharField(max_length=20, choices=PLANES, default='free')
    plan_activo            = models.BooleanField(default=True)
    plan_seleccionado      = models.BooleanField(default=False)

    # Social — TODO: usar EncryptedTextField de django-encrypted-model-fields
    meta_access_token          = models.TextField(null=True, blank=True)
    meta_instagram_account_id  = models.CharField(max_length=100, null=True, blank=True)

    # Estado — UN SOLO campo
    is_active              = models.BooleanField(default=True)
    is_staff               = models.BooleanField(default=False)

    # Seguridad
    last_login_ip          = models.GenericIPAddressField(null=True, blank=True)
    last_login_user_agent  = models.TextField(null=True, blank=True)
    last_seen              = models.DateTimeField(null=True, blank=True)

    # Auditoría
    fecha_registro         = models.DateTimeField(auto_now_add=True)
    updated_at             = models.DateTimeField(auto_now=True)
    eliminado_en           = models.DateTimeField(null=True, blank=True)  # Soft delete

    objects = AgentManager()
    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['nombre']

    def __str__(self):
        return f"{self.nombre} <{self.email}>"

    def soft_delete(self):
        """
        Anonimiza al usuario en vez de borrarlo físicamente.
        Cumple Ley 25326 (derecho al olvido) sin romper registros contables.
        """
        try:
            from api.services.pool_service import APIPoolService
            APIPoolService.release_keys_from_user(self)
        except Exception:
            pass

        self.email    = f"deleted_{self.id}@leadbook.com"
        self.nombre   = "Usuario eliminado"
        self.telefono = None
        self.meta_access_token         = None
        self.meta_instagram_account_id = None
        self.is_active   = False
        self.eliminado_en = timezone.now()
        self.save()

    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['plan_nombre']),
            models.Index(fields=['is_active']),
            models.Index(fields=['eliminado_en']),
        ]


class AgentAssociation(models.Model):
    """
    Agentes asociados a una agencia/equipo.
    Reemplaza el JSONField agentes_asociados — ahora es consultable y eficiente.
    """
    agente   = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='mis_asociados')
    asociado = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='asociado_a')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('agente', 'asociado')


class ComercialAgentProfile(models.Model):
    """
    Perfil comercial reutilizable para branding en assets.
    Un usuario puede tener varios perfiles y marcar uno como default.
    """

    owner = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='commercial_agents')
    nombre = models.CharField(max_length=255)
    rol = models.CharField(max_length=120, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telefono_e164 = models.CharField(max_length=20, blank=True, null=True)
    foto_url = models.TextField(blank=True, null=True)
    is_default = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['owner'],
                condition=models.Q(is_default=True),
                name='unique_default_commercial_agent_per_owner',
            )
        ]
        indexes = [
            models.Index(fields=['owner', 'is_default']),
            models.Index(fields=['owner', 'activo']),
        ]

    def save(self, *args, **kwargs):
        if self.telefono_e164:
            value = str(self.telefono_e164).strip()
            if value and not value.startswith('+'):
                value = f'+{value}'
            self.telefono_e164 = value

        if self.is_default and self.owner_id:
            ComercialAgentProfile.objects.filter(
                owner_id=self.owner_id,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.owner_id})"


class AgentMediaAsset(models.Model):
    """Cloudinary asset vinculado a un perfil comercial."""

    ASSET_KINDS = [
        ('agent_photo', 'Agent Photo'),
    ]

    owner = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='agent_media_assets')
    profile = models.ForeignKey(ComercialAgentProfile, on_delete=models.CASCADE, related_name='media_assets')
    kind = models.CharField(max_length=40, choices=ASSET_KINDS, default='agent_photo')
    cloud_name = models.CharField(max_length=120)
    public_id = models.CharField(max_length=255)
    resource_type = models.CharField(max_length=40, default='image')
    secure_url = models.TextField(blank=True, null=True)
    bytes = models.PositiveIntegerField(default=0)
    format = models.CharField(max_length=30, blank=True, null=True)
    folder = models.CharField(max_length=255, blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    version = models.CharField(max_length=60, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['owner', 'kind', 'is_active']),
            models.Index(fields=['profile', 'kind', 'is_active']),
            models.Index(fields=['cloud_name', 'public_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['profile'],
                condition=models.Q(kind='agent_photo', is_active=True),
                name='unique_active_agent_photo_per_profile',
            )
        ]

    def as_cloudinary_ref(self):
        return {
            'cloudinary_account': self.cloud_name,
            'cloud_name': self.cloud_name,
            'public_id': self.public_id,
            'resource_type': self.resource_type,
            'url': self.secure_url or '',
        }

    def __str__(self):
        return f"{self.kind}:{self.public_id}"


class UserContentPreference(models.Model):
    """Preferencias globales para captions generados por IA."""

    EMOJI_DENSITY_CHOICES = [
        ('none', 'None'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    owner = models.OneToOneField(Agent, on_delete=models.CASCADE, related_name='content_preferences')
    hashtags = models.JSONField(default=list, blank=True)
    emoji_density = models.CharField(max_length=20, choices=EMOJI_DENSITY_CHOICES, default='medium')
    use_emojis = models.BooleanField(default=True)
    tone = models.CharField(max_length=40, default='premium')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"content-preferences:{self.owner_id}"


def default_template_tokens():
    return {
        'schema_version': 2,
        'palette': {
            'primary': '#0d47a1',
            'secondary': '#1565c0',
            'accent': '#00e5ff',
            'background': '#081421',
            'surface': '#0d1b2a',
            'text': '#e8f3ff',
            'muted_text': '#8fb1d1',
            'border': '#1d3e5d',
            'overlay': 'rgba(0,0,0,0.65)',
        },
        'typography': {
            'display': 'Space Grotesk',
            'body': 'DM Sans',
            'mono': 'Space Mono',
            'google_fonts': ['Space Grotesk', 'DM Sans', 'Space Mono'],
            'title_transform': 'uppercase',
            'letter_spacing': 'normal',
        },
        'emoji': {
            'headline': '✨',
            'price': '💰',
            'location': '📍',
            'cta': '📲',
        },
        'copy': {
            'tone': 'premium',
            'emoji_density': 'low',
            'cta_style': 'whatsapp_direct',
            'hashtags': ['#RealEstate', '#Inmobiliaria', '#Propiedades', '#Inversion'],
        },
        'layout': {
            'logo_position': 'top_right',
            'agent_block_position': 'bottom_left',
            'qr_position': 'bottom_right',
            'style': 'tech_modern',
            'density': 'comfortable',
            'border_radius': 'medium',
            'image_treatment': 'normal',
            'custom_css': '',
        },
        'components': {
            'hero': {
                'variant': 'full_bleed',
                'title_position': 'bottom_left',
                'overlay_strength': 'medium',
                'show_badge': True,
            },
            'price': {
                'variant': 'pill',
                'position': 'below_title',
                'size': 'medium',
            },
            'stats': {
                'variant': 'cards',
                'show_icons': True,
            },
            'gallery': {
                'variant': 'mosaic',
                'max_items': 6,
            },
            'contact': {
                'variant': 'card',
                'show_agent_photo': True,
                'show_qr': True,
            },
        },
        'formats': {
            'pdf': {'show_gallery': True},
            'post': {'aspect_ratio': '4:5', 'safe_area': True},
            'story': {'aspect_ratio': '9:16', 'safe_area': True},
            'carousel': {'aspect_ratio': '4:5', 'gallery_slide_fit': 'contain'},
            'email': {'width': 600, 'show_gallery': True, 'button_style': 'solid'},
        },
    }


class BrandTemplate(models.Model):
    BASE_TEMPLATE_CHOICES = [
        ('dubai_night', 'Dubai Night'),
        ('beverly_hills', 'Beverly Hills'),
        ('manhattan', 'Manhattan'),
        ('mediterraneo', 'Mediterraneo'),
        ('tech_modern', 'Tech Modern'),
    ]

    owner = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='brand_templates')
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.TextField(blank=True, null=True)
    base_template_id = models.CharField(max_length=40, choices=BASE_TEMPLATE_CHOICES, default='tech_modern')
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'slug'], name='unique_brand_template_slug_per_owner'),
            models.UniqueConstraint(
                fields=['owner'],
                condition=models.Q(is_default=True, is_active=True),
                name='unique_default_brand_template_per_owner',
            ),
        ]
        indexes = [
            models.Index(fields=['owner', 'is_active']),
            models.Index(fields=['owner', 'is_default']),
        ]

    def save(self, *args, **kwargs):
        base_slug = slugify(self.slug or self.name or '')[:120] or f'template-{self.owner_id or "owner"}'
        next_slug = base_slug
        suffix = 2
        while self.owner_id and BrandTemplate.objects.filter(owner_id=self.owner_id, slug=next_slug).exclude(pk=self.pk).exists():
            suffix_text = f'-{suffix}'
            next_slug = f'{base_slug[:140 - len(suffix_text)]}{suffix_text}'
            suffix += 1
        self.slug = next_slug[:140]

        if self.is_default and self.owner_id:
            BrandTemplate.objects.filter(
                owner_id=self.owner_id,
                is_default=True,
                is_active=True,
            ).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.owner_id})"


class BrandTemplateRevision(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    template = models.ForeignKey(BrandTemplate, on_delete=models.CASCADE, related_name='revisions')
    revision = models.IntegerField()
    tokens_json = models.JSONField(default=default_template_tokens)
    gemini_instructions = models.TextField(blank=True, null=True)
    preview_html = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='template_revisions_created')
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-revision']
        constraints = [
            models.UniqueConstraint(fields=['template', 'revision'], name='unique_template_revision_number'),
            models.UniqueConstraint(
                fields=['template'],
                condition=models.Q(status='published'),
                name='unique_published_revision_per_template',
            ),
        ]
        indexes = [models.Index(fields=['template', 'status'])]

    def save(self, *args, **kwargs):
        if not self.revision:
            last = BrandTemplateRevision.objects.filter(template_id=self.template_id).order_by('-revision').first()
            self.revision = (last.revision if last else 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.template_id} r{self.revision}"


class CRMClient(models.Model):
    """Cliente/lead básico para el CRM de cada inmobiliaria."""

    ESTADOS = [
        ('nuevo', 'Nuevo'),
        ('contactado', 'Contactado'),
        ('interesado', 'Interesado'),
        ('visita', 'Visita agendada'),
        ('cerrado', 'Cerrado'),
        ('descartado', 'Descartado'),
    ]

    owner = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='crm_clients')
    nombre = models.CharField(max_length=180)
    email = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=40, blank=True, null=True)
    estado = models.CharField(max_length=24, choices=ESTADOS, default='nuevo')
    origen = models.CharField(max_length=80, blank=True, null=True)
    presupuesto = models.CharField(max_length=80, blank=True, null=True)
    ciudad_interes = models.CharField(max_length=120, blank=True, null=True)
    notas = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['owner', 'estado']),
            models.Index(fields=['owner', 'updated_at']),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.owner_id})"


# ══════════════════════════════════════════════════════════════════════════════
# PLANES Y SUSCRIPCIONES
# ══════════════════════════════════════════════════════════════════════════════

class Plan(models.Model):
    """
    Configuración de cada plan de suscripción.
    Incluye los límites de API por servicio para poder recalcular quotas al cambiar de plan.
    """
    PLAN_CHOICES = [
        ('free',     'Free'),
        ('starter',  'Starter'),
        ('pro',      'Pro'),
        ('scale',    'Scale'),
        ('business', 'Business'),
    ]
    nombre               = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    precio_ars_mensual   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_ars_anual     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    listados_por_mes     = models.IntegerField(default=20)
    ai_generaciones      = models.IntegerField(default=50)

    # Límites de API por plan — usados para recalcular UserAPIQuota al cambiar de plan
    gemini_daily_limit      = models.IntegerField(default=1500)
    elevenlabs_daily_limit  = models.IntegerField(default=1500)
    uploadpost_daily_limit  = models.IntegerField(default=10)

    video_generaciones   = models.IntegerField(default=0)
    auto_posting         = models.BooleanField(default=False)
    voice_ai             = models.BooleanField(default=False)
    branding             = models.BooleanField(default=False)
    priority_support     = models.BooleanField(default=False)
    mp_plan_id           = models.CharField(max_length=100, null=True, blank=True)
    activo               = models.BooleanField(default=True)

    def __str__(self): return self.nombre


class Suscripcion(models.Model):
    """
    Suscripción activa del usuario.
    Los contadores de uso (properties_used, ai_used, etc.) fueron ELIMINADOS.
    El uso real siempre se calcula desde UsageLog — sin duplicados.
    """
    STATUS = [
        ('free',       'Free'),
        ('active',     'Activa'),
        ('paused',     'Pausada'),
        ('cancelled',  'Cancelada'),
        ('past_due',   'Vencida'),
    ]
    agente             = models.OneToOneField(Agent, on_delete=models.CASCADE, related_name='suscripcion')
    plan               = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    mp_subscription_id = models.CharField(max_length=100, null=True, blank=True)
    mp_preapproval_id  = models.CharField(max_length=100, null=True, blank=True)
    mp_customer_id     = models.CharField(max_length=100, null=True, blank=True)
    mp_status          = models.CharField(max_length=20, choices=STATUS, default='free')
    periodo_inicio     = models.DateTimeField(auto_now_add=True)
    periodo_fin        = models.DateTimeField(null=True, blank=True)
    activa             = models.BooleanField(default=True)
    updated_at         = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.agente.email} — {self.plan}"


# ══════════════════════════════════════════════════════════════════════════════
# CONTENIDO
# ══════════════════════════════════════════════════════════════════════════════

class Listado(models.Model):
    """
    Propiedad inmobiliaria generada por el usuario.
    Los campos importantes son columnas reales (consultables, indexables).
    El resto va en datos_extra JSONField.
    """
    OPERACIONES = [
        ('venta',             'Venta'),
        ('alquiler',          'Alquiler'),
        ('alquiler_temporal', 'Alquiler Temporal'),
    ]

    agente           = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='listados')

    # Campos indexables — no van en JSON
    titulo           = models.CharField(max_length=255)
    tipo_propiedad   = models.CharField(max_length=100)
    operacion        = models.CharField(max_length=20, choices=OPERACIONES, default='venta')
    ciudad           = models.CharField(max_length=100)
    barrio           = models.CharField(max_length=100, null=True, blank=True)
    precio           = models.CharField(max_length=50)
    moneda           = models.CharField(max_length=10, default='USD')
    ambientes        = models.IntegerField(null=True, blank=True)
    metros_cuadrados = models.IntegerField(null=True, blank=True)

    # Estado de generación
    video_url        = models.URLField(max_length=500, null=True, blank=True)
    video_status     = models.CharField(max_length=50, default='none')
    videos_creados   = models.IntegerField(default=0)
    brand_template   = models.ForeignKey('BrandTemplate', on_delete=models.SET_NULL, null=True, blank=True, related_name='listados')
    brand_template_revision = models.ForeignKey('BrandTemplateRevision', on_delete=models.SET_NULL, null=True, blank=True, related_name='listados')

    # Datos adicionales no estructurados
    datos_extra      = models.JSONField(default=dict, blank=True)

    creado_en        = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.titulo} — {self.agente.nombre}"

    class Meta:
        ordering = ['-creado_en']
        indexes = [
            models.Index(fields=['agente', 'creado_en']),
            models.Index(fields=['ciudad']),
            models.Index(fields=['tipo_propiedad']),
            models.Index(fields=['operacion']),
        ]


class GeneratedAsset(models.Model):
    """
    Asset generado (PDF, video, email, social).
    USA cloudinary_url — nunca FileField (Railway borra archivos en cada deploy).
    """
    ASSET_TYPES = [
        ('pdf',    'PDF Brochure'),
        ('video',  'Video'),
        ('email',  'Email'),
        ('social', 'Social Media'),
    ]
    STATUS = [
        ('pending',   'Pendiente'),
        ('processing','Procesando'),
        ('done',      'Listo'),
        ('error',     'Error'),
    ]

    listado            = models.ForeignKey(Listado, on_delete=models.CASCADE, related_name='assets')
    asset_type         = models.CharField(max_length=10, choices=ASSET_TYPES)
    cloudinary_url     = models.URLField(max_length=500, null=True, blank=True)
    cloudinary_public_id = models.CharField(max_length=255, null=True, blank=True)
    status             = models.CharField(max_length=20, choices=STATUS, default='pending')
    error_message      = models.TextField(null=True, blank=True)
    creado_en          = models.DateTimeField(auto_now_add=True)
    completado_en      = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['listado', 'asset_type'])]


# ══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE APIs — EL CORAZÓN
# ══════════════════════════════════════════════════════════════════════════════

class Servicio(models.Model):
    """
    Catálogo de servicios de API disponibles.
    Reemplaza los strings sueltos 'gemini', 'elevenlabs', etc.
    Para agregar Groq, NVIDIA, Anthropic: solo insertar una fila acá.
    La estructura del sistema no cambia — solo los datos.
    """
    nombre             = models.CharField(max_length=50, unique=True)
    descripcion        = models.CharField(max_length=255, blank=True)
    activo             = models.BooleanField(default=True)
    default_daily_limit   = models.IntegerField(default=1500)
    default_monthly_limit = models.IntegerField(null=True, blank=True)
    extra_increment    = models.IntegerField(default=1500)  # Cuánto suma una API extra

    def __str__(self): return self.nombre

    class Meta:
        ordering = ['nombre']


class APIKey(models.Model):
    """
    Nuestra bodega de claves API.
    Una fila = una clave real de Google/ElevenLabs/etc. que nos pertenece.

    CAMBIOS vs v1:
    - Sin assigned_to: la asignación va en UserAPIAssignment
    - google_daily_limit en vez de daily_limit (evita confusión con user limit)
    - servicio es FK a Servicio, no string libre (sin typos posibles)
    - api_key: marcar con EncryptedTextField en producción
    """
    STATUS = [
        ('available',  'Disponible'),
        ('assigned',   'Asignada'),
        ('exhausted',  'Agotada hoy'),
        ('dead',       'Muerta'),
        ('disabled',   'Deshabilitada'),
    ]

    servicio             = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name='keys')
    api_key              = models.TextField()  # TODO: EncryptedTextField
    label                = models.CharField(max_length=100, blank=True, null=True)
    empresa              = models.CharField(max_length=100, blank=True, null=True)
    status               = models.CharField(max_length=20, choices=STATUS, default='available')

    # Límites de la clave — lo que Google/ElevenLabs nos permite a nosotros
    google_daily_limit   = models.IntegerField(default=1500)
    google_monthly_limit = models.IntegerField(null=True, blank=True)

    # Estadísticas de uso de la clave
    requests_today       = models.IntegerField(default=0)
    requests_this_month  = models.IntegerField(default=0)
    total_requests       = models.IntegerField(default=0)
    error_count          = models.IntegerField(default=0)

    # Health
    last_used_at         = models.DateTimeField(null=True, blank=True)
    last_health_check    = models.DateTimeField(null=True, blank=True)
    last_health_status   = models.BooleanField(default=True)

    notes                = models.TextField(null=True, blank=True)
    creado_en            = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.servicio.nombre} — {self.api_key[:12]}..."

    class Meta:
        indexes = [
            models.Index(fields=['servicio', 'status']),
            models.Index(fields=['status']),
        ]


class UserAPIAssignment(models.Model):
    """
    Qué clave tiene asignada cada usuario para cada servicio.

    Reemplaza TODO:
    - APIKey.assigned_to (asignación directa legacy)
    - APIBundle (bundle muerto)
    - APIBundleAssignment (bundle muerto)
    - BundleAPIExtra (extras comprados)

    is_primary=True  → clave base asignada al registrarse
    is_primary=False → clave extra comprada con pago
    """
    user      = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='api_assignments')
    apikey    = models.ForeignKey(APIKey, on_delete=models.PROTECT, related_name='assignments')
    servicio  = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name='assignments')
    is_primary = models.BooleanField(default=True)
    activo    = models.BooleanField(default=True)
    pago      = models.ForeignKey(
        'Pago', on_delete=models.SET_NULL, null=True, blank=True,
        help_text="null = asignada manualmente por admin"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        tipo = 'primaria' if self.is_primary else 'extra'
        return f"{self.user.email} → {self.servicio.nombre} ({tipo})"

    class Meta:
        indexes = [
            models.Index(fields=['user', 'servicio', 'activo']),
            models.Index(fields=['apikey']),
        ]
        constraints = [
            # Un usuario solo puede tener UNA clave primaria activa por servicio
            models.UniqueConstraint(
                fields=['user', 'servicio'],
                condition=models.Q(is_primary=True, activo=True),
                name='unique_primary_assignment_per_user_service'
            )
        ]


class UserAPIQuota(models.Model):
    """
    ÚNICA fuente de verdad del consumo de APIs por usuario.

    REGLA: nada más trackea el consumo. Solo esta tabla.
    - requests_today: cuánto usó hoy
    - user_daily_limit: cuánto le permitimos (base del plan + extras activos)
    - is_blocked: True cuando requests_today >= user_daily_limit
    - maybe_reset_daily(): fallback si Celery está caído

    CAMBIO vs v1: daily_limit → user_daily_limit (evita confusión con google_daily_limit)
    """
    user      = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='api_quotas')
    servicio  = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name='quotas')

    # Límites — lo que nosotros le permitimos al usuario
    user_daily_limit    = models.IntegerField(default=1500)
    user_monthly_limit  = models.IntegerField(null=True, blank=True)

    # Uso actual
    requests_today      = models.IntegerField(default=0)
    requests_this_month = models.IntegerField(default=0)

    # Bloqueo
    is_blocked          = models.BooleanField(default=False)
    blocked_reason      = models.CharField(max_length=255, null=True, blank=True)

    # Timestamps de reset
    last_reset_daily    = models.DateTimeField(null=True, blank=True)
    last_reset_monthly  = models.DateTimeField(null=True, blank=True)

    updated_at          = models.DateTimeField(auto_now=True)

    def maybe_reset_daily(self):
        """
        Reset lazy: las APIs free se resetean cada 12 horas; el resto, diario.
        Es el fallback para cuando Celery está caído.
        Se llama al inicio de cada request antes de verificar la cuota.
        """
        now = timezone.now()
        servicio_nombre = str(getattr(self.servicio, 'nombre', '') or '').lower()
        uses_twelve_hour_reset = servicio_nombre in {'gemini', 'elevenlabs'}

        if uses_twelve_hour_reset:
            should_reset = self.last_reset_daily is None or now - self.last_reset_daily >= timedelta(hours=12)
        else:
            should_reset = self.last_reset_daily is None or self.last_reset_daily.date() < now.date()

        if should_reset:
            should_notify = (
                uses_twelve_hour_reset
                and self.last_reset_daily is not None
                and (self.is_blocked or self.requests_today >= (self.user_daily_limit or 0))
            )
            self.requests_today = 0
            self.is_blocked     = False
            self.blocked_reason = None
            self.last_reset_daily = now
            self.save(update_fields=[
                'requests_today', 'is_blocked', 'blocked_reason',
                'last_reset_daily', 'updated_at'
            ])

            if should_notify:
                notificacion_model = globals().get('Notificacion')
                if notificacion_model:
                    cutoff = now - timedelta(hours=11, minutes=30)
                    exists = notificacion_model.objects.filter(
                        usuario=self.user,
                        tipo='reset_creditos',
                        creada_en__gte=cutoff,
                    ).exists()
                    if not exists:
                        notificacion_model.objects.create(
                            usuario=self.user,
                            tipo='reset_creditos',
                            titulo='Ya podés generar contenido de nuevo',
                            mensaje='Las APIs free fueron reintentadas/resetadas. Si el proveedor ya renovó la cuota, podés generar contenido otra vez.',
                        )

    def maybe_reset_monthly(self):
        now = timezone.now()
        should_reset = (
            self.last_reset_monthly is None
            or self.last_reset_monthly.year != now.year
            or self.last_reset_monthly.month != now.month
        )
        if should_reset:
            self.requests_this_month = 0
            self.last_reset_monthly = now
            if self.blocked_reason and 'mensual' in self.blocked_reason.lower():
                self.is_blocked = False
                self.blocked_reason = None
            self.save(update_fields=[
                'requests_this_month', 'last_reset_monthly',
                'is_blocked', 'blocked_reason', 'updated_at'
            ])

    def recalcular_limite(self, plan=None):
        """
        Recalcula user_daily_limit = límite base del plan + (extras activos × incremento).
        Se llama al: cambiar de plan, agregar extra, desactivar extra.
        """
        if plan is None:
            plan = self.user.plan_nombre

        # Límite base según plan
        planes_limites = {
            'free':     {'gemini': 1500, 'elevenlabs': 1500, 'uploadpost': 999999},
            'starter':  {'gemini': 3000, 'elevenlabs': 3000, 'uploadpost': 999999},
            'pro':      {'gemini': 7500, 'elevenlabs': 7500, 'uploadpost': 999999},
            'scale':    {'gemini': 15000,'elevenlabs': 15000,'uploadpost': 999999},
            'business': {'gemini': 30000,'elevenlabs': 30000,'uploadpost': 999999},
        }
        planes_limites_mensuales = {
            'free':     {'uploadpost': 10},
            'starter':  {'uploadpost': 10},
            'pro':      {'uploadpost': None},
            'scale':    {'uploadpost': None},
            'business': {'uploadpost': None},
        }
        servicio_nombre = self.servicio.nombre
        base = planes_limites.get(plan, {}).get(servicio_nombre, 1500)
        # LeadBook limita auto-posting por mes; la API/proveedor mantiene sus propios hard caps diarios.

        # Extras activos
        extras = UserAPIAssignment.objects.filter(
            user=self.user,
            servicio=self.servicio,
            is_primary=False,
            activo=True
        ).count()

        incremento = self.servicio.extra_increment
        if servicio_nombre == 'uploadpost' and incremento == 1500:
            incremento = 10
        nuevo_limite = base + (extras * incremento)
        if self.user_daily_limit != nuevo_limite:
            self.user_daily_limit = nuevo_limite
            self.save(update_fields=['user_daily_limit', 'updated_at'])

        monthly_base = planes_limites_mensuales.get(plan, {}).get(servicio_nombre)
        nuevo_limite_mensual = None if monthly_base is None else monthly_base + (extras * incremento)
        if self.user_monthly_limit != nuevo_limite_mensual:
            self.user_monthly_limit = nuevo_limite_mensual
            self.save(update_fields=['user_monthly_limit', 'updated_at'])

    def __str__(self):
        return f"{self.user.email} — {self.servicio.nombre}: {self.requests_today}/{self.user_daily_limit}"

    class Meta:
        unique_together = ('user', 'servicio')
        indexes = [models.Index(fields=['user', 'servicio'])]


# ══════════════════════════════════════════════════════════════════════════════
# PAGOS Y COMPLIANCE
# ══════════════════════════════════════════════════════════════════════════════

class Pago(models.Model):
    """
    Registro INMUTABLE de cada pago.
    SET_NULL en user: si el usuario se borra, el pago queda pero no se pierde.
    mp_payment_id es UNIQUE: garantiza idempotencia (webhook repetido no duplica).
    """
    TIPOS = [
        ('plan_starter',       'Plan Starter'),
        ('plan_pro',           'Plan Pro'),
        ('plan_scale',         'Plan Scale'),
        ('plan_business',      'Plan Business'),
        ('extra_gemini',       'API Extra Gemini'),
        ('extra_elevenlabs',   'API Extra ElevenLabs'),
        ('extra_uploadpost',   'API Extra UploadPost'),
        ('extra_pack_completo','Pack Completo APIs'),
    ]
    STATUS = [
        ('pending',  'Pendiente'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
        ('refunded', 'Reembolsado'),
    ]

    user               = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, related_name='pagos')
    tipo               = models.CharField(max_length=50, choices=TIPOS)
    mp_payment_id      = models.CharField(max_length=100, unique=True)  # Idempotencia garantizada
    mp_status          = models.CharField(max_length=30, choices=STATUS, default='pending')
    monto              = models.DecimalField(max_digits=12, decimal_places=2)
    moneda             = models.CharField(max_length=10, default='ARS')
    external_reference = models.CharField(max_length=255, null=True, blank=True)
    datos_mp           = models.JSONField(default=dict)  # Payload completo de MP para auditoría
    creado_en          = models.DateTimeField(auto_now_add=True)
    procesado_en       = models.DateTimeField(null=True, blank=True)

    def __str__(self): return f"Pago {self.mp_payment_id} — {self.tipo} — {self.mp_status}"

    class Meta:
        indexes = [
            models.Index(fields=['mp_payment_id']),
            models.Index(fields=['user', 'creado_en']),
        ]


class Comprobante(models.Model):
    """Comprobante fiscal. Compliance Argentina — registros contables 10 años."""
    pago      = models.OneToOneField(Pago, on_delete=models.PROTECT, related_name='comprobante')
    numero    = models.CharField(max_length=50, unique=True)
    tipo      = models.CharField(max_length=20, default='recibo')
    datos     = models.JSONField(default=dict)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Comprobante {self.numero}"


class WebhookLog(models.Model):
    """
    Log de cada webhook recibido.
    FLUJO: guardar primero → procesar después.
    Si el procesamiento falla, status='error' y se puede reprocesar manualmente.
    Evita pérdida de pagos por errores en el processing.
    """
    STATUS = [
        ('received',  'Recibido'),
        ('processed', 'Procesado'),
        ('error',     'Error'),
        ('ignored',   'Ignorado'),
        ('duplicate', 'Duplicado'),
    ]

    fuente       = models.CharField(max_length=50, default='mercadopago')
    event_id     = models.CharField(max_length=100, null=True, blank=True)
    event_type   = models.CharField(max_length=100, null=True, blank=True)
    payload      = models.JSONField(default=dict)
    status       = models.CharField(max_length=20, choices=STATUS, default='received')
    error        = models.TextField(null=True, blank=True)
    recibido_en  = models.DateTimeField(auto_now_add=True)
    procesado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['fuente', 'event_id']),
            models.Index(fields=['status']),
        ]


# ══════════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN
# ══════════════════════════════════════════════════════════════════════════════

class OTPCode(models.Model):
    """
    Códigos OTP para registro y recuperación.
    Se limpian automáticamente con tarea Celery diaria (no crecen indefinido).
    """
    email      = models.EmailField()
    code_hash  = models.CharField(max_length=64)
    creado_en  = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts   = models.IntegerField(default=0)
    verified   = models.BooleanField(default=False)
    tipo       = models.CharField(max_length=20, default='registro')

    @staticmethod
    def hash_code(code):
        import hashlib
        return hashlib.sha256(code.encode()).hexdigest()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_valid(self, code):
        return (
            not self.verified and
            not self.is_expired() and
            self.attempts < 5 and
            self.code_hash == self.hash_code(code)
        )

    class Meta:
        ordering = ['-creado_en']
        indexes = [models.Index(fields=['email', 'tipo', 'verified'])]


# ══════════════════════════════════════════════════════════════════════════════
# SEGURIDAD Y MODERACIÓN
# ══════════════════════════════════════════════════════════════════════════════

class UserBanRecord(models.Model):
    user      = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='bans')
    banned_at = models.DateTimeField(auto_now_add=True)
    banned_by = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, related_name='banned_users')
    reason    = models.TextField()
    is_active = models.BooleanField(default=True)


class BannedEmail(models.Model):
    email     = models.EmailField(unique=True)
    banned_at = models.DateTimeField(auto_now_add=True)
    reason    = models.TextField(blank=True, null=True)


class BannedIP(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    banned_at  = models.DateTimeField(auto_now_add=True)
    reason     = models.TextField(blank=True, null=True)


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICACIONES Y ALERTAS
# ══════════════════════════════════════════════════════════════════════════════

class Notificacion(models.Model):
    TIPOS = [
        ('quota_agotada',       'Cuota agotada'),
        ('quota_80',            'Cuota al 80%'),
        ('contenido_generado',  'Contenido generado'),
        ('reset_creditos',      'Reset de créditos'),
        ('pago_aprobado',       'Pago aprobado'),
        ('api_extra_asignada',  'API extra asignada'),
        ('info',                'Información'),
    ]
    usuario   = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='notificaciones')
    tipo      = models.CharField(max_length=30, choices=TIPOS, default='info')
    titulo    = models.CharField(max_length=200)
    mensaje   = models.TextField()
    leida     = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creada_en']
        indexes = [models.Index(fields=['usuario', 'leida'])]


class AdminAlert(models.Model):
    TIPOS = [
        ('quota_warning',   'Quota Warning'),
        ('api_dead',        'API Muerta'),
        ('pool_low',        'Pool bajo — menos de 3 disponibles'),
        ('user_abuse',      'Abuso de usuario'),
        ('high_error_rate', 'Alta tasa de errores'),
        ('webhook_error',   'Error en Webhook'),
        ('assign_failed',   'Fallo en asignación de APIs'),
    ]
    SEVERIDAD = [('info','Info'),('warning','Warning'),('critical','Critical')]

    tipo            = models.CharField(max_length=20, choices=TIPOS)
    severidad       = models.CharField(max_length=10, choices=SEVERIDAD, default='info')
    titulo          = models.CharField(max_length=255)
    mensaje         = models.TextField()
    related_api_key = models.ForeignKey(APIKey, on_delete=models.SET_NULL, null=True, blank=True)
    related_user    = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True)
    is_read         = models.BooleanField(default=False)
    creado_en       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']
        indexes  = [models.Index(fields=['is_read', 'severidad'])]


class AdminLog(models.Model):
    """
    Audit trail de todas las acciones del admin.
    Quién hizo qué, cuándo, sobre qué objeto, con qué datos antes/después.
    """
    admin       = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, related_name='acciones_admin')
    accion      = models.CharField(max_length=100)     # 'add_extra_api', 'ban_user', 'change_plan'
    objeto_tipo = models.CharField(max_length=50)      # 'Agent', 'APIKey', 'UserAPIQuota'
    objeto_id   = models.IntegerField(null=True, blank=True)
    detalle     = models.JSONField(default=dict)        # {'antes': {...}, 'despues': {...}}
    ip          = models.GenericIPAddressField(null=True, blank=True)
    creado_en   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']
        indexes  = [models.Index(fields=['admin', 'creado_en'])]


# ══════════════════════════════════════════════════════════════════════════════
# LOGS DE USO (con archivado)
# ══════════════════════════════════════════════════════════════════════════════

class UsageLog(models.Model):
    """
    Log de uso de features.
    Campo archivado=True para cleanup periódico — no crece infinito.
    """
    TIPOS = [
        ('property', 'Listado'),
        ('ai', 'IA / Guion'),
        ('image', 'Imagen'),
        ('video', 'Video'),
        ('pdf', 'PDF'),
    ]

    agent     = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='usage_logs')
    tipo      = models.CharField(max_length=10, choices=TIPOS)
    fecha     = models.DateTimeField(auto_now_add=True)
    archivado = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['agent', 'tipo', 'fecha']),
            models.Index(fields=['archivado', 'fecha']),
        ]


class APIRequestLog(models.Model):
    """
    Log detallado de cada llamada a una API externa.
    Campo archivado para cleanup — retención 90 días por defecto.
    """
    api_key       = models.ForeignKey(APIKey, on_delete=models.CASCADE, related_name='logs')
    user          = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='api_logs')
    servicio      = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name='logs')
    endpoint      = models.CharField(max_length=255)
    method        = models.CharField(max_length=10, default='POST')
    status_code   = models.IntegerField(null=True, blank=True)
    success       = models.BooleanField(default=False)
    response_time_ms = models.IntegerField(default=0)
    tokens_used   = models.IntegerField(null=True, blank=True)
    cost_estimate = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    creado_en     = models.DateTimeField(auto_now_add=True, db_index=True)
    archivado     = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'creado_en']),
            models.Index(fields=['api_key', 'creado_en']),
            models.Index(fields=['archivado', 'creado_en']),
        ]


class SocialPublicationLog(models.Model):
    """
    Registro persistente de cada intento de publicacion social.
    UserAPIQuota se sincroniza desde esta tabla para UploadPost/Gestor de Redes.
    """
    PROVIDERS = [
        ('uploadpost', 'UploadPost'),
        ('meta', 'Meta Graph'),
    ]
    STATUSES = [
        ('queued', 'En cola'),
        ('completed', 'Completada'),
        ('failed', 'Fallida'),
        ('unknown', 'Desconocida'),
    ]

    user = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='social_publication_logs')
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, null=True, blank=True, related_name='social_publication_logs')
    provider = models.CharField(max_length=30, choices=PROVIDERS, default='uploadpost')
    platform = models.CharField(max_length=50, default='instagram')
    media_type = models.CharField(max_length=30, default='unknown')
    request_id = models.CharField(max_length=128, blank=True, db_index=True)
    job_id = models.CharField(max_length=128, blank=True, db_index=True)
    batch_id = models.CharField(max_length=64, blank=True, db_index=True)
    success = models.BooleanField(default=False)
    counted = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=STATUSES, default='unknown')
    caption = models.TextField(blank=True)
    media_count = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    response = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.provider}/{self.media_type} - {self.status}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'provider', 'request_id'], name='api_social_unique_request'),
        ]
        indexes = [
            models.Index(fields=['user', 'creado_en'], name='api_social_user_created_idx'),
            models.Index(fields=['user', 'success', 'counted', 'creado_en'], name='api_social_user_count_idx'),
            models.Index(fields=['provider', 'platform'], name='api_social_provider_idx'),
            models.Index(fields=['batch_id', 'creado_en'], name='api_social_batch_idx'),
        ]


# ══════════════════════════════════════════════════════════════════════════════
# SISTEMA / CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

class ConfiguracionSistema(models.Model):
    clave         = models.CharField(max_length=100, unique=True)
    valor         = models.TextField(blank=True, null=True)
    datos         = models.JSONField(default=dict, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self): return self.clave


class TerminosCondiciones(models.Model):
    titulo             = models.CharField(max_length=255, default="Términos y Condiciones de Uso")
    contenido          = models.TextField()
    version            = models.CharField(max_length=10, default="1.0")
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    activo             = models.BooleanField(default=True)

    class Meta: ordering = ['-fecha_actualizacion']


class PoliticaPrivacidad(models.Model):
    titulo             = models.CharField(max_length=255, default="Política de Privacidad")
    contenido          = models.TextField()
    version            = models.CharField(max_length=10, default="1.0")
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    activo             = models.BooleanField(default=True)

    class Meta: ordering = ['-fecha_actualizacion']


class AmenidadPreset(models.Model):
    agente    = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='amenidad_presets')
    nombre    = models.CharField(max_length=100)
    creado    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        unique_together = ['agente', 'nombre']


class UserFieldPreset(models.Model):
    user = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='field_presets')
    field = models.CharField(max_length=60)
    value = models.CharField(max_length=255)
    label = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    usage_count = models.PositiveIntegerField(default=1)
    last_used_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['field', '-usage_count', '-last_used_at']
        unique_together = ['user', 'field', 'value']
        indexes = [
            models.Index(fields=['user', 'field', '-usage_count']),
            models.Index(fields=['user', 'last_used_at']),
        ]


# ══════════════════════════════════════════════════════════════════════════════
# MEDIA / AUDIO
# ══════════════════════════════════════════════════════════════════════════════

class VideoMusic(models.Model):
    nombre            = models.CharField(max_length=100)
    cloudinary_url    = models.URLField(max_length=500, null=True, blank=True)
    duracion_segundos = models.FloatField(default=0)
    activo            = models.BooleanField(default=True)
    creado_en         = models.DateTimeField(auto_now_add=True)


class VideoSFX(models.Model):
    TIPOS = [('swoosh','Swoosh'),('impact','Impact'),('camera','Camera'),('other','Other')]
    nombre         = models.CharField(max_length=100)
    tipo           = models.CharField(max_length=20, choices=TIPOS, default='other')
    cloudinary_url = models.URLField(max_length=500, null=True, blank=True)
    activo         = models.BooleanField(default=True)
    creado_en      = models.DateTimeField(auto_now_add=True)


# ══════════════════════════════════════════════════════════════════════════════
# SEÑALES (SIGNALS)
# ══════════════════════════════════════════════════════════════════════════════

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender=Agent)
def setup_nuevo_usuario(sender, instance, created, **kwargs):
    """
    Al crear un usuario: asignar APIs + crear quotas.
    TODO dentro de transaction.atomic() — si falla cualquier paso, se revierte todo.
    Si falla, el admin ve una AdminAlert crítica y puede reparar manualmente.
    """
    if created and instance.is_active and not instance.eliminado_en:
        from api.services.pool_service import assign_apis_to_agent
        try:
            with transaction.atomic():
                assign_apis_to_agent(instance)
        except Exception as e:
            AdminAlert.objects.create(
                tipo='assign_failed',
                severidad='critical',
                titulo=f'Fallo asignación de APIs — {instance.email}',
                mensaje=f'Usuario creado sin APIs: {str(e)}',
                related_user=instance,
            )


@receiver(post_delete, sender=UserAPIAssignment)
def liberar_key_al_desasignar(sender, instance, **kwargs):
    """
    Al eliminar una asignación, la clave vuelve al pool.
    Evita claves zombi (keys asignadas a usuarios que ya no existen).
    """
    try:
        key = instance.apikey
        otras_activas = UserAPIAssignment.objects.filter(apikey=key, activo=True).exists()
        if not otras_activas:
            key.status = 'available'
            key.save(update_fields=['status', 'updated_at'])
    except Exception:
        pass  # No romper si la key ya no existe


@receiver(post_save, sender=Agent)
def recalcular_quotas_al_cambiar_plan(sender, instance, created, **kwargs):
    """
    Al cambiar de plan, recalcular los límites de todas las quotas del usuario.
    Evita que un usuario que hizo downgrade mantenga límites del plan anterior.
    """
    if not created:
        for quota in instance.api_quotas.all():
            quota.recalcular_limite(plan=instance.plan_nombre)
        if not instance.is_active or instance.eliminado_en:
            return
        try:
            from api.services.pool_service import assign_apis_to_agent
            assign_apis_to_agent(instance)
        except Exception as e:
            AdminAlert.objects.create(
                tipo='assign_failed',
                severidad='warning',
                titulo=f'Fallo reasignación por plan — {instance.email}',
                mensaje=f'No se pudieron completar APIs del plan {instance.plan_nombre}: {str(e)}',
                related_user=instance,
            )
