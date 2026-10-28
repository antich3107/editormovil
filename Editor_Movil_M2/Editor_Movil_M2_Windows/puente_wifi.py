# -*- coding: utf-8 -*-
"Editor M2 Wi-Fi Bridge: recibe paquetes ZIP en la red local y prepara proyectos para Windows."
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import socket, json, zipfile, shutil, os, threading, subprocess, sys, html, time
BASE=Path(__file__).resolve().parent
INBOX=BASE/'Transferencias_recibidas'; PROJECTS=BASE/'Proyectos_importados'; MAX_UPLOAD=12*1024**3
INBOX.mkdir(exist_ok=True); PROJECTS.mkdir(exist_ok=True)
STATE={'last_project':None,'render':None,'log':'','error':None}

def lan_ip():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:s.connect(('192.0.2.1',80)); return s.getsockname()[0]
    except Exception:return '127.0.0.1'

def page(msg=''):
    status=''
    if STATE['last_project']:
        p=Path(STATE['last_project']); meta=json.loads((p/'project.json').read_text(encoding='utf-8')); pr=meta.get('project',meta)
        audios=[m for m in pr.get('media',[]) if m.get('type')=='audio' and (p/m.get('path','')).is_file()]
        options=''.join(f'<option value="{html.escape(m["path"],quote=True)}" {"selected" if m.get("id")==pr.get("narrationId") else ""}>{html.escape(m["name"])}</option>' for m in audios)
        status=f'''<section><h2>Proyecto importado: {html.escape(pr.get('name','Sin título'))}</h2><p>{len(pr.get('scenes',[]))} escenas · {len(pr.get('media',[]))} recursos</p><p>Carpeta: <code>{html.escape(str(p))}</code></p><form id="render"><label>Narración principal <select name="audio" required>{options or '<option value="">No se encontraron audios</option>'}</select></label><label>Formato <select name="aspect"><option value="horizontal">YouTube 16:9</option><option value="vertical">Vertical 9:16</option><option value="cuadrado">Cuadrado 1:1</option></select></label><button>Preparar y renderizar MP4</button></form><p id="renderStatus"></p><pre id="renderLog"></pre></section>'''
    return f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Editor M2 Wi-Fi</title><style>body{{font:16px system-ui;max-width:820px;margin:24px auto;padding:0 16px;background:#101827;color:#f1f5f9}}section,.card{{background:#1c283a;padding:18px;border-radius:14px;margin:16px 0}}button{{padding:12px 18px;border:0;border-radius:9px;background:#5eead4;color:#06211e;font-weight:700;margin-top:12px}}input,select{{display:block;width:100%;box-sizing:border-box;padding:12px;margin:8px 0 16px;border-radius:8px}}code,pre{{overflow-wrap:anywhere;white-space:pre-wrap}}.muted{{color:#bac7d9}}</style><h1>Editor M2 · Transferencia Wi-Fi</h1><p class="muted">Móvil y PC deben estar conectados a la misma red Wi-Fi. Transferencia local; el ZIP no se envía a Internet.</p><section><h2>1. Recibir paquete desde Android</h2><p>En Editor Móvil pulsa <b>Crear ZIP completo</b>. Luego selecciona ese ZIP aquí.</p><input id="zip" type="file" accept=".zip,application/zip"><button id="upload">Subir ZIP al PC</button><p id="uploadStatus">{html.escape(msg)}</p><progress id="progress" max="100" value="0" style="width:100%"></progress></section>{status}<script>const $=id=>document.getElementById(id);$('upload').onclick=async()=>{{const f=$('zip').files[0];if(!f){{alert('Selecciona el ZIP exportado desde el móvil.');return}}$('uploadStatus').textContent='Transfiriendo '+f.name+' ('+(f.size/1048576).toFixed(1)+' MB)…';$('progress').value=0;try{{const r=await fetch('/upload?name='+encodeURIComponent(f.name),{{method:'POST',headers:{{'Content-Type':'application/zip'}},body:f}});const j=await r.json();if(!r.ok)throw new Error(j.error||'Error de transferencia');$('progress').value=100;$('uploadStatus').textContent=j.message;location.href='/?imported=1'}}catch(e){{$('uploadStatus').textContent='Error: '+e.message}}}};const form=$('render');if(form)form.onsubmit=async e=>{{e.preventDefault();$('renderStatus').textContent='Preparando render…';const data=Object.fromEntries(new FormData(form));try{{const r=await fetch('/render',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});const j=await r.json();if(!r.ok)throw new Error(j.error);$('renderStatus').textContent=j.message;poll()}}catch(e){{$('renderStatus').textContent='Error: '+e.message}}}};async function poll(){{try{{const r=await fetch('/status');const j=await r.json();if($('renderLog'))$('renderLog').textContent=j.log||'';if($('renderStatus'))$('renderStatus').textContent=j.render||'Listo';if(j.running)setTimeout(poll,2500)}}catch(e){{}}}}if(form)poll();</script></html>'''

def safe_extract(zf,dest):
    for info in zf.infolist():
        name=info.filename.replace('\\','/')
        if name.startswith('/') or any(part=='..' for part in name.split('/')): raise ValueError('ZIP contiene una ruta no permitida')
        if info.file_size>MAX_UPLOAD: raise ValueError('Un archivo del ZIP supera el límite permitido')
    zf.extractall(dest)

def prepare_render(proj,audio_rel,aspect):
    meta=json.loads((proj/'project.json').read_text(encoding='utf-8')); pr=meta.get('project',meta)
    media=pr.get('media',[]); scenes=pr.get('scenes',[])
    aud=next((m for m in media if m.get('path')==audio_rel and m.get('type')=='audio'),None)
    if not aud: raise ValueError('Selecciona un audio válido como narración')
    audio=(proj/aud['path']).resolve()
    if not audio.is_file() or proj.resolve() not in audio.parents: raise ValueError('No se encontró la narración dentro del proyecto')
    assets=proj/'render_assets'; assets.mkdir(exist_ok=True)
    for old in assets.iterdir():
        if old.is_file():old.unlink()
    scene_lines=[]; missing=[]
    byid={m.get('id'):m for m in media}
    for i,sc in enumerate(scenes,1):
        m=byid.get(sc.get('mediaId'))
        if not m and sc.get('mediaName'):m=next((x for x in media if x.get('name','').lower()==str(sc['mediaName']).lower()),None)
        if not m:
            missing.append(f'Escena {i}: sin recurso asignado');continue
        src=(proj/m.get('path','')).resolve()
        if not src.is_file() or proj.resolve() not in src.parents:missing.append(f'Escena {i}: falta {m.get("name")}');continue
        supported={'.jpg','.jpeg','.jfif','.png','.webp','.bmp','.tif','.tiff','.gif','.avif','.ppm','.pgm','.pbm','.mp4','.mov','.webm','.mkv','.m4v'}
        if src.suffix.lower() not in supported: missing.append(f'Escena {i}: formato {src.suffix} no compatible con el motor; usa JPG/PNG/MP4') ; continue
        dst=assets/(f'{i:04d}_'+src.name)
        shutil.copy2(src,dst);scene_lines.append(str(sc.get('text','')).replace('\n',' ').strip())
    if missing: raise ValueError('Asigna un archivo a cada escena antes de renderizar. '+ '; '.join(missing[:8]))
    if not scene_lines: raise ValueError('El proyecto no tiene escenas con recursos asignados')
    scene_file=proj/'escenas_render.txt';scene_file.write_text('\n'.join(scene_lines)+'\n',encoding='utf-8')
    return audio,assets,scene_file,aspect

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,code,body,ctype='text/html; charset=utf-8'):
        raw=body.encode('utf-8') if isinstance(body,str) else body;self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/status':self.send(200,json.dumps({'running':bool(STATE['render'] and STATE['render'].poll() is None),'render':STATE.get('render_message'),'log':STATE.get('log','')},ensure_ascii=False),'application/json');return
        self.send(200,page('Paquete recibido correctamente.' if 'imported=1' in self.path else ''))
    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/upload':
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>MAX_UPLOAD:self.send(413,json.dumps({'error':'ZIP vacío o mayor de 12 GB'}),'application/json');return
            name=urlparse(self.path).query
            from urllib.parse import parse_qs
            filename=parse_qs(name).get('name',['paquete.zip'])[0]
            if not filename.lower().endswith('.zip'):filename+='.zip'
            dest=INBOX/(str(int(time.time()))+'_'+Path(filename).name.replace('..','_').replace(' ','_'))
            remaining=length
            with dest.open('wb') as f:
                while remaining:
                    chunk=self.rfile.read(min(1024*1024,remaining))
                    if not chunk:break
                    f.write(chunk);remaining-=len(chunk)
            if remaining:dest.unlink(missing_ok=True);self.send(400,json.dumps({'error':'Transferencia incompleta'}),'application/json');return
            try:
                with zipfile.ZipFile(dest) as z:
                    names=z.namelist()
                    if 'project.json' not in names:raise ValueError('El ZIP no contiene project.json de Editor M2')
                    project=PROJECTS/(dest.stem);project.mkdir(parents=True,exist_ok=False);safe_extract(z,project)
                meta=json.loads((project/'project.json').read_text(encoding='utf-8'))
                if meta.get('format')!='editor-movil-package' or int(meta.get('version',0))<2:raise ValueError('Formato de paquete no compatible')
                STATE['last_project']=str(project)
                self.send(200,json.dumps({'message':'ZIP recibido y descomprimido. Elige la narración y renderiza más abajo.','project':project.name},ensure_ascii=False),'application/json')
            except Exception as e:
                shutil.rmtree(project,ignore_errors=True) if 'project' in locals() else None
                self.send(400,json.dumps({'error':'No se pudo importar el ZIP: '+str(e)},ensure_ascii=False),'application/json')
            return
        if path=='/render':
            if not STATE.get('last_project'):self.send(400,json.dumps({'error':'Primero importa un ZIP'}),'application/json');return
            try:
                data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));proj=Path(STATE['last_project'])
                audio,assets,scenes,aspect=prepare_render(proj,data.get('audio',''),data.get('aspect','horizontal'))
                if STATE.get('render') and STATE['render'].poll() is None:raise ValueError('Ya hay un render en curso')
                out=proj/(proj.name+'_final.mp4');cmd=[sys.executable,str(BASE/'sincronizar_video.py'),str(audio),str(assets),'-o',str(out),'--formato',aspect,'--escenas',str(scenes),'--sin-whisper']
                logpath=proj/'render.log';logpath.write_text('Comando: '+' '.join(cmd)+'\n',encoding='utf-8')
                def run():
                    with logpath.open('a',encoding='utf-8',errors='replace') as log:
                        proc=subprocess.Popen(cmd,cwd=BASE,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));STATE['render']=proc;proc.wait();STATE['render_message']=('Render completado: '+str(out) if proc.returncode==0 else 'Render falló (código '+str(proc.returncode)+'). Revisa el registro.');STATE['log']=logpath.read_text(encoding='utf-8',errors='replace')[-12000:]
                STATE['render_message']='Render iniciado; puedes dejar esta página abierta.';threading.Thread(target=run,daemon=True).start()
                self.send(200,json.dumps({'message':'Render iniciado. El registro aparecerá abajo.'},ensure_ascii=False),'application/json')
            except Exception as e:self.send(400,json.dumps({'error':str(e)},ensure_ascii=False),'application/json')
            return
        self.send(404,'No encontrado')

if __name__=='__main__':
    ip=lan_ip();server=ThreadingHTTPServer(('0.0.0.0',8765),Handler);print('\nEDITOR M2 — PUENTE WI-FI WINDOWS\n');print('En Android abre: http://%s:8765'%ip);print('Móvil y PC deben estar en la misma red Wi-Fi.');print('La primera vez, permite Python en Firewall de Windows para redes privadas.');print('Carpeta de proyectos: %s'%PROJECTS);print('Pulsa Ctrl+C para cerrar.\n');
    try:server.serve_forever()
    except KeyboardInterrupt:print('\nCerrando puente Wi-Fi...')
