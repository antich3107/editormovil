# Editor v1.0 — editor documental automático local

Editor es un conjunto de herramientas locales para preparar documentales de YouTube en Windows. No requiere servicios de IA de pago. El acceso desde Android queda para una versión posterior.

## Requisitos
- Windows 10/11 y Python 3.10+ en PATH.
- FFmpeg y FFprobe en PATH para renderizar.
- `faster-whisper` opcional para sincronización por voz.

## Inicio del editor de vídeo
1. Extrae el ZIP.
2. Ejecuta `DIAGNOSTICO.bat`.
3. Ejecuta `INICIAR_EDITOR.bat`.
4. El editor de montaje se abre en `http://127.0.0.1:8765`.

## Flujo recomendado
1. Prepara un guion de narración con un párrafo por escena.
2. Indexa tus imágenes y vídeos: `python asistente_editor.py indexar "D:\Documentales\recursos"`.
3. Genera el plan: `python asistente_editor.py planificar "proyectos\forest-city\guion.txt" --index "D:\Documentales\recursos\indice_multimedia.json" --minutes 12`.
4. Abre el revisor visual: `python revisar_plan.py "proyectos\forest-city\plan_escenas.json"`.
5. Abre en el navegador la dirección mostrada por consola (normalmente `http://127.0.0.1:8766`). Revisa las vistas previas, selecciona el recurso correcto en cada escena y pulsa **Guardar selecciones**. Mantén abierta la consola del revisor.
6. Prepara el montaje usando el plan revisado: `python asistente_editor.py preparar-montaje "proyectos\forest-city\plan_escenas.json" --output "proyectos\forest-city\montaje" --audio "D:\Documentales\forest-city.wav"`. Añade `--reuse` si aceptas repetir un recurso en distintas escenas.
7. Abre la carpeta preparada: `python editor_timeline.py --carpeta "proyectos\forest-city\montaje"`.
8. Revisa la sincronización y renderiza primero una prueba corta.

También puedes usar `REVISAR_ESCENAS.bat` y pegar la ruta del plan cuando lo solicite.

## Qué hace el revisor visual
- Muestra cada párrafo del guion con su tiempo estimado.
- Permite previsualizar imágenes y vídeos candidatos.
- Permite escoger manualmente el recurso de cada escena y guardar la selección en el JSON.
- El preparador de montaje prioriza esa selección manual sobre las coincidencias automáticas.
- Si una escena no tiene recurso, queda marcada para revisión; no se inventan medios.

