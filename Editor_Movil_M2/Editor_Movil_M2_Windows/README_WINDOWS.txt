EDITOR MÓVIL M2 — PUENTE WI-FI PARA WINDOWS

REQUISITOS
- Windows 10/11 y Python 3 instalado.
- Editor Móvil M2 publicado en HTTPS e instalado/abierto en Android.
- Android y PC conectados a la misma red Wi-Fi privada.
- FFmpeg/ffprobe disponibles para renderizar (el motor existente los requiere).

TRANSFERIR
1. Extrae esta carpeta en Windows.
2. Ejecuta INICIAR_TRANSFERENCIA_WIFI.bat.
3. Si Windows Firewall pregunta, permite Python solo en redes privadas.
4. Anota la dirección http://IP-DEL-PC:8765 que aparece en la consola.
5. En Android, abre esa dirección en Chrome. En Editor Móvil M2, ve a Exportar y pulsa Crear ZIP completo.
6. Vuelve a la página del puente, selecciona el ZIP descargado y pulsa Subir ZIP al PC.
7. Cuando se importe, selecciona la narración y el formato; pulsa Preparar y renderizar MP4.

SEGURIDAD Y LÍMITES
- Servidor sin autenticación: úsalo solo en una red Wi-Fi privada y de confianza. Cierra la ventana al terminar.
- El ZIP se transmite por la red local; no se usa nube. El archivo puede ser grande; mantén el teléfono despierto durante la transferencia.
- Los proyectos importados quedan en Proyectos_importados. No borra el ZIP ni los medios originales.
- El render exige que cada escena tenga un recurso asignado compatible. Se utiliza el motor sincronizar_video.py incluido y se desactiva Whisper para la primera prueba.
- No renderices con medios no confiables.
