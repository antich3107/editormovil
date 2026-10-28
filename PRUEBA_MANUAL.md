# Prueba manual de Editor Móvil M1

1. Abrir `index.html` en un navegador moderno para comprobar la interfaz (para PWA/offline, servir por HTTPS).
2. Crear proyecto de prueba `Demo móvil`.
3. Pegar tres párrafos separados por líneas vacías y crear escenas; comprobar que aparecen tres.
4. Importar al menos un JPG, un JFIF, un MP4 corto y un MP3/WAV.
5. Confirmar que la lista de medios muestra nombre y tamaño; abrir vista previa cuando el navegador soporte el formato.
6. Asignar una imagen a escena 1 y ajustar duración a 7.5 s; comprobar que los tiempos de escenas posteriores se recalculan.
7. Cambiar de pestaña y recargar: proyecto y escenas deben persistir en IndexedDB.
8. Exportar JSON, TXT y plan JSON. Revisar que el TXT contiene el texto de las escenas en orden.
9. Importar el JSON exportado: debe recuperar metadatos/escenas y solicitar reimportar los medios.
10. Probar modo avión después de instalar desde HTTPS: la interfaz debe abrir offline. La previsualización de medios previamente guardados debe funcionar.

Nota: la prueba en este paquete no puede sustituir pruebas en el teléfono Android real. Formatos como HEIC/AVIF y algunos contenedores de vídeo dependen del navegador y de su decodificador.
