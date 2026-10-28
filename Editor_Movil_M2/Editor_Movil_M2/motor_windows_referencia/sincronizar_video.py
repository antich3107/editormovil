#!/usr/bin/env python3
"""
sincronizar_video.py
Empareja una carpeta de imágenes con una narración y genera un video fluido
(cambio de imagen en pausas naturales, zoom suave y fundidos entre imágenes).

Requisitos:
    - FFmpeg instalado y en el PATH (ffmpeg y ffprobe)
    - pip install faster-whisper      (solo si quieres sincronizar con la voz)

Uso básico:
    python sincronizar_video.py narracion.mp3 carpeta_imagenes -o video.mp4

Videos largos: si hay más de 60 imágenes, el script renderiza por bloques
(de ~40 imágenes) y los une al final sin recodificar. Así usa menos memoria y,
si algo falla, puedes retomar con --reanudar sin empezar de cero.

Las imágenes se ordenan por nombre (01.png, 02.png ... o img_1, img_2 ...).

Sincronización exacta con el guion: pasa --escenas escenas.txt (una línea de
narración por imagen, en el mismo orden). El script alinea ese texto con lo que
Whisper escucha y cambia cada imagen justo cuando empieza su línea.
"""
import argparse
import csv
import bisect
import collections
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".avif", ".ppm", ".pgm", ".pbm"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
UMBRAL_LOOP_SEG = 30   # más allá de esto no se guarda en memoria para repetir; se congela el último cuadro
_DUR_CACHE = {}
MEDIA_EXT = IMG_EXT | VIDEO_EXT
FORMATOS = {
    "horizontal": (1920, 1080),  # YouTube normal
    "vertical": (1080, 1920),    # Shorts / Reels / TikTok
    "cuadrado": (1080, 1080),
}
PROCESO_ACTUAL = None      # proceso de FFmpeg en curso (lo usa el editor para cancelar)
ULTIMA_COINCIDENCIA = None  # % de palabras del guion reconocidas en la última alineación
BLOQUE_AUTO = 40      # imágenes por bloque cuando se activa solo
UMBRAL_AUTO = 60      # a partir de cuántas imágenes se activan los bloques solos


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
MENSAJE_FFMPEG = (
    "No encuentro FFmpeg (ffmpeg y ffprobe) en tu equipo. En Windows: abre PowerShell y ejecuta "
    "'winget install Gyan.FFmpeg', cierra esa ventana, abre una nueva y comprueba con 'ffmpeg -version'. "
    "Alternativa: copia ffmpeg.exe y ffprobe.exe en la misma carpeta que este programa, "
    "o indica su carpeta con --ffmpeg C:\\ruta\\ffmpeg\\bin"
)


def herramientas_ok():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _tiene_ambos(d: Path):
    try:
        return (d.is_dir()
                and any((d / n).exists() for n in ("ffmpeg", "ffmpeg.exe"))
                and any((d / n).exists() for n in ("ffprobe", "ffprobe.exe")))
    except OSError:
        return False


def preparar_ffmpeg(ruta=None):
    """Si ffmpeg/ffprobe no están en el PATH, los busca en carpetas habituales
    (junto al programa, winget, chocolatey, C:\\ffmpeg...) y los agrega al PATH de este proceso."""
    if herramientas_ok():
        return True
    aqui = Path(__file__).resolve().parent
    candidatos = []
    if ruta:
        r = Path(ruta)
        candidatos += [r, r.parent, r / "bin"]
    candidatos += [aqui, aqui / "bin", aqui / "ffmpeg" / "bin", Path.cwd(), Path.cwd() / "ffmpeg" / "bin"]
    home = Path.home()
    candidatos += [Path("C:/ffmpeg/bin"), Path("C:/Program Files/ffmpeg/bin"),
                   Path("C:/Program Files (x86)/ffmpeg/bin"), Path("C:/ProgramData/chocolatey/bin"),
                   home / "ffmpeg" / "bin", home / "scoop" / "shims"]
    raices_winget = []
    if os.environ.get("LOCALAPPDATA"):
        raices_winget.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Packages")
    if os.environ.get("ProgramFiles"):
        raices_winget.append(Path(os.environ["ProgramFiles"]) / "WinGet" / "Packages")
    for raiz in raices_winget:
        try:
            for pkg in raiz.glob("*FFmpeg*"):
                candidatos += list(pkg.rglob("bin"))
        except OSError:
            pass
    for d in candidatos:
        if _tiene_ambos(d):
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            print(f"FFmpeg encontrado en {d}")
            return True
    return False


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def duracion_fuente(path) -> float:
    """Duración de un video (con caché, para no repetir ffprobe en el mismo render)."""
    clave = str(path)
    if clave not in _DUR_CACHE:
        _DUR_CACHE[clave] = duracion_audio(Path(path))
    return _DUR_CACHE[clave]


