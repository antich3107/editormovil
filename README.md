# Editor Móvil M1 — Android, independiente del PC

Primera versión funcional tipo PWA para organizar proyectos documentales directamente en Android. No requiere cuenta ni servicios de IA de pago.

## Qué funciona en M1
- Interfaz adaptada a pantallas táctiles.
- Crea y guarda varios proyectos en el almacenamiento local del navegador (IndexedDB).
- Importa imágenes, vídeos y audios desde el teléfono, incluyendo JFIF y extensiones comunes.
- Previsualiza recursos compatibles con el navegador.
- Divide el guion en escenas por párrafos, asigna recursos, ordena escenas y ajusta duraciones estimadas.
- Exporta el guion por escenas (`.txt`), un manifiesto de escenas (`.json`) y una copia de metadatos del proyecto (`.json`).
- Una vez instalada como PWA, la interfaz carga sin conexión a Internet.

## Limitaciones explícitas de M1
- No transcribe audio con Whisper ni renderiza MP4 con FFmpeg dentro de Android.
- La duración de cada escena es una estimación manual basada en longitud del texto, editable por el usuario; no es sincronización real con voz.
- La exportación JSON de proyecto contiene referencias/nombres de medios, no los bytes de los archivos. Los archivos originales siguen en el almacenamiento local del navegador y deben volver a importarse en otro dispositivo.
- El navegador puede limitar espacio disponible, especialmente con vídeos grandes. Exporta copias de metadatos con frecuencia y conserva originales.
- La integración directa para enviar trabajos al motor Windows aún no está implementada. El motor actual se incluye en `motor_windows_referencia/` como referencia para la siguiente fase.

## Instalar en Android sin depender del PC después de la instalación
Una PWA necesita servirse desde HTTPS para que Chrome permita instalarla y habilitar el modo sin conexión. Puedes publicarla gratuitamente con GitHub Pages una sola vez; después se abre desde el móvil y funciona offline. No requiere que el PC permanezca encendido.

### Publicar gratuitamente con GitHub Pages
1. En GitHub crea un repositorio nuevo, por ejemplo `editor-movil`.
2. Sube el contenido de esta carpeta a la raíz del repositorio (no subas el ZIP como único archivo: sube los archivos y carpetas extraídos).
3. En el repositorio abre **Settings → Pages**.
4. En **Build and deployment**, elige **Deploy from a branch**, selecciona `main` y la carpeta `/ (root)`, y guarda.
5. Espera a que GitHub Pages muestre una URL HTTPS.
6. Abre esa URL en Chrome en Android → menú ⋮ → **Instalar aplicación** o **Añadir a pantalla de inicio**.
7. Abre la aplicación una vez conectada, espera a que cargue, y luego comprueba el modo avión.

GitHub Pages aloja los archivos estáticos de la aplicación. El contenido de tus proyectos y medios se guarda en el almacenamiento del navegador de tu móvil, no se sube al repositorio.

## Uso
1. Abre la pestaña **Proyecto**, pon nombre y formato.
2. Pega el guion. Separa escenas con una línea en blanco.
3. Pulsa **Crear escenas desde el guion**.
4. En **Recursos**, importa imágenes/vídeos y audio; puedes seleccionar la narración principal.
5. En **Escenas**, asigna un recurso y ajusta la duración estimada de cada escena.
6. En **Exportar**, guarda una copia JSON, el guion TXT o el plan JSON.

## Recuperación y privacidad
- No borres los datos del sitio ni desinstales la PWA sin exportar la copia del proyecto y mantener copias de los medios originales.
- El JSON exportado no incluye los archivos binarios multimedia.
- Si Android elimina datos de sitios por falta de espacio, los proyectos locales pueden perderse. Mantén respaldo externo.

## Próximas fases
- M2: exportación de paquete portable que incluya los medios, con advertencia de tamaño.
- M3: importación directa de paquete al editor Windows y puente de sincronización.
- M4: estudiar motor de render en Android o render remoto opcional.
