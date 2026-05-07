import io
import logging
import os
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

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
        try:
            # networkidle es clave para asegurar que se carguen imágenes y fuentes antes de imprimir
            page.set_content(html_content, wait_until="networkidle", timeout=30000)
            # Asegurar estado idle por si acaso set_content no fue suficiente
            page.wait_for_load_state('networkidle', timeout=30000)
        except PlaywrightTimeoutError:
            logger.warning("[Render Engine] Timeout esperando networkidle para PDF, procediendo de todas formas.")
        except Exception as e:
            logger.error(f"[Render Engine] Error cargando contenido para PDF: {e}")
            
        # 3 segundos extra para asegurar renderizado completo de fuentes de Google y animaciones iniciales
        page.wait_for_timeout(3000) 
        
        pdf_bytes = page.pdf(
            format="A4", 
            print_background=True,
            margin={'top': '0mm', 'right': '0mm', 'bottom': '0mm', 'left': '0mm'}
        )
        
        size_bytes = len(pdf_bytes)
        logger.info(f"[Render Engine] PDF generado exitosamente. Tamaño: {size_bytes} bytes")
        
        if size_bytes < 10000:
            logger.warning(f"[Render Engine] WARNING: El PDF generado es sospechosamente pequeño ({size_bytes} bytes). Podría estar en blanco.")
            
        browser.close()
        
    return pdf_bytes
