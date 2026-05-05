import io
import logging
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
