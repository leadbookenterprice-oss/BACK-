## Objetivo

Subir la generación de video a nivel publicitario: videos fluidos, legibles, con audio consistente y narrativa adecuada al tipo de propiedad.

## Principios

- Confiabilidad primero: nunca entregar video roto o silencioso.
- Calidad medible: cada mejora debe impactar en métricas.
- Modularidad: guion, voz, captions, visual y QA separados.
- Escalabilidad: plantillas y perfiles reutilizables.

## Fase 1 - Estabilidad y Calidad Base (1-2 semanas)

### Entregables

1. Perfiles de calidad por tipo de video (reel/tour/terreno).
2. Audio siempre presente (voz o fallback + música controlada).
3. Captions legibles y fluidos (chunking por frase).
4. Duración mínima consistente (reel ~20s).
5. Fallbacks robustos sin bloquear render.

### KPI

- % videos generados sin error > 97%
- % videos con audio audible > 95%
- % videos sin frame negro final > 99%

## Fase 2 - Mejora Visual Premium (2-4 semanas)

### Entregables

1. 3-5 templates premium (casa/depto/terreno/lujo/alquiler).
2. Sistema de contraste adaptativo para captions.
3. Ritmo visual adaptativo por cantidad de fotos.
4. Transiciones y motion consistentes por perfil.

### KPI

- Retención 3s +20%
- Feedback positivo visual +30%

## Fase 3 - Audio Pro y Narración Natural (2-3 semanas)

### Entregables

1. Limpieza lingüística de guion (monedas, cifras, abreviaturas).
2. Variantes de voz por tono y tipo de propiedad.
3. Mezcla automática (ducking música bajo voz).
4. Biblioteca curada de música/SFX por perfil.

### KPI

- % quejas de voz robótica -50%
- % videos con VO utilizable > 90%

## Fase 4 - QA Automático y Operación (1-2 semanas)

### Entregables

1. Validaciones automáticas pre-entrega:
   - duración mínima,
   - audio track presente,
   - loudness básico,
   - no blackout largo,
   - captions dentro de safe-area.
2. Score interno de calidad por video.
3. Trazabilidad completa de fallos por etapa.

### KPI

- Reintentos manuales -40%
- Tiempo de soporte por incidente -35%

## Inicio Inmediato (Sprint actual)

1. Consolidar perfiles de calidad en código backend.
2. Unificar parámetros de duración/ritmo/audio bajo perfil.
3. Dejar flags en `.env` para tuning rápido.
4. Medir salida en 3 tipos: casa, depto, terreno.

## Riesgos y mitigación

- Dependencia de APIs TTS inestables: fallback multi-voz + música base.
- Datos de usuario incompletos: guion por tipo con campos opcionales.
- Entornos locales sin assets: fallback local/autogenerado.
