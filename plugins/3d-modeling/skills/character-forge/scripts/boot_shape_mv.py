import urllib.request, tarfile, io, subprocess, sys, os, time, re
import http.server, threading

os.makedirs('/workspace/out', exist_ok=True)
os.makedirs('/workspace/views', exist_ok=True)
def st(s): open('/workspace/out/status.txt', 'w').write(s)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory='/workspace/out', **k)
    def do_PUT(self):
        name = os.path.basename(self.path)
        if not re.fullmatch(r'[a-z_]+\.(png|txt)', name):
            self.send_response(400); self.end_headers(); return
        n = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(n)
        open('/workspace/views/' + name, 'wb').write(data)
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
    do_POST = do_PUT
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(('0.0.0.0', 8000), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def run(name, cmd, cwd=None, timeout=2400):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    open('/workspace/out/err-' + name + '.txt', 'w').write(
        'RC=' + str(r.returncode) + '\n--STDOUT--\n' + r.stdout[-4000:] +
        '\n--STDERR--\n' + r.stderr[-6000:])
    if r.returncode: raise RuntimeError(name + ' rc=' + str(r.returncode))

os.chdir('/workspace')
try:
    st('gpu-check')
    import torch
    assert torch.cuda.is_available(), 'NO CUDA on this machine'
    st('fetch-repo')
    data = urllib.request.urlopen('https://github.com/Tencent-Hunyuan/Hunyuan3D-2/archive/refs/heads/main.tar.gz', timeout=300).read()
    tarfile.open(fileobj=io.BytesIO(data)).extractall('/workspace')
    st('apt-libs')
    run('apt', ['bash', '-c', 'apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libglib2.0-0'])
    st('pip-hy')
    run('pip', [sys.executable, '-m', 'pip', 'install', '-q',
                'diffusers', 'einops', 'opencv-python-headless', 'numpy==1.26.4',
                'transformers==4.44.2', 'torchvision', 'omegaconf', 'tqdm', 'trimesh',
                'pymeshlab', 'pygltflib', 'accelerate', 'safetensors',
                'huggingface_hub', 'rembg', 'onnxruntime', 'scikit-image'])
    st('await-views')
    need = ['front.png', 'left.png', 'back.png', 'right.png', 'done.txt']
    deadline = time.time() + 1500
    while time.time() < deadline:
        if all(os.path.exists('/workspace/views/' + f) for f in need):
            break
        time.sleep(3)
    else:
        raise RuntimeError('views never arrived')
    gen = '''
import sys, torch
sys.path.insert(0, '/workspace/Hunyuan3D-2-main')
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
rembg = BackgroundRemover()
views = {}
for v in ('front', 'left', 'back', 'right'):
    img = Image.open('/workspace/views/' + v + '.png').convert('RGB')
    views[v] = rembg(img)
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    'tencent/Hunyuan3D-2mv', subfolder='hunyuan3d-dit-v2-mv', variant='fp16')
mesh = pipe(image=views, num_inference_steps=50, octree_resolution=512,
            num_chunks=20000, generator=torch.manual_seed(7),
            output_type='trimesh')[0]
mesh.export('/workspace/out/hy_mv.glb')
print('faces', len(mesh.faces), 'verts', len(mesh.vertices))
'''
    open('/workspace/gen.py', 'w').write(gen)
    st('hy-mv-gen')
    run('gen', [sys.executable, '/workspace/gen.py'])
    assert os.path.exists('/workspace/out/hy_mv.glb'), 'no output'
    assert os.path.getsize('/workspace/out/hy_mv.glb') > 500000, 'degenerate output'
    st('done')
    open('/workspace/out/DONE', 'w').write('ok')
except Exception as e:
    st('FAIL: ' + repr(e)[:300])
time.sleep(3600)
