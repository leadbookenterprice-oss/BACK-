from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Property, PropertyImage, GeneratedAsset, AmenidadPreset,
    Listado, APIKey, APIBundle, APIBundleAssignment,
    Agent, VideoMusic, VideoSFX, APIRequestLog, UserAPIQuota, AdminAlert
)


# ─── Agent ──────────────────────────────────────────────────────────────────
@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('email', 'nombre', 'plan_nombre', 'plan_activo', 'fecha_registro', 'bundle_asignado')
    list_filter = ('plan_nombre', 'plan_activo', 'is_active')
    search_fields = ('email', 'nombre')
    readonly_fields = ('fecha_registro',)

    def bundle_asignado(self, obj):
        try:
            asig = obj.api_bundle_assignment
            if asig and asig.activo:
                return format_html('<span style="color:green;">✔ {}</span>', asig.bundle.nombre)
            return format_html('<span style="color:gray;">Sin bundle</span>')
        except Exception:
            return format_html('<span style="color:gray;">Sin bundle</span>')
    bundle_asignado.short_description = 'Bundle Activo'


# ─── APIKey ──────────────────────────────────────────────────────────────────
@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('label_display', 'servicio', 'empresa', 'status_badge', 'requests_today',
                    'total_requests', 'error_count', 'last_used_at')
    list_filter = ('servicio', 'status')
    search_fields = ('label', 'empresa', 'api_key')
    readonly_fields = ('created_at', 'updated_at', 'requests_today', 'requests_this_month',
                       'total_requests', 'last_used_at', 'error_count')
    fieldsets = (
        ('Identificación', {
            'fields': ('servicio', 'label', 'empresa', 'api_key', 'notes')
        }),
        ('Estado', {
            'fields': ('status', 'assigned_to', 'assigned_at')
        }),
        ('Métricas', {
            'fields': ('daily_limit', 'monthly_limit', 'requests_today',
                       'requests_this_month', 'total_requests', 'error_count',
                       'last_used_at', 'last_health_check', 'last_health_status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def label_display(self, obj):
        return obj.label or (obj.api_key[:14] + '...')
    label_display.short_description = 'Nombre / Key'

    def status_badge(self, obj):
        colors = {
            'available': '#22c55e',
            'in_bundle': '#3b82f6',
            'assigned': '#f59e0b',
            'exhausted': '#ef4444',
            'dead': '#6b7280',
            'disabled': '#9ca3af',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Estado'


# ─── APIBundle ───────────────────────────────────────────────────────────────
@admin.register(APIBundle)
class APIBundleAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'status_badge', 'completeness', 'usuarios_asignados',
                    'gemini_label', 'elevenlabs_label', 'uploadpost_label', 'created_at')
    list_filter = ('status',)
    search_fields = ('nombre', 'notas')
    autocomplete_fields = ['key_gemini', 'key_elevenlabs', 'key_uploadpost']
    readonly_fields = ('created_at', 'updated_at', 'usuarios_asignados')
    fieldsets = (
        ('Identificación', {
            'fields': ('nombre', 'status', 'notas')
        }),
        ('Keys del Bundle', {
            'description': 'Asigná una key de cada servicio. Solo las keys en estado "Disponible" deberían usarse.',
            'fields': ('key_gemini', 'key_elevenlabs', 'key_uploadpost')
        }),
        ('Info', {
            'fields': ('usuarios_asignados', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {'available': '#22c55e', 'assigned': '#3b82f6', 'retired': '#6b7280'}
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Estado'

    def completeness(self, obj):
        filled = sum([bool(obj.key_gemini_id), bool(obj.key_elevenlabs_id), bool(obj.key_uploadpost_id)])
        color = '#22c55e' if filled == 3 else ('#f59e0b' if filled > 0 else '#ef4444')
        return format_html(
            '<span style="color:{};font-weight:bold;">{}/3 keys</span>', color, filled
        )
    completeness.short_description = 'Completitud'

    def usuarios_asignados(self, obj):
        count = obj.assignments.filter(activo=True).count()
        return count
    usuarios_asignados.short_description = 'Usuarios Activos'

    def gemini_label(self, obj):
        if obj.key_gemini:
            return obj.key_gemini.label or '✔'
        return format_html('<span style="color:#ef4444;">✗ Sin key</span>')
    gemini_label.short_description = 'Gemini'

    def elevenlabs_label(self, obj):
        if obj.key_elevenlabs:
            return obj.key_elevenlabs.label or '✔'
        return format_html('<span style="color:#ef4444;">✗ Sin key</span>')
    elevenlabs_label.short_description = 'ElevenLabs'

    def uploadpost_label(self, obj):
        if obj.key_uploadpost:
            return obj.key_uploadpost.label or '✔'
        return format_html('<span style="color:#ef4444;">✗ Sin key</span>')
    uploadpost_label.short_description = 'UploadPost'


# ─── APIBundleAssignment ─────────────────────────────────────────────────────
@admin.register(APIBundleAssignment)
class APIBundleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'bundle', 'activo', 'asignado_en', 'liberado_en')
    list_filter = ('activo',)
    search_fields = ('usuario__email', 'bundle__nombre')
    readonly_fields = ('asignado_en',)
    raw_id_fields = ('usuario', 'bundle')

    actions = ['liberar_bundles']

    def liberar_bundles(self, request, queryset):
        for asig in queryset.filter(activo=True):
            asig.activo = False
            asig.liberado_en = timezone.now()
            asig.bundle.status = 'available'
            asig.bundle.save()
            asig.save()
        self.message_user(request, f'{queryset.count()} bundle(s) liberados.')
    liberar_bundles.short_description = 'Liberar bundles seleccionados'


# ─── Modelos de sonido ───────────────────────────────────────────────────────
@admin.register(VideoMusic)
class VideoMusicAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'duracion_segundos', 'activo', 'creado_en')
    list_filter = ('activo',)

@admin.register(VideoSFX)
class VideoSFXAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo', 'creado_en')
    list_filter = ('tipo', 'activo')


# ─── Resto de modelos ────────────────────────────────────────────────────────
admin.site.register(Property)
admin.site.register(PropertyImage)
admin.site.register(GeneratedAsset)
admin.site.register(AmenidadPreset)
admin.site.register(Listado)
admin.site.register(APIRequestLog)
admin.site.register(UserAPIQuota)
admin.site.register(AdminAlert)
