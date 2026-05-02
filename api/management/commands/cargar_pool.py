from django.core.management.base import BaseCommand
from api.models import APIKey

class Command(BaseCommand):
    help = 'Carga el pool inicial de cuentas API para usuarios free'

    def handle(self, *args, **kwargs):
        cuentas = [
            # Cuenta 1
            {'servicio': 'gemini', 'api_key': 'AIzaSyATKH8c5rfsROmGQoSxzIVlDjFs9l1a-mI'},
            {'servicio': 'elevenlabs', 'api_key': 'sk_b17c4a7ffde16ed09531ca7edfdffff5ae3906d79c59b073'},
            {'servicio': 'uploadpost', 'api_key': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6Im1hdGlhc2xsYW5vczE0MkBnbWFpbC5jb20iLCJleHAiOjQ5Mjk2MzMwMTcsImp0aSI6IjgyNWU1YzVmLTIyMWMtNDI4ZC05OTJmLTFhNmU3NTFkNTRkNCJ9._bjLsZTdorhVoJpx99-EPTyg0hWP753jr3D4-QhUSK0'},
            # Cuenta 2
            {'servicio': 'gemini', 'api_key': 'AIzaSyASP2LSTUZdbJJMQygtXTAka6HJ8AYIjT4'},
            {'servicio': 'elevenlabs', 'api_key': 'sk_b614c723ab512272a0502351ac0506d87539a1bba9c50f4f'},
            {'servicio': 'uploadpost', 'api_key': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImNoYXJseXNhbm1hcnRpbjIwQGdtYWlsLmNvbSIsImV4cCI6NDkyOTYzMzIwOSwianRpIjoiNDQ0NDJiMmYtNjY3ZS00NmZjLWE3ODktNWNjZjFjN2RlZmI5In0.R2-bGaZT9hEAVxSOfQAfaZRtZFst7SPa21o3-x5tNyM'},
        ]
        for c in cuentas:
            obj, created = APIKey.objects.get_or_create(
                servicio=c['servicio'],
                api_key=c['api_key']
            )
            estado = 'creada' if created else 'ya existía'
            self.stdout.write(f"  [{estado}] {c['servicio']}")
        self.stdout.write(self.style.SUCCESS('Pool cargado: 6 cuentas listas'))