def duracion_audio(audio: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(audio)])
    return float(out.strip())


def listar_imagenes(carpeta: Path):
    """Lista imágenes y videoclips cortos (para B-roll de noticias) mezclados, por nombre."""
    imgs = sorted((p for p in carpeta.iterdir() if p.suffix.lower() in MEDIA_EXT),
                  key=natural_key)
    if not imgs:
        sys.exit(f"No encontré imágenes ni videoclips en {carpeta}")
    return imgs


# ----------------------------------------------------------------------------
# 1) Puntos de corte a partir de la narración
# ----------------------------------------------------------------------------
def _compat_pyav_metadata_errors():
    """Compatibilidad con versiones antiguas de PyAV que no aceptan metadata_errors."""
    try:
        import av
    except Exception:
        return
    actual = getattr(av, "open", None)
    if actual is None or getattr(actual, "_editor_metadata_compat", False):
        return

    def open_compatible(*args, **kwargs):
        try:
            return actual(*args, **kwargs)
        except TypeError as exc:
            # Solo repetir si el argumento que falla es exactamente metadata_errors.
            if "metadata_errors" not in kwargs or "metadata_errors" not in str(exc):
                raise
            kwargs = dict(kwargs)
            kwargs.pop("metadata_errors", None)
            return actual(*args, **kwargs)

    open_compatible._editor_metadata_compat = True
    av.open = open_compatible


def _transcribir(audio: Path, modelo: str, idioma: str):
    """Transcribe con faster-whisper y devuelve la lista de segmentos (con palabras).
    Usa la GPU si funciona; si falla (p. ej. faltan las librerías de NVIDIA), sigue en CPU."""
    _compat_pyav_metadata_errors()
    try:
        from faster_whisper import WhisperModel
    except ModuleNotFoundError as e:
        if (e.name or "").split(".")[0] == "faster_whisper":
            sys.exit("faster-whisper no está instalado en el Python que estás usando. Instálalo con:  "
                     f'"{sys.executable}" -m pip install faster-whisper  '
                     "(o usa el reparto rápido / --sin-whisper)")
        sys.exit(f"faster-whisper está instalado pero le falta un componente ({e.name}). Prueba:  "
                 f'"{sys.executable}" -m pip install --upgrade --force-reinstall faster-whisper')
    except ImportError as e:
        sys.exit(f"faster-whisper está instalado pero no se pudo cargar ({e}). En Windows suele resolverse "
                 "instalando el «Microsoft Visual C++ Redistributable» (vc_redist.x64.exe, desde microsoft.com) "
                 "y volviendo a abrir el programa.")
    print(f"Transcribiendo con Whisper ({modelo})... la primera vez descarga el modelo.")
    ultimo = None
    for dispositivo, tipo in (("auto", "auto"), ("cpu", "int8")):
        try:
            model = WhisperModel(modelo, device=dispositivo, compute_type=tipo)
            segmentos, _ = model.transcribe(str(audio), language=idioma,
                                            word_timestamps=True, vad_filter=True)
            return list(segmentos)   # se consume aquí: los errores de GPU aparecen en este punto
        except Exception as e:  # noqa: BLE001
            ultimo = e
            error_gpu = any(k in str(e).lower() for k in ("cuda", "cublas", "cudnn", "gpu", "ctranslate2"))
            if dispositivo == "auto" and error_gpu:
                print(f"No pude usar la GPU ({type(e).__name__}: {str(e)[:110]}). "
                      "Sigo con el procesador (CPU); tardará un poco más.")
                continue
            break
    texto = f"{type(ultimo).__name__} {ultimo}".lower()
    if any(k in texto for k in ("huggingface", "connect", "max retries", "localentrynotfound", "offline")):
        raise RuntimeError("No pude descargar el modelo de Whisper. Revisa tu conexión a internet "
                           "(solo hace falta la primera vez con cada modelo).")
    if "metadata_errors" in str(ultimo) and "unexpected keyword argument" in str(ultimo):
        raise RuntimeError(
            "Hay una incompatibilidad de versiones entre PyAV (av) y faster-whisper. "
            "Cierra el editor y ejecuta en CMD: "
            f'"{sys.executable}" -m pip install --upgrade av faster-whisper. '
            "Después vuelve a abrir el editor e intenta sincronizar otra vez."
        ) from ultimo
    raise ultimo