## Comprobación antes de renderizar (v0.8)
- Ejecuta `VALIDAR_PROYECTO.bat` o `python VALIDAR_PROYECTO.py "proyecto_video"` para verificar que los recursos del proyecto se pueden leer con FFprobe. La carpeta debe contener `imagenes\` y, si corresponde, `audio.*`.
- Ejecuta `python PRUEBA_RAPIDA.py` para comprobar las funciones básicas y el flujo de selección manual.
- Ejecuta `python PRUEBA_RENDER.py` para probar con FFmpeg un montaje sintético que mezcla una imagen fija, un videoclip y una pista de audio.
- Estas pruebas no garantizan que cualquier archivo del usuario sea compatible ni sustituyen la prueba de un documental completo.

## Limitaciones
- Las sugerencias automáticas usan nombres y etiquetas, no reconocimiento del contenido visual. Revisa siempre cada medio.
- Esta versión no descarga automáticamente material de Internet ni verifica licencias.
- El revisor se limita a `127.0.0.1` y solo sirve archivos que ya aparecen como candidatos en el plan. No lo expongas a Internet.
- La generación de un proyecto o metadatos no constituye investigación factual verificada.


## Novedades v0.6
- En movimiento automático, las imágenes fijas reciben un patrón suave alternado de zoom y paneo.
- Los videoclips conservan su movimiento original en modo automático; no se les añade zoom artificial.
- Los movimientos manuales (zoom in/out y paneos) siguen disponibles y se pueden aplicar también a los vídeos.
- Se incorpora una prueba de renderizado real con FFmpeg (`PRUEBA_RENDER.py`) para verificar la generación de un MP4 corto.


## Novedades v0.7
- Validador previo al render que detecta archivos multimedia ilegibles, extensiones incorrectas y ausencia de pistas de vídeo/audio.
- La prueba de renderizado ahora mezcla una imagen fija, un videoclip generado de prueba y una narración de audio; verifica que el MP4 tenga duración razonable y ambas pistas.
- Incluye `VALIDAR_PROYECTO.bat` para ejecutar la comprobación en Windows sin escribir comandos.
- El modo automático mantiene el zoom/paneo suave en imágenes y conserva el movimiento nativo de los videoclips.


## Novedades v0.8
- La lectura de `escenas.txt` reconoce párrafos separados por líneas vacías; los saltos de línea dentro de un párrafo se unen, evitando que una escena se divida por el ajuste de texto. Si no hay líneas vacías, se conserva el formato clásico de una escena por línea.
- Al generar los tiempos se crea también `*_informe.csv`, con número de escena, inicio, fin, duración, recurso y texto correspondiente. Se puede abrir con Excel o LibreOffice para revisar la sincronización.
- Añade `PRUEBA_SINCRONIZACION.py`, que comprueba la lectura de párrafos multilínea, el formato de una escena por línea y el informe CSV.

## Pruebas recomendadas para v0.8
1. `python PRUEBA_RAPIDA.py`
2. `python PRUEBA_SINCRONIZACION.py`
3. `python PRUEBA_RENDER.py` (requiere FFmpeg/FFprobe)
4. Ejecuta una prueba con una copia de tu guion real y verifica el CSV antes de renderizar el documental completo.

## Editor v0.9: auditoría antes del render

Antes de renderizar, puedes revisar el archivo `*_tiempos.json` generado por el sincronizador:

```bat
python REVISAR_TIMELINE.py "proyecto_video\video_final_tiempos.json" --medios "proyecto_video\imagenes"
```

El auditor crea un CSV con cada escena, sus tiempos, recurso encontrado y observaciones. Devuelve código 0 si no detecta problemas básicos, 1 si hay avisos y 2 si encuentra errores (por ejemplo, un recurso que falta). Para comparar con la duración de la narración, añade `--audio "ruta\narracion.mp3"`; esto requiere `ffprobe` disponible en PATH. También puedes ejecutar `REVISAR_TIMELINE.bat` y seguir las preguntas.

La auditoría no evalúa si el contenido visual coincide semánticamente con la narración. Conserva los mismos medios, tiempos y ajustes cuando uses `--reanudar` para continuar un render por bloques.


## Editor v1.0: informe de calidad ampliado

El auditor `REVISAR_TIMELINE.py` ahora genera dos informes: `*_auditoria.csv` (detalle por escena) y `*_calidad.json` (resumen de la línea de tiempo). Muestra duración total en segundos/minutos, duración mínima/media/máxima por escena, escenas demasiado cortas, huecos, solapamientos y diferencia frente a la duración de la narración.

También puedes pasar el guion para comprobar que la cantidad de escenas coincida con la cantidad de clips:

```bat
python REVISAR_TIMELINE.py "proyecto_video\video_final_tiempos.json" --medios "proyecto_video\imagenes" --audio "proyecto_video\narracion.mp3" --escenas "proyecto_video\escenas.txt"
```

`REVISAR_TIMELINE.bat` pregunta opcionalmente por la carpeta de medios, el audio y el guion. Código de salida: `0` = no detectó problemas estructurales; `1` = avisos que conviene revisar; `2` = errores. Un resultado OK no verifica que cada imagen coincida con lo narrado ni que los recursos tengan licencia de uso.

### Pruebas de v1.0

Ejecuta `python PRUEBA_AUDITORIA.py` para comprobar que se detectan recursos ausentes, huecos y diferencias entre el número de escenas del guion y de la timeline. Repite también las pruebas de sincronización y render indicadas arriba.


### Informe de coincidencia guion/voz

Al sincronizar con guion y Whisper, se guarda `video_alineacion.json` junto al video de salida. El campo `porcentaje_coincidencia_palabras` es una aproximación basada en palabras normalizadas. Puedes cambiar el umbral de aviso, por ejemplo `--umbral-coincidencia 60`. Una puntuación baja no bloquea automáticamente el render: indica que conviene comprobar que el audio y el guion correspondan.


## Solución: `open() got an unexpected keyword argument 'metadata_errors'`

Este mensaje suele indicar una incompatibilidad entre la versión instalada de PyAV (`av`) y `faster-whisper`. Cierra el editor y ejecuta `REPARAR_WHISPER.bat` desde la carpeta extraída. También puedes abrir CMD en esa carpeta y ejecutar `python -m pip install --upgrade av faster-whisper`. Luego reinicia el editor. Si usas un entorno virtual, ejecuta la actualización con el mismo Python que inicia el editor.
\n\n### Corrección v1.0.2 para `metadata_errors`\n\nEl sincronizador incluye una compatibilidad de respaldo para instalaciones de PyAV cuya función `av.open` no acepta `metadata_errors`. Si ocurre exactamente ese error, vuelve a intentar abrir el audio sin ese argumento. Si falla por otra causa, el error original se conserva.\n

### Soporte JFIF (v1.0.4)

Se admiten imágenes `.jfif` además de `.jpg` y `.jpeg`. JFIF suele contener datos JPEG; la extensión se reconoce en el importador, la sincronización y la auditoría.
