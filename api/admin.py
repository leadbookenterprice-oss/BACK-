from django.contrib import admin
from .models import (
    Property, PropertyImage, GeneratedAsset, AmenidadPreset, 
    Listado, APIKey, Agent, VideoMusic, VideoSFX, APIRequestLog, UserAPIQuota
)

admin.site.register(Agent)
admin.site.register(Property)
admin.site.register(PropertyImage)
admin.site.register(GeneratedAsset)
admin.site.register(AmenidadPreset)
admin.site.register(Listado)
admin.site.register(APIKey)
admin.site.register(APIRequestLog)
admin.site.register(UserAPIQuota)
admin.site.register(VideoMusic)
admin.site.register(VideoSFX)
