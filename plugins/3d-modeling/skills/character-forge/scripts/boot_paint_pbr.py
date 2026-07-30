import urllib.request, tarfile, io, subprocess, sys, os, time, re
import http.server, threading

os.makedirs('/workspace/out', exist_ok=True)
os.makedirs('/workspace/in', exist_ok=True)
def st(s): open('/workspace/out/status.txt', 'w').write(s)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory='/workspace/out', **k)
    def do_PUT(self):
        name = os.path.basename(self.path)
        if not re.fullmatch(r'[a-z0-9_]+\.(png|obj|glb|txt)', name):
            self.send_response(400); self.end_headers(); return
        n = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(n)
        open('/workspace/in/' + name, 'wb').write(data)
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
    do_POST = do_PUT
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(('0.0.0.0', 8000), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def fetch(url, timeout=300, tries=4):
    """Downloads from GitHub DO get truncated mid-stream (IncompleteRead).
    An unretried fetch turns a transient blip into a wasted pod."""
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


def run(name, cmd, cwd=None, timeout=2400, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout, env=e)
    open('/workspace/out/err-' + name + '.txt', 'w').write(
        'RC=' + str(r.returncode) + '\n--STDOUT--\n' + r.stdout[-5000:] +
        '\n--STDERR--\n' + r.stderr[-8000:])
    if r.returncode: raise RuntimeError(name + ' rc=' + str(r.returncode))

os.chdir('/workspace')
try:
    st('gpu-check')
    import torch
    assert torch.cuda.is_available(), 'NO CUDA on this machine'
    st('fetch-repo')
    data = fetch('https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/archive/refs/heads/main.tar.gz', timeout=300)
    tarfile.open(fileobj=io.BytesIO(data)).extractall('/workspace')
    R = '/workspace/Hunyuan3D-2.1-main'
    st('apt-libs')
    run('apt', ['bash', '-c', 'apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libglib2.0-0 libopengl0 libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libsm6 libice6 libxkbcommon0'])
    st('pip-hy21')
    run('pip', [sys.executable, '-m', 'pip', 'install', '-q',
                'transformers==4.46.0', 'diffusers==0.30.0', 'accelerate==1.1.1',
                'pytorch-lightning==1.9.5', 'huggingface-hub==0.30.2',
                'safetensors==0.4.4', 'numpy==1.26.4', 'einops==0.8.0',
                'opencv-python-headless', 'imageio==2.36.0', 'scikit-image',
                'trimesh', 'pymeshlab', 'pygltflib', 'xatlas', 'rembg',
                'onnxruntime', 'omegaconf', 'tqdm', 'ninja', 'pybind11',
                'peft', 'sentencepiece', 'bpy==4.2.0', 'realesrgan==0.3.0', 'basicsr==1.4.2', 'fast_simplification'])
    st('compile-rast')
    # Build the rasterizer for EVERY card the orchestrator may fall back to,
    # not just the 4090 (8.9). Landing on an A6000/A40/3090 (8.6) with an
    # 8.9-only kernel fails at render time with "no kernel image is
    # available for execution on the device" — after the pod has already
    # paid for the whole compile.
    run('rast', [sys.executable, 'setup.py', 'install'],
        cwd=R + '/hy3dpaint/custom_rasterizer',
        env={'TORCH_CUDA_ARCH_LIST': '8.0;8.6;8.9'})
    st('compile-renderer')
    run('rend', ['bash', 'compile_mesh_painter.sh'],
        cwd=R + '/hy3dpaint/DifferentiableRenderer')
    st('fetch-esrgan')
    os.makedirs(R + '/hy3dpaint/ckpt', exist_ok=True)
    data = fetch('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth', timeout=600)
    open(R + '/hy3dpaint/ckpt/RealESRGAN_x4plus.pth', 'wb').write(data)
    st('await-files')
    need = ['mesh.obj', 'ref.png', 'done.txt']
    deadline = time.time() + 1500
    while time.time() < deadline:
        if all(os.path.exists('/workspace/in/' + f) for f in need):
            break
        time.sleep(3)
    else:
        raise RuntimeError('input files never arrived')
    gen = '''
import sys, os
os.chdir('/workspace/Hunyuan3D-2.1-main')
sys.path.insert(0, '/workspace/Hunyuan3D-2.1-main')
sys.path.insert(0, './hy3dshape')
sys.path.insert(0, './hy3dpaint')
try:
    from torchvision_fix import apply_fix
    apply_fix()
except Exception as e:
    print('torchvision fix skipped:', e)
from textureGenPipeline import Hunyuan3DPaintPipeline, Hunyuan3DPaintConfig
conf = Hunyuan3DPaintConfig(max_num_view=6, resolution=512)
conf.realesrgan_ckpt_path = "hy3dpaint/ckpt/RealESRGAN_x4plus.pth"
conf.multiview_cfg_path = "hy3dpaint/cfgs/hunyuan-paint-pbr.yaml"
conf.custom_pipeline = "hy3dpaint/hunyuanpaintpbr"
pipe = Hunyuan3DPaintPipeline(conf)
out = pipe(mesh_path='/workspace/in/mesh.obj',
           image_path='/workspace/in/ref.png',
           output_mesh_path='/workspace/out/pbr_textured.glb', use_remesh=False)
print('painted ->', out)
'''
    open('/workspace/gen.py', 'w').write(gen)
    st('paint-pbr')
    run('gen', [sys.executable, '/workspace/gen.py'], timeout=3000,
        env={'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True'})
    assert os.path.exists('/workspace/out/pbr_textured.glb'), 'no output'
    assert os.path.getsize('/workspace/out/pbr_textured.glb') > 300000, 'degenerate output'
    st('done')
    open('/workspace/out/DONE', 'w').write('ok')
except Exception as e:
    st('FAIL: ' + repr(e)[:300])
time.sleep(3600)
