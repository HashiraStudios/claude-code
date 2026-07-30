import urllib.request, tarfile, io, subprocess, sys, os, time, re, glob
import http.server, threading

os.makedirs('/workspace/out', exist_ok=True)
os.makedirs('/workspace/views', exist_ok=True)
def st(s): open('/workspace/out/status.txt', 'w').write(s)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory='/workspace/out', **k)
    def do_PUT(self):
        name = os.path.basename(self.path)
        if not re.fullmatch(r'[a-z0-9_]+\.(png|txt)', name):
            self.send_response(400); self.end_headers(); return
        n = int(self.headers.get('Content-Length', 0))
        open('/workspace/views/' + name, 'wb').write(self.rfile.read(n))
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
    do_POST = do_PUT
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(('0.0.0.0', 8000), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def fetch(url, timeout=300, tries=4):
    for i in range(tries):
        try:
            d = urllib.request.urlopen(url, timeout=timeout).read()
            if len(d) < 1000:
                raise RuntimeError('suspiciously small download: %d bytes' % len(d))
            return d
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def run(name, cmd, cwd=None, timeout=7200):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    open('/workspace/out/err-' + name + '.txt', 'w').write(
        'RC=' + str(r.returncode) + '\n--STDOUT--\n' + r.stdout[-8000:] +
        '\n--STDERR--\n' + r.stderr[-8000:])
    return r.returncode

os.chdir('/workspace')
try:
    st('gpu-check')
    import torch
    assert torch.cuda.is_available(), 'NO CUDA on this machine'
    st('fetch-repo')
    data = fetch('https://github.com/Tencent-Hunyuan/Hunyuan3D-2/archive/refs/heads/main.tar.gz')
    tarfile.open(fileobj=io.BytesIO(data)).extractall('/workspace')
    st('apt-libs')
    run('apt', ['bash', '-c', 'apt-get update -qq && apt-get install -y -qq '
                '--no-install-recommends libgl1 libglib2.0-0'])
    st('pip-hy')
    run('pip', [sys.executable, '-m', 'pip', 'install', '-q',
                'diffusers', 'einops', 'opencv-python-headless', 'numpy==1.26.4',
                'transformers==4.44.2', 'torchvision', 'omegaconf', 'tqdm', 'trimesh',
                'pymeshlab', 'pygltflib', 'accelerate', 'safetensors',
                'huggingface_hub', 'rembg', 'onnxruntime', 'scikit-image'])

    st('await-views')
    deadline = time.time() + 1800
    while time.time() < deadline:
        if os.path.exists('/workspace/views/done.txt') and \
           os.path.exists('/workspace/views/parts.txt'):
            break
        time.sleep(3)
    else:
        raise RuntimeError('views never arrived')
    parts = [p for p in open('/workspace/views/parts.txt').read().split() if p]
    missing = [f'{p}_{v}.png' for p in parts for v in ('front', 'left', 'back', 'right')
               if not os.path.exists(f'/workspace/views/{p}_{v}.png')]
    assert not missing, 'missing view files: ' + ','.join(missing[:8])
    open('/workspace/out/kit.txt', 'w').write(f'{len(parts)} parts: ' + ','.join(parts))

    # The whole point of a batch pod: load the pipeline ONCE and run the
    # queue through it. Per-part pods would pay this load (and the pip
    # install, and the boot) once per part.
    gen = '''
import sys, os, torch, traceback
sys.path.insert(0, '/workspace/Hunyuan3D-2-main')
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
parts = [p for p in open('/workspace/views/parts.txt').read().split() if p]
rembg = BackgroundRemover()
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    'tencent/Hunyuan3D-2mv', subfolder='hunyuan3d-dit-v2-mv', variant='fp16')
ok, bad = [], []
for i, part in enumerate(parts, 1):
    try:
        views = {v: rembg(Image.open(f'/workspace/views/{part}_{v}.png').convert('RGB'))
                 for v in ('front', 'left', 'back', 'right')}
        mesh = pipe(image=views, num_inference_steps=50, octree_resolution=512,
                    num_chunks=20000, generator=torch.manual_seed(7),
                    output_type='trimesh')[0]
        out = f'/workspace/out/parts/{part}.glb'
        os.makedirs('/workspace/out/parts', exist_ok=True)
        mesh.export(out)
        sz = os.path.getsize(out)
        # one bad part must not sink the kit: record and carry on
        (ok if sz > 200000 else bad).append(part)
        print(f'[{i}/{len(parts)}] {part}: {len(mesh.faces)} faces, {sz} bytes', flush=True)
        open('/workspace/out/progress.txt', 'w').write(f'{i}/{len(parts)} {part}')
    except Exception:
        traceback.print_exc()
        bad.append(part)
print('OK:', ','.join(ok))
print('BAD:', ','.join(bad))
'''
    open('/workspace/gen.py', 'w').write(gen)
    st('gen-kit')
    rc = run('gen', [sys.executable, '/workspace/gen.py'])

    st('pack')
    globs = glob.glob('/workspace/out/parts/*.glb')
    assert globs, 'no part produced (gen rc=%d)' % rc
    with tarfile.open('/workspace/out/kit.tar.gz', 'w:gz') as tf:
        for g in globs:
            tf.add(g, arcname='parts/' + os.path.basename(g))
    open('/workspace/out/count.txt', 'w').write(
        '%d/%d parts produced (gen rc=%d)' % (len(globs), len(parts), rc))
    st('done')
except Exception as e:
    open('/workspace/out/err-fatal.txt', 'w').write(repr(e)[:8000])
    st('FAIL: ' + repr(e)[:200])
time.sleep(36000)
