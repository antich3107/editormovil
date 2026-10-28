# Editor Móvil M2

PWA local-first para Android. M2 añade exportación ZIP real con todos los medios y un puente Wi-Fi local para Windows.

## Android
1. Publica el contenido de esta carpeta en un sitio HTTPS (por ejemplo GitHub Pages gratuito).
2. Abre en Chrome Android e instala/añade a pantalla de inicio.
3. Importa recursos, crea escenas y asigna un medio a cada escena.
4. En Exportar, pulsa **Crear ZIP completo**. El ZIP contiene `project.json`, `scenes.txt`, `README_IMPORTAR.txt` y `media/`.

## Windows / Wi-Fi
Usa la carpeta `Editor_Movil_M2_Windows` incluida en el ZIP de entrega. Ejecuta `INICIAR_TRANSFERENCIA_WIFI.bat`, abre en el móvil la URL local mostrada, y sube el ZIP generado. El puente descomprime el proyecto y permite iniciar el motor existente con la narración seleccionada.

## Limitaciones
- Android y Windows deben estar en la misma Wi-Fi; no es una transferencia por Internet.
- No se ha probado en un teléfono físico en esta sesión.
- El ZIP utiliza compresión STORE (sin comprimir archivos ya comprimidos) para evitar pérdida y mantener medios originales. Tamaño de ZIP cercano al total de los medios.
- Para renderizar, asigna un recurso a cada escena y selecciona un audio de narración. La primera integración utiliza `--sin-whisper` y duraciones proporcionales por escena; la sincronización Whisper/tiempos avanzados se puede añadir en la siguiente fase.
- Servidor de transferencia local sin contraseña; solo usar en red privada de confianza y cerrar al terminar.
