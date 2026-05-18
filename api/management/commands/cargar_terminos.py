from django.core.management.base import BaseCommand
from api.models import TerminosCondiciones, PoliticaPrivacidad

class Command(BaseCommand):
    help = 'Carga los Términos y Condiciones en la base de datos'

    def handle(self, *args, **options):
        # Elimina versiones anteriores
        TerminosCondiciones.objects.all().delete()
        PoliticaPrivacidad.objects.all().delete()
        
        # Contenido de Términos y Condiciones (COMPLETO)
        contenido_terminos = """LeadBook
Términos y Condiciones de Uso
Plataforma SaaS de Generación de Contenido con Inteligencia Artificial
Versión 1.0 | Última actualización: 2025-01-20
Aplicable a todos los planes: Starter, Pro y Scale

Al registrarse o utilizar la plataforma LeadBook, el Usuario acepta quedar vinculado jurídicamente por estos Términos y Condiciones. Si el Usuario no está de acuerdo con alguno de los términos aquí establecidos, deberá abstenerse de utilizar la plataforma.

1. ACEPTACIÓN DE LOS TÉRMINOS
LeadBook ofrece una plataforma basada en la nube que utiliza inteligencia artificial para la generación de contenido inmobiliario. Al acceder, el usuario reconoce haber leído y comprendido estos términos.

2. USO DE LA PLATAFORMA
El usuario se compromete a utilizar la plataforma de manera legal y ética, no interfiriendo con el funcionamiento técnico ni utilizando el contenido generado para fines ilícitos.

3. PROPIEDAD INTELECTUAL
LeadBook es propietario de la plataforma y su tecnología. El usuario retiene los derechos sobre los datos de entrada, mientras que LeadBook otorga una licencia de uso sobre el contenido generado.

4. LIMITACIÓN DE RESPONSABILIDAD
LeadBook no se hace responsable por decisiones comerciales tomadas basadas en el contenido generado por la IA. El servicio se presta "tal cual".

5. MODIFICACIONES
Nos reservamos el derecho de modificar estos términos en cualquier momento, notificando a los usuarios a través de la plataforma.
"""

        # Contenido de Política de Privacidad
        contenido_privacidad = """LeadBook - Política de Privacidad

En LeadBook nos comprometemos a proteger tu privacidad. Esta Política de Privacidad explica cómo recopilamos, utilizamos, divulgamos y salvaguardamos tu información.

1. INFORMACIÓN QUE RECOPILAMOS
Recopilamos información que proporcionas voluntariamente, información recopilada automáticamente, y información de terceros.

2. CÓMO UTILIZAMOS TU INFORMACIÓN
Utilizamos la información para prestar, mejorar y expandir nuestros servicios, personalizar la experiencia del usuario y cumplir con obligaciones legales.

3. PROTECCIÓN DE DATOS
Implementamos medidas técnicas y organizativas para proteger tus datos personales contra acceso no autorizado, alteración o destrucción.

4. DERECHOS DEL USUARIO
Tienes derecho a acceder, rectificar, cancelar y oponerte al tratamiento de tus datos personales en cualquier momento.

5. CONTACTO
Si tienes preguntas sobre esta Política de Privacidad, contáctanos en privacy@leadbook.io
"""

        # Crear registros en BD
        TerminosCondiciones.objects.create(
            titulo="Términos y Condiciones de Uso",
            contenido=contenido_terminos,
            version="1.0",
            activo=True
        )
        
        PoliticaPrivacidad.objects.create(
            titulo="Política de Privacidad",
            contenido=contenido_privacidad,
            version="1.0",
            activo=True
        )
        
        self.stdout.write(self.style.SUCCESS('✅ Términos y Políticas cargados exitosamente'))
