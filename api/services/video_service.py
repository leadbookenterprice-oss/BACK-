import subprocess
import os
import json
import logging
import shutil
from django.conf import settings
from decouple import config
from api.models import Listado

import cloudinary
import cloudinary.uploader
import cloudinary.api
from api.ai_services import smart_call, call_elevenlabs_api
from api.services.almacenamiento import AlmacenamientoCloudinary

cloudinary.config( 
  cloud_name = config('CLOUDINARY_CLOUD_NAME', default=''), 
  api_key = config('CLOUDINARY_API_KEY', default=''), 
  api_secret = config('CLOUDINARY_API_SECRET', default='') 
)

def generar_video_listado(listado_id):
    try:
        listado = Listado.objects.get(id=listado_id)
        listado.video_status = 'processing'
        listado.save()
        
        # Paths
        engine_dir = os.path.join(settings.BASE_DIR, 'hyperframes_engine')
        output_filename = f'video_{listado.id}.mp4'
        output_path = os.path.join(settings.MEDIA_ROOT, 'assets', output_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Temp render directory
        render_dir = os.path.join(settings.MEDIA_ROOT, 'temp_render', str(listado.id))
        os.makedirs(render_dir, exist_ok=True)
        
        datos = listado.datos
        
        # Assets logic from DB
        from api.models import VideoMusic, VideoSFX
        
        # MUSIC
        music_id = datos.get('music_id')
        music_obj = None
        if music_id:
            music_obj = VideoMusic.objects.filter(id=music_id, activo=True).first()
        if not music_obj:
            music_obj = VideoMusic.objects.filter(activo=True).order_by('?').first()
        
        music_url = music_obj.archivo.url if music_obj else f"{backend_url}/media/assets/music/fondo.mp3"
        
        # SFX: Swoosh
        sfx_swoosh = VideoSFX.objects.filter(tipo='swoosh', activo=True).order_by('?').first()
        sfx_swoosh_url = sfx_swoosh.archivo.url if sfx_swoosh else f"{backend_url}/media/assets/sfx/EMP - Techno House Samples - Fx Swoosh 1.wav"
        
        # SFX: Impact
        sfx_impact = VideoSFX.objects.filter(tipo='impact', activo=True).order_by('?').first()
        sfx_impact_url = sfx_impact.archivo.url if sfx_impact else f"{backend_url}/media/assets/sfx/CBE_Impact_150_02.wav"
        
        # SFX: Camera
        sfx_camera = VideoSFX.objects.filter(tipo='camera', activo=True).order_by('?').first()
        sfx_camera_url = sfx_camera.archivo.url if sfx_camera else f"{backend_url}/media/assets/sfx/CameraShot.wav"

        escenas = datos.get('escenas', [])

        def _normalize_url(item):
            if isinstance(item, dict):
                if item.get('url'):
                    return str(item.get('url')).strip()
                if item.get('fotoUrl'):
                    return str(item.get('fotoUrl')).strip()
            if isinstance(item, str):
                return item.strip()
            return ''

        fotos_escenas = []
        if isinstance(escenas, list):
            for escena in escenas:
                if not isinstance(escena, dict):
                    continue
                foto_url = _normalize_url(escena.get('fotoUrl'))
                if foto_url:
                    fotos_escenas.append(foto_url)

        fotos_base = []
        for f in datos.get('fotosRecorrido', []) or []:
            u = _normalize_url(f)
            if u:
                fotos_base.append(u)

        portada = _normalize_url(datos.get('portadaUrl'))
        if portada:
            fotos_base.append(portada)

        fotos = fotos_escenas or fotos_base
        fotos = [f for f in fotos if f]
        if not fotos:
            fotos = ["https://via.placeholder.com/1080x1920/111"]

        # --- VOICE OVER GENERATION ---
        audio_filename = f'audio_{listado.id}.mp3'
        audio_path = os.path.join(settings.MEDIA_ROOT, 'assets', audio_filename)
        
        tipo_video = datos.get('tipoVideo', 'reel').lower()
        voz_seleccionada = datos.get('voz', 'femenina').lower()
        tono_seleccionado = datos.get('tono', 'profesional')
        contexto_adicional = datos.get('contextoAdicional', '')
        is_tour = 'tour' in tipo_video
        
        # Parámetros según el estilo
        vo_duration = 45 if is_tour else 15 # fallback initial
        duracion_texto = "entre 45 y 60 segundos. Describí los ambientes con detalle y de forma inmersiva" if is_tour else "unos 15-20 segundos. Sé muy dinámico y enfocado en el hook"
        
        try:
            # SI EL USUARIO EDITÓ EL GUION EN EL PASO 5, USAR ESO Y NO REGENERAR
            if escenas and isinstance(escenas, list) and len(escenas) > 0:
                script_vo = " ".join([str(esc.get('texto', '')).strip() for esc in escenas if isinstance(esc, dict) and str(esc.get('texto', '')).strip()])
            else:
                prompt_vo = f"""Escribí un guion persuasivo para un video sobre esta propiedad.
Tipo: {listado.tipo_propiedad} en {listado.ciudad}
Precio: {listado.precio}
Detalles: {listado.titulo}

El guion debe durar {duracion_texto}.
Tono de voz deseado: {tono_seleccionado}.
Enfoque especial solicitado por el usuario: {contexto_adicional}.

No incluyas preámbulos, solo el texto en español neutro."""
                
                script_vo = smart_call(prompt_vo, agente=listado.agente)
                if not script_vo:
                    script_vo = f"Descubre esta increíble {listado.tipo_propiedad} en {listado.ciudad}. Una oportunidad única por solo {listado.precio}. Contáctanos hoy mismo para más información."

            if script_vo:
                script_vo = script_vo.replace('**', '').replace('"', '').strip()
                audio_bytes = call_elevenlabs_api(script_vo, agente=listado.agente, voz=voz_seleccionada)
                if audio_bytes:
                    with open(audio_path, 'wb') as f_audio:
                        f_audio.write(audio_bytes)
                    
                    # Transcribe for word-level timing using Local Whisper
                    try:
                        import whisper
                        # Load the base model (downloads automatically if not cached)
                        model = whisper.load_model("base")
                        result = model.transcribe(audio_path, word_timestamps=True)
                        
                        words = []
                        for segment in result.get('segments', []):
                            for word_data in segment.get('words', []):
                                words.append({
                                    "word": word_data['word'].strip(),
                                    "start": word_data['start'],
                                    "end": word_data['end']
                                })
                                
                        transcript_path = audio_path.replace('.mp3', '.json')
                        with open(transcript_path, 'w', encoding='utf-8') as f:
                            json.dump(words, f)
                            
                        if words:
                            vo_duration = words[-1]['end'] + 0.5
                    except Exception as e:
                        logging.error(f"Local Whisper transcription failed: {e}")
                        # Fallback to dummy transcript if whisper fails
                        transcript_path = audio_path.replace('.mp3', '.json')
                        words_list = script_vo.split()
                        dummy_transcript = []
                        step = vo_duration / len(words_list) if words_list else 1
                        for i, w in enumerate(words_list):
                            dummy_transcript.append({
                                "word": w,
                                "start": i * step,
                                "end": (i + 1) * step
                            })
                        with open(transcript_path, 'w', encoding='utf-8') as f_dummy:
                            json.dump(dummy_transcript, f_dummy)
        except Exception as e:
            logging.error(f"Voiceover/Transcription failed: {e}")

        # --- VIDEO COMPOSITION LOGIC ---
        scene_duration = 3.8 if is_tour else 1.8
        first_overlap = 0.8
        if len(fotos) <= 1:
            visual_duration = scene_duration + 2
        else:
            visual_duration = (scene_duration + first_overlap) + ((len(fotos) - 1) * scene_duration)

        total_duration = max(vo_duration + 2.0, visual_duration + 1.0)
        total_duration = max(10.0, total_duration)
        cta_start = max(1.5, total_duration - 3.5)
        
        images_html = ""
        ken_burns_js = ""
        sfx_camera_html = ""
        cut_times = []
        
        for i, url in enumerate(fotos):
            if i == 0:
                start = 0.0
                duration = scene_duration + (first_overlap if len(fotos) > 1 else 0.5)
                track_index = 6
            elif i == 1:
                start = scene_duration - first_overlap
                duration = scene_duration
                track_index = 7
            else:
                start = (scene_duration - first_overlap) + ((i - 1) * scene_duration)
                duration = scene_duration
                track_index = 6

            start_str = f"{start:.3f}".rstrip('0').rstrip('.')
            duration_str = f"{duration:.3f}".rstrip('0').rstrip('.')
            images_html += f'<img id="img{i}" class="scene-img clip" data-start="{start_str}" data-duration="{duration_str}" data-track-index="{track_index}" src="{url}" />\n'
            ken_burns_js += f'tl.fromTo("#img{i}", {{ scale: 1.000 }}, {{ scale: 1.03, duration: {duration_str}, ease: "none" }}, {start_str});\n'

            if i > 0:
                sfx_camera_html += f'<audio class="clip" data-start="{start_str}" data-duration="1" data-track-index="2" data-volume="0.65" src="{sfx_camera_url}"></audio>\n'
                cut_times.append(start_str)

        # Build Captions
        captions_html = ""
        words_js = ""
        transcript_path = audio_path.replace('.mp3', '.json')
        if os.path.exists(transcript_path):
            with open(transcript_path, 'r', encoding='utf-8') as f_trans:
                words = json.load(f_trans)
                for i, w in enumerate(words):
                    word_text = str(w['word']).strip().upper()
                    if not word_text:
                        continue
                    extra_class = ""
                    if any(x in word_text for x in ["PESOS", "$", "USD"]): extra_class = "price"
                    elif len(word_text) > 8: extra_class = "gold"

                    captions_html += f'<div id="cg-{i}" class="cap-word"><div class="cap-inner"><span class="cap-text {extra_class}">{word_text}</span></div></div>\n'
                    word_start = max(0.0, float(w["start"]) + 0.5)
                    word_end = max(word_start + 0.04, float(w["end"]) + 0.5)
                    words_js += f'[{i}, {word_start:.3f}, {word_end:.3f}],\n'

        local_audio_name = os.path.basename(audio_path)
        render_audio_path = os.path.join(render_dir, local_audio_name)
        if os.path.exists(audio_path):
            shutil.copy2(audio_path, render_audio_path)

        # --- FILL TEMPLATE ---
        template_path = os.path.join(engine_dir, 'template_index.html')
        with open(template_path, 'r', encoding='utf-8') as f_temp:
            html_content = f_temp.read()
        
        replacements = {
            '{{ duration }}': f"{total_duration:.3f}".rstrip('0').rstrip('.'),
            '{{ images_html }}': images_html,
            '{{ music_url }}': music_url,
            '{{ vo_url }}': f"./{local_audio_name}",
            '{{ vo_duration }}': f"{vo_duration:.3f}".rstrip('0').rstrip('.'),
            '{{ sfx_swoosh_url }}': sfx_swoosh_url,
            '{{ sfx_impact_url }}': sfx_impact_url,
            '{{ cta_start }}': f"{cta_start:.3f}".rstrip('0').rstrip('.'),
            '{{ sfx_camera_html }}': sfx_camera_html,
            '{{ captions_html }}': captions_html,
            '{{ price }}': listado.precio,
            '{{ location }}': f"{listado.ciudad}",
            '{{ ken_burns_js }}': ken_burns_js,
            '{{ cut_times }}': ",".join(cut_times),
            '{{ words_js }}': words_js
        }
        
        for k, v in replacements.items():
            html_content = html_content.replace(k, v)

        # Write final index.html in the temp render directory
        index_path = os.path.join(render_dir, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f_out:
            f_out.write(html_content)

        # --- RENDER ---
        render_cmd = [
            "npx.cmd" if os.name == 'nt' else "npx",
            "hyperframes",
            "render",
            ".", # Render the current (temp) directory
            "--output", output_path,
            "--quality", config('HYPERFRAMES_QUALITY', default='high')
        ]
        
        process = subprocess.run(
            render_cmd,
            cwd=render_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True if os.name == 'nt' else False
        )

        # Cleanup
        try:
            shutil.rmtree(render_dir)
            transcript_path = audio_path.replace('.mp3', '.json')
            if os.path.exists(transcript_path): os.remove(transcript_path)
        except:
            pass

        if process.returncode == 0:
            try:
                video_url = AlmacenamientoCloudinary.guardar_video(
                    output_path,
                    user_id=listado.agente.id,
                    listado_id=listado.id,
                )
                if video_url:
                    listado.video_url = video_url
                else:
                    listado.video_url = f"/media/assets/{output_filename}"
                    
                listado.video_status = 'done'
                listado.save()
            except Exception as e:
                listado.video_url = f"/media/assets/{output_filename}"
                listado.video_status = 'done'
                listado.save()
                logging.error(f"Cloudinary upload failed: {e}")
            
            return True
        else:
            listado.video_status = 'error'
            listado.save()
            logging.error(f"Render failed: {process.stderr}")
            return False

    except Exception as e:
        if 'listado' in locals() and listado:
            listado.video_status = 'error'
            listado.save()
        logging.error(f"Generate video failed: {e}")
        return False
