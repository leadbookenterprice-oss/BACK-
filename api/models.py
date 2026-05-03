from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

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

class Agent(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=255)
    telefono = models.CharField(max_length=50, null=True, blank=True)
    agencia = models.CharField(max_length=255, null=True, blank=True)
    logo_url = models.TextField(null=True, blank=True)
    nombre_inmobiliaria = models.CharField(max_length=255, null=True, blank=True)
    meta_access_token = models.TextField(null=True, blank=True)
    meta_instagram_account_id = models.CharField(max_length=100, null=True, blank=True)
    nicho = models.CharField(max_length=100, null=True, blank=True)
    pais = models.CharField(max_length=100, null=True, blank=True)
    agentes_asociados = models.JSONField(default=list)
    plan_nombre = models.CharField(
        max_length=20,
        choices=[('free','Free'),('starter','Starter'),
                 ('pro','Pro'),('scale','Scale'),('business','Business')],
        default='free'
    )
    plan_activo = models.BooleanField(default=True)
    mp_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    mp_customer_id = models.CharField(max_length=100, blank=True, null=True)
    plan_seleccionado = models.BooleanField(default=False)
    plan = models.CharField(max_length=20, default='free')
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    eliminado_en = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = AgentManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre']

    def __str__(self):
        return self.email

class Property(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    address = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class PropertyImage(models.Model):
    property = models.ForeignKey(Property, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='properties/')
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.property.title}"

class GeneratedAsset(models.Model):
    ASSET_TYPES = [
        ('PDF', 'PDF Brochure'),
        ('VIDEO', 'Marketing Video'),
        ('EMAIL', 'Email Template'),
        ('SOCIAL', 'Social Media Image'),
    ]

    property = models.ForeignKey(Property, related_name='assets', on_delete=models.CASCADE)
    asset_type = models.CharField(max_length=10, choices=ASSET_TYPES)
    file = models.FileField(upload_to='assets/', null=True, blank=True)
    status = models.CharField(max_length=50, default='PENDING') # PENDING, PROCESSING, COMPLETED, FAILED
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_asset_type_display()} for {self.property.title}"

class Listado(models.Model):
    agente = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='listados')
    titulo = models.CharField(max_length=255)
    tipo_propiedad = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=100)
    precio = models.CharField(max_length=50)
    datos = models.JSONField(default=dict)
    video_url = models.URLField(max_length=500, null=True, blank=True)
    video_status = models.CharField(max_length=50, default='none')
    creado_en = models.DateTimeField(auto_now_add=True)
    videos_creados = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-creado_en']

    def __str__(self):
        return f"{self.titulo} - {self.agente.email}"

class Plan(models.Model):
    PLAN_CHOICES = [('starter','Starter'),('pro','Pro'),('premium','Premium')]
    nombre = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    precio_usd = models.DecimalField(max_digits=6, decimal_places=2)
    properties_per_month = models.IntegerField(default=20)
    ai_generations = models.IntegerField(default=50)
    image_generations = models.IntegerField(default=20)
    video_generations = models.IntegerField(default=0)
    auto_posting = models.BooleanField(default=False)
    voice_ai = models.BooleanField(default=False)
    branding = models.BooleanField(default=False)
    priority_support = models.BooleanField(default=False)
    mp_plan_id = models.CharField(max_length=100, null=True, blank=True)
    # Soporte para billing diferenciado mensual/anual
    mp_price_id_mensual = models.CharField(max_length=100, null=True, blank=True)
    mp_price_id_anual = models.CharField(max_length=100, null=True, blank=True)

class Suscripcion(models.Model):
    agente = models.OneToOneField(Agent, on_delete=models.CASCADE, related_name='suscripcion')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    periodo_inicio = models.DateTimeField(auto_now_add=True)
    periodo_fin = models.DateTimeField(null=True, blank=True)
    mp_subscription_id = models.CharField(max_length=100, null=True, blank=True)
    mp_preapproval_id = models.CharField(max_length=100, null=True, blank=True)
    mp_status = models.CharField(max_length=30, default='free')
    properties_used = models.IntegerField(default=0)
    ai_used = models.IntegerField(default=0)
    images_used = models.IntegerField(default=0)
    videos_used = models.IntegerField(default=0)
    extra_credits = models.IntegerField(default=0)
    activa = models.BooleanField(default=True)

