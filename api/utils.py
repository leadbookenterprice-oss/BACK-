from django.conf import settings


_COMMON_MOJIBAKE_REPLACEMENTS = (
    ('ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡', 'á'),
    ('ÃƒÆ’Ã‚Â¡', 'á'),
    ('ÃƒÂ¡', 'á'),
    ('Ã¡', 'á'),
    ('ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©', 'é'),
    ('ÃƒÆ’Ã‚Â©', 'é'),
    ('ÃƒÂ©', 'é'),
    ('Ã©', 'é'),
    ('ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­', 'í'),
    ('ÃƒÆ’Ã‚Â­', 'í'),
    ('ÃƒÂ­', 'í'),
    ('Ã­', 'í'),
    ('ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³', 'ó'),
    ('ÃƒÆ’Ã‚Â³', 'ó'),
    ('ÃƒÂ³', 'ó'),
    ('Ã³', 'ó'),
    ('ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âº', 'ú'),
    ('ÃƒÆ’Ã‚Âº', 'ú'),
    ('ÃƒÂº', 'ú'),
    ('Ãº', 'ú'),
    ('ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±', 'ñ'),
    ('ÃƒÆ’Ã‚Â±', 'ñ'),
    ('ÃƒÂ±', 'ñ'),
    ('Ã±', 'ñ'),
    ('ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¿', '¿'),
    ('Ãƒâ€šÃ‚Â¿', '¿'),
    ('Ã‚Â¿', '¿'),
    ('ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡', '¡'),
    ('Ãƒâ€šÃ‚Â¡', '¡'),
    ('Ã‚Â¡', '¡'),
    ('ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â·', '·'),
    ('Ãƒâ€šÃ‚Â·', '·'),
    ('Ã‚Â·', '·'),
    ('Â', ''),
)


def repair_mojibake_text(value):
    text = str(value or '')
    if not text:
        return ''

    for broken, fixed in _COMMON_MOJIBAKE_REPLACEMENTS:
        text = text.replace(broken, fixed)

    try:
        from ftfy import fix_text
        for _ in range(4):
            fixed = fix_text(text)
            if fixed == text:
                break
            text = fixed
    except Exception:
        pass

    for broken, fixed in _COMMON_MOJIBAKE_REPLACEMENTS:
        text = text.replace(broken, fixed)
    return text


def crear_notificacion(usuario, tipo, titulo, mensaje):
    from .models import Notificacion
    Notificacion.objects.create(
        usuario=usuario,
        tipo=tipo,
        titulo=repair_mojibake_text(titulo),
        mensaje=repair_mojibake_text(mensaje)
    )
