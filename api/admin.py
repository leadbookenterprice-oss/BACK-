from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Agent, AgentAssociation,
    Plan, Suscripcion,
    Listado,
    Servicio, APIKey, UserAPIAssignment, UserAPIQuota,
    Pago, WebhookLog,
    OTPCode, UserBanRecord, BannedEmail, BannedIP,
    Notificacion, AdminAlert, AdminLog,
    UsageLog, APIRequestLog,
    ConfiguracionSistema, TerminosCondiciones, PoliticaPrivacidad,
    AmenidadPreset, VideoMusic, VideoSFX,
)


# ─── Agent ───────────────────────────────────────────────────────────────────
@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('email', 'nombre', 'plan_nombre', 'plan_activo', 'is_active', 'fecha_registro', 'eliminado_en')
    list_filter = ('plan_nombre', 'plan_activo', 'is_active')
    search_fields = ('email', 'nombre')
    readonly_fields = ('fecha_registro', 'updated_at')


# ─── APIKey ──────────────────────────────────────────────────────────────────
@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('label_display', 'servicio', 'empresa', 'status_badge',
                    'requests_today', 'total_requests', 'error_count', 'last_used_at')
    list_filter = ('servicio', 'status')
    search_fields = ('label', 'empresa', 'api_key')
    readonly_fields = ('creado_en', 'updated_at', 'requests_today',
                       'requests_this_month', 'total_requests', 'last_used_at', 'error_count')

    def label_display(self, obj):
        return obj.label or (obj.api_key[:14] + '...')
    label_display.short_description = 'Nombre / Key'

    def status_badge(self, obj):
        colors = {
            'available': '#22c55e',
            'assigned':  '#3b82f6',
            'exhausted': '#ef4444',
            'dead':      '#6b7280',
            'disabled':  '#9ca3af',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Estado'


# ─── Servicio ─────────────────────────────────────────────────────────────────
@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'default_daily_limit', 'extra_increment')
    list_filter = ('activo',)


# ─── UserAPIAssignment ───────────────────────────────────────────────────────
@admin.register(UserAPIAssignment)
class UserAPIAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'servicio', 'apikey_label', 'is_primary', 'activo', 'assigned_at')
    list_filter = ('servicio', 'is_primary', 'activo')
    search_fields = ('user__email', 'apikey__label')
    raw_id_fields = ('user', 'apikey', 'pago')

    def apikey_label(self, obj):
        return obj.apikey.label or obj.apikey.api_key[:14] + '...'
    apikey_label.short_description = 'API Key'


# ─── UserAPIQuota ─────────────────────────────────────────────────────────────
@admin.register(UserAPIQuota)
class UserAPIQuotaAdmin(admin.ModelAdmin):
    list_display = ('user', 'servicio', 'requests_today', 'user_daily_limit', 'is_blocked', 'updated_at')
    list_filter = ('servicio', 'is_blocked')
    search_fields = ('user__email',)
    raw_id_fields = ('user', 'servicio')


# ─── Pago ─────────────────────────────────────────────────────────────────────
@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('mp_payment_id', 'user', 'tipo', 'mp_status', 'monto', 'moneda', 'creado_en')
    list_filter = ('mp_status', 'tipo')
    search_fields = ('mp_payment_id', 'user__email', 'external_reference')
    readonly_fields = ('creado_en', 'mp_payment_id')


# ─── WebhookLog ───────────────────────────────────────────────────────────────
@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ('fuente', 'event_type', 'event_id', 'status', 'recibido_en', 'procesado_en')
    list_filter = ('fuente', 'status')
    search_fields = ('event_id', 'event_type')
    readonly_fields = ('recibido_en',)


# ─── AdminAlert ───────────────────────────────────────────────────────────────
@admin.register(AdminAlert)
class AdminAlertAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo', 'severidad', 'is_read', 'creado_en')
    list_filter = ('tipo', 'severidad', 'is_read')
    search_fields = ('titulo', 'mensaje')


# ─── AdminLog ─────────────────────────────────────────────────────────────────
@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = ('admin', 'accion', 'objeto_tipo', 'objeto_id', 'creado_en')
    list_filter = ('accion', 'objeto_tipo')
    search_fields = ('admin__email', 'accion')
    readonly_fields = ('creado_en',)


# ─── Audio / Media ────────────────────────────────────────────────────────────
@admin.register(VideoMusic)
class VideoMusicAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'duracion_segundos', 'activo', 'creado_en')
    list_filter = ('activo',)


@admin.register(VideoSFX)
class VideoSFXAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo', 'creado_en')
    list_filter = ('tipo', 'activo')


# ─── Resto ────────────────────────────────────────────────────────────────────
admin.site.register(AgentAssociation)
admin.site.register(Plan)
admin.site.register(Suscripcion)
admin.site.register(Listado)
admin.site.register(OTPCode)
admin.site.register(UserBanRecord)
admin.site.register(BannedEmail)
admin.site.register(BannedIP)
admin.site.register(Notificacion)
admin.site.register(UsageLog)
admin.site.register(APIRequestLog)
admin.site.register(ConfiguracionSistema)
admin.site.register(TerminosCondiciones)
admin.site.register(PoliticaPrivacidad)
admin.site.register(AmenidadPreset)
