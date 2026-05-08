from django.conf import settings

def crear_notificacion(usuario, tipo, titulo, mensaje):
    from .models import Notificacion
    Notificacion.objects.create(
        usuario=usuario,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje
    )