def candidatos_whisper(audio: Path, modelo: str, idioma: str):
    """Devuelve (fuertes, debiles): tiempos donde termina una frase / una coma."""
    fuertes, debiles = [], []
    for seg in _transcribir(audio, modelo, idioma):
        for w in (seg.words or []):
            t = w.word.strip()
            if not t:
                continue
            if t[-1] in ".?!…;:":
                fuertes.append(w.end)
            elif t[-1] == ",":
                debiles.append(w.end)
        fuertes.append(seg.end)
    return sorted(set(fuertes)), sorted(set(debiles))


def palabras_whisper(audio: Path, modelo: str, idioma: str):
    """Lista de (texto, inicio, fin) de cada palabra de la narración."""
    return [(w.word.strip(), w.start, w.end)
            for seg in _transcribir(audio, modelo, idioma)
            for w in (seg.words or []) if w.word.strip()]


def normalizar(texto):
    """Minúsculas, sin tildes ni signos: solo palabras."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.findall(r"[a-z0-9]+", t)


def leer_escenas(ruta: Path):
    """Lee escenas como párrafos separados por líneas vacías.

    Si el archivo no contiene líneas vacías, conserva el formato clásico:
    una escena por línea. Esto evita que un párrafo largo envuelto en varias
    líneas se convierta accidentalmente en muchas escenas.
    """
    texto = ruta.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not texto.strip():
        return []
    if re.search(r"\n\s*\n", texto):
        bloques = re.split(r"\n\s*\n+", texto.strip())
        return [re.sub(r"\s+", " ", b).strip() for b in bloques if b.strip()]
    return [re.sub(r"\s+", " ", l).strip() for l in texto.splitlines() if l.strip()]


def cortes_proporcionales(escenas, total):
    """Sin Whisper: reparte el audio según la cantidad de palabras de cada escena."""
    pesos = [max(1, len(normalizar(e))) for e in escenas]
    suma, acum, cortes = sum(pesos), 0, [0.0]
    for p in pesos[:-1]:
        acum += p
        cortes.append(total * acum / suma)
    cortes.append(total)
    return cortes


def _tiempo(idx, tabla, claves, total, n):
    """Tiempo de la palabra idx del guion; si Whisper no la reconoció, interpola."""
    if idx in tabla:
        return tabla[idx]
    p = bisect.bisect_left(claves, idx)
    izq = claves[p - 1] if p > 0 else -1
    der = claves[p] if p < len(claves) else n
    ti = tabla[izq] if izq >= 0 else 0.0
    td = tabla[der] if der < n else total
    return ti + (td - ti) * (idx - izq) / (der - izq)


def cortes_desde_escenas(escenas, palabras, total, hueco=0.5):
    """Alinea el texto de las escenas con las palabras que Whisper escuchó.
    Devuelve los tiempos de corte (len(escenas)+1), o None si no hay coincidencias."""
    wt, wmap = [], []
    for i, (txt, _, _) in enumerate(palabras):
        for tok in normalizar(txt):
            wt.append(tok)
            wmap.append(i)
    st, inicios = [], []
    for e in escenas:
        inicios.append(len(st))
        st.extend(normalizar(e))
    n = len(st)

    sm = difflib.SequenceMatcher(None, st, wt, autojunk=False)
    ini, fin, coinc = {}, {}, 0
    for a, b, k in sm.get_matching_blocks():
        for j in range(k):
            w = palabras[wmap[b + j]]
            ini[a + j], fin[a + j] = w[1], w[2]
            coinc += 1
    global ULTIMA_COINCIDENCIA
    ULTIMA_COINCIDENCIA = 100 * coinc / max(1, n)
    print(f"Coincidencia guion/voz: {ULTIMA_COINCIDENCIA:.0f}% de las palabras")
    if coinc < 0.3 * n:
        print("Aviso: coincide muy poco; revisa que el audio y el guion sean el mismo texto.")
    if not ini:
        return None
    claves = sorted(ini)

    cortes = [0.0]
    for s in inicios[1:]:
        t_ini = _tiempo(s, ini, claves, total, n)
        t_fin = _tiempo(s - 1, fin, claves, total, n)
        cortes.append((t_ini + t_fin) / 2 if t_fin <= t_ini else t_ini)
    cortes.append(total)
    for i in range(1, len(cortes) - 1):
        cortes[i] = max(cortes[i], cortes[i - 1] + hueco)
    for i in range(len(cortes) - 2, 0, -1):
        cortes[i] = min(cortes[i], cortes[i + 1] - hueco)
    return cortes


def elegir_cortes(n, total, fuertes, debiles, min_dur):
    """Elige n-1 cortes: lo más cerca posible de un reparto parejo,
    pero siempre en un final de frase (o coma como segunda opción)."""
    if n * min_dur > total:
        min_dur = total / (n * 2)
    candidatos = [(t, 0.0) for t in fuertes] + [(t, 1.5) for t in debiles]
    cortes = [0.0]
    for k in range(1, n):
        objetivo = k * total / n
        lo = cortes[-1] + min_dur
        hi = total - (n - k) * min_dur
        pool = [(t, pen) for t, pen in candidatos if lo <= t <= hi]
        if pool:
            c = min(pool, key=lambda x: abs(x[0] - objetivo) + x[1])[0]
        else:
            c = min(max(objetivo, lo), hi)
        cortes.append(c)
    cortes.append(total)
    return cortes


def construir_clips(imagenes, cortes):
    return [{"imagen": img.name, "path": str(img),
             "inicio": round(cortes[i], 3), "fin": round(cortes[i + 1], 3)}
            for i, img in enumerate(imagenes)]


def cargar_tiempos(json_path: Path, carpeta: Path):
    data = json.loads(json_path.read_text(encoding="utf-8"))
    clips = []
    for c in data["clips"]:
        clips.append({"imagen": c["imagen"], "path": str(carpeta / c["imagen"]),
                      "inicio": float(c["inicio"]), "fin": float(c["fin"])})
    return clips


def guardar_tiempos(clips, ruta: Path, escenas=None):
    data = {"version": 2, "clips": [{k: c[k] for k in ("imagen", "inicio", "fin")} for c in clips]}
    ruta.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    informe = ruta.with_name(ruta.stem + "_informe.csv")
    with informe.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["escena", "inicio_segundos", "fin_segundos", "duracion_segundos", "recurso", "texto_escena"])
        for i, c in enumerate(clips):
            inicio, fin = float(c["inicio"]), float(c["fin"])
            texto = escenas[i] if escenas and i < len(escenas) else ""
            writer.writerow([i + 1, f"{inicio:.3f}", f"{fin:.3f}", f"{max(0, fin-inicio):.3f}", c["imagen"], texto])
    print(f"Tiempos guardados en {ruta} (puedes editarlos y reusarlos con --tiempos)")
    print(f"Informe de escenas guardado en {informe}")


# ----------------------------------------------------------------------------
# 2) Render con FFmpeg
# ----------------------------------------------------------------------------
def filtro_color(nombre):
    """Filtros de color integrados de FFmpeg; no requieren servicios externos."""
    return {
        "ninguno": "",
        "cinematico": "eq=contrast=1.12:saturation=0.92:brightness=-0.015,colorbalance=rs=0.03:bs=-0.025",
        "blanco-negro": "hue=s=0,eq=contrast=1.12:brightness=0.01",
        "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:0:0:0:1",
        "frio": "colorbalance=rs=-0.025:bs=0.045,eq=saturation=0.92:contrast=1.04",
        "calido": "colorbalance=rs=0.045:bs=-0.035,eq=saturation=1.05",
        "vintage": "curves=vintage,eq=contrast=1.08:saturation=0.78:brightness=0.015",
        "alto-contraste": "eq=contrast=1.22:saturation=1.08:brightness=-0.01",
        "suave": "eq=contrast=0.96:saturation=0.92:brightness=0.015,gblur=sigma=0.25",
    }.get(nombre, "")


def ajustar_transicion(clips, trans):
    """La transición no puede ser más larga que la imagen más corta."""
    if len(clips) < 2:
        return 0.0
    dur_min = min(c["fin"] - c["inicio"] for c in clips)
    return max(0.0, min(trans, dur_min * 0.9))


def renderizar(clips, audio, salida, W, H, fps, trans, zoom, efecto, ss, preset, t0=0.0, progreso=None, filtro_color_nombre="cinematico", movimiento="automatico"):
    """Renderiza una lista de clips. Si audio es None, genera video sin audio
    (se usa para los bloques). t0 = instante del audio donde arranca el primer clip."""
    n = len(clips)
    durs = [c["fin"] - c["inicio"] for c in clips]

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"]
    cmd += ["-nostats", "-progress", "pipe:1"] if progreso else ["-stats"]
    filtros = []
    for i, c in enumerate(clips):
        d = durs[i]
        if n == 1:
            L = d
        elif i in (0, n - 1):
            L = d + trans / 2
        else:
            L = d + trans
        es_video = Path(c["path"]).suffix.lower() in VIDEO_EXT
        if movimiento == "automatico":
            # Movimiento Ken Burns en imágenes fijas; los vídeos conservan su
            # movimiento original para evitar zoom artificial y recodificación visual innecesaria.
            patron = 4 if es_video else i % 4
        else:
            patron = {
                "zoom-in": 0, "zoom-out": 1,
                "paneo-izquierda-derecha": 2, "paneo-derecha-izquierda": 3,
                "ninguno": 4,
            }.get(movimiento, 0)
        color = filtro_color(filtro_color_nombre)
        if es_video:
            cmd += ["-i", c["path"]]
            origen = max(0.0, float(c.get("origen", 0.0) or 0.0))
            disponible = max(0.1, duracion_fuente(c["path"]) - origen)
            cadena = (f"[{i}:v]fps={fps},trim=start={origen:.3f},setpts=PTS-STARTPTS")
            if disponible < L and disponible <= UMBRAL_LOOP_SEG:
                cadena += f",loop=loop=-1:size={max(1, round(disponible * fps))}:start=0"
            cadena += f",trim=duration={L:.3f},setpts=PTS-STARTPTS"
            if disponible > UMBRAL_LOOP_SEG and disponible < L:
                cadena += f",tpad=stop_mode=clone:stop_duration={L - disponible:.3f}"
            cadena += f",scale={W * ss}:{H * ss}:force_original_aspect_ratio=increase,crop={W * ss}:{H * ss},setsar=1"
            if patron != 4:
                frames = max(2, round(L * fps))
                cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
                if patron == 0:
                    z, x, y = f"min(1+{zoom}*on/{frames},1+{zoom})", cx, cy
                elif patron == 1:
                    z, x, y = f"max(1+{zoom}-{zoom}*on/{frames},1)", cx, cy
                elif patron == 2:
                    z, x, y = f"1+{zoom}", f"(iw-iw/zoom)*on/{frames}", cy
                else:
                    z, x, y = f"1+{zoom}", f"(iw-iw/zoom)*(1-on/{frames})", cy
                cadena += f",zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={fps}"
            if color:
                cadena += "," + color
            filtros.append(cadena + f",settb=AVTB,fps={fps},format=yuv420p[v{i}]")
        else:
            frames = max(2, round(L * fps))
            cmd += ["-i", c["path"]]
            cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
            if patron == 0:
                z, x, y = f"1+{zoom}*on/{frames}", cx, cy
            elif patron == 1:
                z, x, y = f"{1 + zoom}-{zoom}*on/{frames}", cx, cy
            elif patron == 2:
                z, x, y = f"1+{zoom}", f"(iw-iw/zoom)*on/{frames}", cy
            elif patron == 3:
                z, x, y = f"1+{zoom}", f"(iw-iw/zoom)*(1-on/{frames})", cy
            else:
                z, x, y = "1", cx, cy
            cadena = (f"[{i}:v]scale={W * ss}:{H * ss}:force_original_aspect_ratio=increase,"
                      f"crop={W * ss}:{H * ss},setsar=1,"
                      f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={fps}")
            if color:
                cadena += "," + color
            filtros.append(cadena + f",settb=AVTB,fps={fps},format=yuv420p[v{i}]")

    if n == 1:
        ultimo = "[v0]"
    else:
        prev = "[v0]"
        for k in range(1, n):
            offset = max(0.0, clips[k]["inicio"] - t0 - trans / 2)
            out = f"[x{k}]"
            filtros.append(f"{prev}[v{k}]xfade=transition={efecto}:"
                           f"duration={trans:.3f}:offset={offset:.3f}{out}")
            prev = out
        ultimo = prev

    grafo = ";".join(filtros)
    if audio is not None:
        cmd += ["-i", str(audio)]
    if len(grafo) > 24000:  # evita el límite de longitud de comando (Windows)
        tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        tmp.write(grafo)
        tmp.close()
        cmd += ["-filter_complex_script", tmp.name]
    else:
        cmd += ["-filter_complex", grafo]

    cmd += ["-map", ultimo]
    if audio is not None:
        cmd += ["-map", f"{n}:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-movflags", "+faststart", str(salida)]
    if progreso is None:
        subprocess.run(cmd, check=True)
        return
    _correr_con_progreso(cmd, clips[-1]["fin"] - clips[0]["inicio"], progreso)


def _correr_con_progreso(cmd, dur_total, progreso):
    """Ejecuta FFmpeg y llama a progreso(0..1) mientras avanza."""
    global PROCESO_ACTUAL
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1)
    PROCESO_ACTUAL = p
    ultimas = collections.deque(maxlen=20)
    try:
        for linea in p.stdout:
            linea = linea.strip()
            if linea.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    t = int(linea.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                progreso(min(1.0, max(0.0, t / max(dur_total, 0.001))))
            elif linea and "=" not in linea.split(" ")[0]:
                ultimas.append(linea)
        p.wait()
    finally:
        PROCESO_ACTUAL = None
    if p.returncode != 0:
        raise RuntimeError("FFmpeg terminó con error: " + " | ".join(ultimas))


def renderizar_por_bloques(clips, tam, audio, salida, W, H, fps, trans, zoom,
                           efecto, ss, preset, reanudar, conservar, progreso=None,
                           filtro_color_nombre="cinematico", movimiento="automatico"):
    n = len(clips)
    k = -(-n // tam)                 # cantidad de bloques (redondeo hacia arriba)
    size = -(-n // k)                # tamaño parejo, sin bloque final diminuto
    grupos = [clips[i:i + size] for i in range(0, n, size)]

    carpeta = salida.with_name(salida.stem + "_bloques")
    carpeta.mkdir(exist_ok=True)
    partes = []
    total_dur = clips[-1]["fin"] - clips[0]["inicio"]
    hecho = 0.0
    print(f"Render por bloques: {len(grupos)} bloques de ~{size} imágenes")

    for idx, g in enumerate(grupos, 1):
        parte = (carpeta / f"bloque_{idx:03d}.mp4").resolve()
        partes.append(parte)
        dur_b = g[-1]["fin"] - g[0]["inicio"]
        if reanudar and parte.exists():
            print(f"Bloque {idx}/{len(grupos)}: ya existe, se reutiliza")
            hecho += dur_b
            continue
        print(f"Bloque {idx}/{len(grupos)} ({g[0]['inicio']:.0f}s - {g[-1]['fin']:.0f}s)...")
        tmp = parte.with_name(parte.stem + "_tmp.mp4")
        cb = None
        if progreso:
            cb = (lambda f, h=hecho, d=dur_b: progreso(0.97 * (h + f * d) / total_dur))
        renderizar(g, None, tmp, W, H, fps, trans, zoom, efecto, ss, preset,
                   t0=g[0]["inicio"], progreso=cb, filtro_color_nombre=filtro_color_nombre,
                   movimiento=movimiento)
        tmp.replace(parte)           # solo queda con nombre final si terminó bien
        hecho += dur_b

    lista = carpeta / "lista.txt"
    lista.write_text("".join("file '{}'\n".format(p.as_posix().replace("'", "'\\''"))
                             for p in partes), encoding="utf-8")
    print("Uniendo bloques y agregando el audio...")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
                    "-f", "concat", "-safe", "0", "-i", str(lista), "-i", str(audio),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    "-movflags", "+faststart", str(salida)], check=True)
    if progreso:
        progreso(1.0)
    if not conservar:
        shutil.rmtree(carpeta, ignore_errors=True)


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Sincroniza imágenes con una narración.")
    ap.add_argument("audio", type=Path, help="Archivo de narración (mp3, wav, m4a...)")
    ap.add_argument("imagenes", type=Path, help="Carpeta con las imágenes (ordenadas por nombre)")
    ap.add_argument("-o", "--salida", type=Path, default=Path("video_final.mp4"))
    ap.add_argument("--formato", choices=FORMATOS, default="horizontal")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--transicion", type=float, default=0.4, help="Segundos de fundido (0 = corte seco)")
    ap.add_argument("--efecto", default="fade",
                    help="Efecto xfade de FFmpeg: fade, dissolve, smoothleft, wipeleft...")
    ap.add_argument("--zoom", type=float, default=0.10, help="Intensidad del zoom (0.10 = 10%%)")
    ap.add_argument("--filtro", dest="filtro_color_nombre", choices=["ninguno", "cinematico", "blanco-negro", "sepia", "frio", "calido", "vintage", "alto-contraste", "suave"], default="cinematico", help="Filtro de color aplicado a imágenes y clips")
    ap.add_argument("--movimiento", choices=["automatico", "zoom-in", "zoom-out", "paneo-izquierda-derecha", "paneo-derecha-izquierda", "ninguno"], default="automatico", help="Movimiento aplicado a imágenes y clips")
    ap.add_argument("--min-dur", type=float, default=2.0, help="Duración mínima por imagen (s)")
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--modelo", default="small",
                    help="Modelo Whisper: tiny, base, small, medium, large-v3")
    ap.add_argument("--umbral-coincidencia", type=float, default=50.0,
                    help="Umbral %% mínimo guion/voz antes de mostrar aviso (por defecto 50)")
    ap.add_argument("--sin-whisper", action="store_true",
                    help="Reparte las imágenes en partes iguales, sin transcribir")
    ap.add_argument("--tiempos", type=Path,
                    help="JSON de tiempos ya generado/editado (omite la transcripción)")
    ap.add_argument("--escenas", type=Path,
                    help="TXT con una línea de narración por imagen (mismo orden): "
                         "cada imagen cambia justo cuando empieza su línea")
    ap.add_argument("--ffmpeg", help="Carpeta donde está ffmpeg (si no está en el PATH)")
    ap.add_argument("--rapido", action="store_true", help="Render más rápido, menos suave")
    ap.add_argument("--bloque", type=int, default=None,
                    help=f"Imágenes por bloque. Por defecto es automático (bloques de "
                         f"{BLOQUE_AUTO} si hay más de {UMBRAL_AUTO} imágenes). 0 = todo de una vez")
    ap.add_argument("--reanudar", action="store_true",
                    help="Reutiliza los bloques ya renderizados (úsalo con los MISMOS tiempos)")
    ap.add_argument("--conservar-bloques", action="store_true",
                    help="No borra la carpeta de bloques al terminar")
    a = ap.parse_args()

    if not preparar_ffmpeg(a.ffmpeg):
        sys.exit(MENSAJE_FFMPEG)
    W, H = FORMATOS[a.formato]
    total = duracion_audio(a.audio)
    imagenes = listar_imagenes(a.imagenes)
    print(f"{len(imagenes)} imágenes | audio {total:.1f}s")

    escenas = []
    if a.tiempos:
        clips = cargar_tiempos(a.tiempos, a.imagenes)
    else:
        if a.escenas:
            escenas = leer_escenas(a.escenas)
            if len(escenas) != len(imagenes):
                sys.exit(f"{a.escenas} tiene {len(escenas)} líneas y hay {len(imagenes)} imágenes: "
                         "deben coincidir (una línea por imagen).")
            cortes = None
            if not a.sin_whisper:
                palabras = palabras_whisper(a.audio, a.modelo, a.idioma)
                cortes = cortes_desde_escenas(escenas, palabras, total)
                coincidencia = ULTIMA_COINCIDENCIA
                alineacion = {
                    "version_editor": "1.0",
                    "audio": str(a.audio.resolve()),
                    "guion": str(a.escenas.resolve()),
                    "modelo_whisper": a.modelo,
                    "idioma": a.idioma,
                    "porcentaje_coincidencia_palabras": round(coincidencia, 2) if coincidencia is not None else None,
                    "umbral_aviso_porcentaje": a.umbral_coincidencia,
                    "cantidad_escenas": len(escenas),
                    "resultado": "REVISAR" if coincidencia is None or coincidencia < a.umbral_coincidencia else "OK",
                    "nota": "La coincidencia es una estimación textual; no garantiza una alineación semántica perfecta."
                }
                alineacion_path = a.salida.with_name(a.salida.stem + "_alineacion.json")
                alineacion_path.write_text(json.dumps(alineacion, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Informe de alineación guardado en {alineacion_path}")
                if coincidencia is not None and coincidencia < a.umbral_coincidencia:
                    print(f"AVISO: coincidencia inferior al umbral ({coincidencia:.1f}% < {a.umbral_coincidencia:.1f}%). Revisa el guion y la narración.")
            if cortes is None:
                print("Repartiendo según la longitud de cada escena (sin Whisper).")
                cortes = cortes_proporcionales(escenas, total)
        else:
            if a.sin_whisper:
                fuertes, debiles = [], []
            else:
                fuertes, debiles = candidatos_whisper(a.audio, a.modelo, a.idioma)
            cortes = elegir_cortes(len(imagenes), total, fuertes, debiles, a.min_dur)
        clips = construir_clips(imagenes, cortes)
        cortas = [c["imagen"] for c in clips if c["fin"] - c["inicio"] < 1.5]
        if cortas:
            print(f"Aviso: {len(cortas)} imágenes duran menos de 1.5 s (ej. {cortas[0]}); "
                  "revisa el JSON de tiempos.")
        guardar_tiempos(clips, a.salida.with_name(a.salida.stem + "_tiempos.json"), escenas or None)

    trans = ajustar_transicion(clips, a.transicion)
    ss, preset = (1, "veryfast") if a.rapido else (2, "medium")

    if a.bloque is None:
        bloque = BLOQUE_AUTO if len(clips) > UMBRAL_AUTO else 0
    else:
        bloque = a.bloque

    print("Renderizando video con FFmpeg (puede tardar bastante en videos largos)...")
    if bloque and len(clips) > bloque:
        renderizar_por_bloques(clips, bloque, a.audio, a.salida, W, H, a.fps, trans,
                               a.zoom, a.efecto, ss, preset, a.reanudar,
                               a.conservar_bloques, filtro_color_nombre=a.filtro_color_nombre,
                               movimiento=a.movimiento)
    else:
        renderizar(clips, a.audio, a.salida, W, H, a.fps, trans, a.zoom, a.efecto, ss, preset,
                   filtro_color_nombre=a.filtro_color_nombre, movimiento=a.movimiento)
    print(f"Listo: {a.salida}")


if __name__ == "__main__":
    main()
