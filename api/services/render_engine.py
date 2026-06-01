import io
import ipaddress
import logging
import os
import json
import socket
from urllib.parse import urlparse
from django.conf import settings
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


def _render_allowed_hosts():
    configured = getattr(settings, 'RENDER_ALLOWED_HOSTS', '') or ''
    hosts = [h.strip().lower().rstrip('.') for h in str(configured).split(',') if h.strip()]
    if not hosts:
        hosts = list(getattr(settings, 'REMOTE_ASSET_ALLOWED_HOSTS', ['res.cloudinary.com']))
    return set(hosts + ['fonts.googleapis.com', 'fonts.gstatic.com'])


_SAFE_HOSTNAME_CACHE = {}

def _is_safe_render_url(url):
    parsed = urlparse(str(url or '').strip())
    if parsed.scheme in {'about', 'data', 'blob'}:
        return True
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return False
    hostname = parsed.hostname.lower().rstrip('.')
    
    if hostname in _SAFE_HOSTNAME_CACHE:
        return _SAFE_HOSTNAME_CACHE[hostname]
        
    if not any(hostname == host or hostname.endswith(f'.{host}') for host in _render_allowed_hosts()):
        _SAFE_HOSTNAME_CACHE[hostname] = False
        return False
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                _SAFE_HOSTNAME_CACHE[hostname] = False
                return False
        _SAFE_HOSTNAME_CACHE[hostname] = True
        return True
    except Exception:
        _SAFE_HOSTNAME_CACHE[hostname] = False
        return False


def _install_network_guard(page):
    def guard(route):
        if _is_safe_render_url(route.request.url):
            return route.continue_()
        logger.warning('[Render Engine] Bloqueando recurso remoto no permitido: %s', route.request.url)
        return route.abort()
    page.route('**/*', guard)

def render_html_to_image(html_content: str, width: int, height: int) -> io.BytesIO:
    """
    Toma un string HTML y devuelve un objeto BytesIO con el PNG renderizado.
    Utiliza Playwright (Chromium Headless) para interpretar CSS, fuentes y glassmorphism.
    """
    with sync_playwright() as p:
        # Optimizado para entornos de servidor (Railway / Docker)
        browser = p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        _install_network_guard(page)
        
        try:
            # wait_until='networkidle' asegura que se carguen las imágenes remotas y fuentes de Google
            page.set_content(html_content, wait_until="networkidle", timeout=12000)
        except PlaywrightTimeoutError:
            logger.warning("[Render Engine] Timeout esperando networkidle, procediendo con screenshot de todas formas.")
        except Exception as e:
            logger.error(f"[Render Engine] Error cargando contenido: {e}")
            
        # Aseguramos un pequeño delay extra para rendering de tipografías pesadas si networkidle fallara
        page.wait_for_timeout(500)
            
        # Tomar captura exacta del viewport
        screenshot_bytes = page.screenshot(type='png', full_page=False)
        browser.close()
        
    output = io.BytesIO(screenshot_bytes)
    output.seek(0)
    return output

def render_html_to_pdf(html_content: str) -> bytes:
    """
    Toma un string HTML y devuelve los bytes del PDF renderizado en formato A4.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        page = browser.new_page()
        _install_network_guard(page)
        try:
            # networkidle es clave para asegurar que se carguen imágenes y fuentes antes de imprimir
            # Reducido timeout a 12s para set_content (load) y luego wait_for_load_state (networkidle) de 8s
            # para asegurar responder antes de los 30s de Railway
            page.set_content(html_content, wait_until="load", timeout=12000)
            try:
                page.wait_for_load_state('networkidle', timeout=8000)
            except PlaywrightTimeoutError:
                logger.warning("[Render Engine] Timeout esperando networkidle en wait_for_load_state, procediendo.")
        except PlaywrightTimeoutError:
            logger.warning("[Render Engine] Timeout esperando load en set_content para PDF, procediendo de todas formas.")
        except Exception as e:
            logger.error(f"[Render Engine] Error cargando contenido para PDF: {e}")
            
        # 1.5 segundos de delay para asegurar renderizado completo de fuentes de Google
        page.wait_for_timeout(1500) 
        
        pdf_bytes = page.pdf(
            format="A4", 
            print_background=True,
            prefer_css_page_size=True,
            margin={'top': '0mm', 'right': '0mm', 'bottom': '0mm', 'left': '0mm'}
        )
        
        size_bytes = len(pdf_bytes)
        logger.info(f"[Render Engine] PDF generado exitosamente. Tamaño: {size_bytes} bytes")
        
        if size_bytes < 10000:
            logger.warning(f"[Render Engine] WARNING: El PDF generado es sospechosamente pequeño ({size_bytes} bytes). Podría estar en blanco.")
            
        browser.close()
        
    return pdf_bytes