import hashlib

class OTPCode(models.Model):
    email = models.EmailField()
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)
    tipo = models.CharField(max_length=20, default='registro') # registro o recuperacion

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def hash_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    def is_expired(self) -> bool:
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def is_valid(self, code: str) -> bool:
        return (
            not self.verified and
            not self.is_expired() and
            self.attempts < 5 and
            self.code_hash == self.hash_code(code)
        )

class TerminosCondiciones(models.Model):
    titulo = models.CharField(max_length=255, default="Términos y Condiciones de Uso")
    contenido = models.TextField()
    version = models.CharField(max_length=10, default="1.0")
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-fecha_actualizacion']
    
    def __str__(self):
        return f"{self.titulo} v{self.version}"

class PoliticaPrivacidad(models.Model):
    titulo = models.CharField(max_length=255, default="Política de Privacidad")
    contenido = models.TextField()
    version = models.CharField(max_length=10, default="1.0")
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-fecha_actualizacion']
    
    def __str__(self):
        return f"{self.titulo} v{self.version}"

class AmenidadPreset(models.Model):
    agente = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='amenidad_presets'
    )
    nombre = models.CharField(max_length=100)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        unique_together = ['agente', 'nombre']

    def __str__(self):
        return f"{self.agente} — {self.nombre}"

class UsageLog(models.Model):
    TIPO_CHOICES = [
        ('ai', 'IA / Guion'),
        ('image', 'Imagen'),
        ('video', 'Video'),
    ]
    agent = models.ForeignKey(
        'Agent',
        on_delete=models.CASCADE,
        related_name='usage_logs'
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['agent', 'tipo', 'fecha']),
        ]

    def __str__(self):
        return f"{self.agent} - {self.tipo} - {self.fecha.strftime('%Y-%m-%d')}"

class APIKey(models.Model):
    SERVICIOS = [
        ('gemini', 'Gemini'),
        ('elevenlabs', 'ElevenLabs'),
        ('uploadpost', 'Upload Post'),
        ('openai', 'OpenAI'),
        ('groq', 'Groq'),
        ('anthropic', 'Anthropic'),
        ('stability', 'Stability AI'),
        ('replicate', 'Replicate'),
        ('other', 'Otro'),
    ]
    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('in_bundle', 'En Bundle'),
        ('assigned', 'Asignada (legacy)'),
        ('exhausted', 'Agotada'),
        ('dead', 'Muerta'),
        ('disabled', 'Deshabilitada'),
    ]
    
    servicio = models.CharField(max_length=20, choices=SERVICIOS)
    api_key = models.TextField()
    label = models.CharField(max_length=100, blank=True, null=True, help_text='Nombre descriptivo interno')
    empresa = models.CharField(max_length=100, blank=True, null=True, help_text='Empresa/cuenta propietaria de la key')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Legacy: asignación directa a un usuario (mantener por compatibilidad)
    assigned_to = models.ForeignKey(
        'Agent', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_keys'
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    
    daily_limit = models.IntegerField(default=1500)
    monthly_limit = models.IntegerField(null=True, blank=True)
    requests_today = models.IntegerField(default=0)
    requests_this_month = models.IntegerField(default=0)
    total_requests = models.IntegerField(default=0)
    
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_health_check = models.DateTimeField(null=True, blank=True)
    last_health_status = models.BooleanField(default=True)
    error_count = models.IntegerField(default=0)
    
    notes = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['assigned_to', 'servicio'], 
                name='unique_service_per_user',
                condition=models.Q(assigned_to__isnull=False)
            )
        ]
        
    def __str__(self):
        label = self.label or self.api_key[:12] + '...'
        return f"[{self.get_servicio_display()}] {label} — {self.get_status_display()}"


