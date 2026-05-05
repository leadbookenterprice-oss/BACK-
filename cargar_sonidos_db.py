import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import django
from django.core.files import File

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_panel.settings')
django.setup()

from api.models import VideoMusic, VideoSFX

MUSICA_DIR = r"C:\Users\elalc\Desktop\videos marketing\maceta-bobesponja\musica"
SONIDOS_DIR = r"C:\Users\elalc\Desktop\videos marketing\maceta-bobesponja\sonidos"

def load_music():
    fondo_path = os.path.join(MUSICA_DIR, "fondo.mp3")
    if os.path.exists(fondo_path):
        if not VideoMusic.objects.filter(nombre="fondo.mp3").exists():
            print("Cargando música: fondo.mp3...")
            with open(fondo_path, 'rb') as f:
                vm = VideoMusic(nombre="fondo.mp3", duracion_segundos=120)
                vm.archivo.save("fondo.mp3", File(f), save=True)
            print("✔ Música cargada.")
        else:
            print("Música fondo.mp3 ya existe.")

def load_sfx():
    sfx_mapping = {
        "CBE_Impact_150_02.wav": "impact",
        "CHIME_foley_mechanical_clicks_15.wav": "other",
        "CameraShot.wav": "camera",
        "EMP - Techno House Samples - Fx Swoosh 1.wav": "swoosh"
    }

    for filename, tipo in sfx_mapping.items():
        path = os.path.join(SONIDOS_DIR, filename)
        if os.path.exists(path):
            if not VideoSFX.objects.filter(nombre=filename).exists():
                print(f"Cargando SFX: {filename} ({tipo})...")
                with open(path, 'rb') as f:
                    vsfx = VideoSFX(nombre=filename, tipo=tipo)
                    vsfx.archivo.save(filename, File(f), save=True)
                print(f"✔ SFX {filename} cargado.")
            else:
                print(f"SFX {filename} ya existe.")
        else:
            print(f"⚠ Archivo {filename} no encontrado en origen.")

if __name__ == '__main__':
    load_music()
    load_sfx()
    print("¡Listo! DB y archivos multimedia actualizados.")
