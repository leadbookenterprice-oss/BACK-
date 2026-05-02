import io
import base64
import os
from PIL import Image, ImageDraw, ImageFont
import requests

def clean_b64(s):
    if not isinstance(s, str):
        return None
    s = s.strip().replace('\n', '').replace('\r', '')
    if ',' in s and s.startswith('data:'):
        s = s.split(',', 1)[1]
    s += "=" * ((4 - len(s) % 4) % 4)
    try:
        return base64.b64decode(s)
    except Exception as e:
        print("Error decoding base64:", e)
        return None

def get_font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except IOError:
        return ImageFont.load_default()

def draw_text_with_shadow(draw, position, text, font, fill, shadow_color="black"):
    x, y = position
    draw.text((x+2, y+2), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=fill)

def generate_social_image(data, is_story=False, headline=None):
    width = 1080
    height = 1920 if is_story else 1080

    # 1. Base Image - Fondo de contingencia (degradado)
    img = Image.new('RGB', (width, height), color=(15, 20, 35))
    draw_bg = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = max(0, int(25 - 15 * ratio))
        g = max(0, int(30 - 20 * ratio))
        b = max(0, int(55 - 35 * ratio))
        draw_bg.line((0, y, width, y), fill=(r, g, b))

    # 2. Descargar y procesar Portada (Cover Centrada)
    portada_url = data.get('portadaUrl') or data.get('formData', {}).get('portadaUrl', '')
    if portada_url:
        try:
            if portada_url.startswith('data:'):
                img_data = clean_b64(portada_url)
                bg_img = Image.open(io.BytesIO(img_data)).convert('RGB')
            else:
                resp = requests.get(portada_url, timeout=10)
                bg_img = Image.open(io.BytesIO(resp.content)).convert('RGB')
            
            # Crop centrado a width x height
            w, h = bg_img.size
            ratio = max(width/w, height/h)
            new_w, new_h = int(w*ratio), int(h*ratio)
            bg_img = bg_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - width) // 2
            top = (new_h - height) // 2
            bg_img = bg_img.crop((left, top, left+width, top+height))
            img.paste(bg_img, (0,0))
            print(f"[Generator] Fondo cargado desde: {portada_url[:50]}...")
        except Exception as e:
            print(f"[Generator] Fallo al cargar portadaUrl: {e}")

    # 3. Overlay Gradiente (0% arriba, 80% abajo)
    overlay = Image.new('RGBA', (width, height), (0,0,0,0))
    d_overlay = ImageDraw.Draw(overlay)
    for y in range(height):
        # Gradiente oscuro que empieza a notarse desde la mitad
        if y > height // 2:
            alpha = int(((y - height//2) / (height//2)) * 220) # Max 220 alpha
            d_overlay.line((0, y, width, y), fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

    draw = ImageDraw.Draw(img)

    # 4. Badge VENTA/ALQUILER (Top-Right)
    operacion = data.get('operacion', data.get('formData', {}).get('operacion', 'VENTA')).upper()
    badge_font = get_font(40 if is_story else 35)
    bbox = draw.textbbox((0, 0), operacion, font=badge_font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    # Dibujar rectángulo rojo
    rect_x1, rect_y1 = width - bw - 80, 40
    rect_x2, rect_y2 = width - 40, 40 + bh + 30
    draw.rectangle([rect_x1, rect_y1, rect_x2, rect_y2], fill=(220, 20, 60))
    draw.text((rect_x1 + 20, rect_y1 + 10), operacion, font=badge_font, fill="white")

    # 5. Logo Inmobiliaria (Top-Left)
    logo_url = data.get('logoAgenciaUrl', data.get('formData', {}).get('logoAgenciaUrl', ''))
    if logo_url:
        try:
            if logo_url.startswith('data:'):
                l_data = clean_b64(logo_url)
                logo = Image.open(io.BytesIO(l_data)).convert('RGBA')
            else:
                resp = requests.get(logo_url, timeout=5)
                logo = Image.open(io.BytesIO(resp.content)).convert('RGBA')
            
            logo.thumbnail((250, 120))
            img.paste(logo, (40, 40), logo if logo.mode == 'RGBA' else None)
        except Exception as e:
            print(f"[Generator] Fallo al cargar Logo: {e}")

    # 6. Textos (Zon inferior)
    tipo = data.get('tipoPropiedad', 'Propiedad').upper()
    ciudad = data.get('ciudad', 'Ciudad').upper()
    precio = f"{data.get('moneda', 'USD')} {data.get('precio', '')}"
    
    # Características
    form_data = data.get('formData', data)
    stats = []
    if form_data.get('superficieCubierta'): stats.append(f"{form_data['superficieCubierta']}m²")
    elif form_data.get('superficieConstruida'): stats.append(f"{form_data['superficieConstruida']}m²")
    if form_data.get('recamaras'): stats.append(f"{form_data['recamaras']} Hab")
    if form_data.get('banos'): stats.append(f"{form_data['banos']} Baños")
    stats_text = "  |  ".join(stats)

    # Fuentes
    price_f = get_font(90 if is_story else 85)
    loc_f = get_font(50 if is_story else 45)
    stats_f = get_font(40 if is_story else 35)

    # Posiciones
    y_start = height - 120
    if is_story: y_start = height - 200

    # Dibujar de abajo hacia arriba
    # Stats
    draw_text_with_shadow(draw, (60, y_start - 50), stats_text, stats_f, "white")
    # Tipo + Ciudad
    draw_text_with_shadow(draw, (60, y_start - 120), f"{tipo} - {ciudad}", loc_f, "white")
    # Precio
    draw_text_with_shadow(draw, (60, y_start - 240), precio, price_f, "white")

    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output