class APIBundle(models.Model):
    """
    Un paquete de 3 APIs (gemini + elevenlabs + uploadpost).
    Se asigna como unidad a un usuario Free.
    """
    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('assigned', 'Asignado'),
        ('retired', 'Retirado'),
    ]
    nombre = models.CharField(max_length=100, help_text='Ej: Bundle #1 — Cuenta Google A')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Las 3 keys del bundle (pueden ser null si no está configurado)
    key_gemini = models.OneToOneField(
        APIKey, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bundle_gemini'
    )
    key_elevenlabs = models.OneToOneField(
        APIKey, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bundle_elevenlabs'
    )
    key_uploadpost = models.OneToOneField(
        APIKey, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bundle_uploadpost'
    )
    
    notas = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'API Bundle'
        verbose_name_plural = 'API Bundles'

    def __str__(self):
        return f"{self.nombre} [{self.get_status_display()}]"

    def is_complete(self):
        """Verifica que las 3 keys requeridas estén configuradas."""
        return all([self.key_gemini_id, self.key_elevenlabs_id, self.key_uploadpost_id])

    def get_key_for(self, servicio):
        """Devuelve el valor de la API key para el servicio indicado."""
        mapping = {
            'gemini': self.key_gemini,
            'elevenlabs': self.key_elevenlabs,
            'uploadpost': self.key_uploadpost,
        }
        key_obj = mapping.get(servicio)
        return key_obj.api_key if key_obj else None


class APIBundleAssignment(models.Model):
    """
    Registro de qué bundle fue asignado a qué usuario y cuándo.
    Un usuario solo puede tener un bundle activo a la vez.
    """
    bundle = models.ForeignKey(
        APIBundle,
        on_delete=models.PROTECT,
        related_name='assignments'
    )
    usuario = models.OneToOneField(
        'Agent',
        on_delete=models.CASCADE,
        related_name='api_bundle_assignment'
    )
    asignado_en = models.DateTimeField(auto_now_add=True)
    liberado_en = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Asignación de Bundle'
        verbose_name_plural = 'Asignaciones de Bundle'

    def __str__(self):
        return f"{self.bundle.nombre} → {self.usuario.email} ({'activo' if self.activo else 'liberado'})"

class APIRequestLog(models.Model):
    api_key = models.ForeignKey(APIKey, on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_logs')
    service = models.CharField(max_length=50)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10, default='POST')
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    response_time_ms = models.IntegerField(default=0)
    tokens_used = models.IntegerField(null=True, blank=True)
    characters_used = models.IntegerField(null=True, blank=True)
    cost_estimate = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    request_context = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

class UserAPIQuota(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_quotas')
    service = models.CharField(max_length=50)
    daily_limit = models.IntegerField(default=1500)
    monthly_limit = models.IntegerField(null=True, blank=True)
    requests_today = models.IntegerField(default=0)
    requests_this_month = models.IntegerField(default=0)
    is_blocked = models.BooleanField(default=False)
    blocked_reason = models.CharField(max_length=255, null=True, blank=True)
    last_reset_daily = models.DateTimeField(null=True, blank=True)
    last_reset_monthly = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('user', 'service')

class AdminAlert(models.Model):
    TYPE_CHOICES = [
        ('quota_warning', 'Quota Warning'),
        ('api_dead', 'API Dead'),
        ('user_abuse', 'User Abuse'),
        ('high_error_rate', 'High Error Rate'),
    ]
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_api_key = models.ForeignKey(APIKey, on_delete=models.SET_NULL, null=True, blank=True)
    related_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class UserBanRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bans')
    banned_at = models.DateTimeField(auto_now_add=True)
    banned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='banned_users')
    reason = models.TextField()
    is_active = models.BooleanField(default=True)

class BannedEmail(models.Model):
    """
    Blacklist permanente de emails. 
    Un email baneado aquí no puede volver a registrarse NUNCA.
    Se crea al banear un usuario. NO se crea al eliminar un usuario.
    """
    email = models.EmailField(unique=True)
    banned_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, default='Baneado por el administrador')

    class Meta:
        verbose_name = "Email Baneado Permanentemente"
        verbose_name_plural = "Emails Baneados Permanentemente"

    def __str__(self):
        return self.email

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Agent)
def assign_keys_on_register(sender, instance, created, **kwargs):
    if created and instance.plan_nombre == 'free':
        from api.services.pool_service import APIPoolService
        APIPoolService.assign_keys_to_user(instance)

class VideoMusic(models.Model):
    nombre = models.CharField(max_length=100)
    archivo = models.FileField(upload_to='assets/music/')
    duracion_segundos = models.FloatField(default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class VideoSFX(models.Model):
    TIPOS = [
        ('swoosh', 'Swoosh'),
        ('impact', 'Impact'),
        ('camera', 'Camera'),
        ('other', 'Other'),
    ]
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPOS, default='other')
    archivo = models.FileField(upload_to='assets/sfx/')
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.nombre}"
