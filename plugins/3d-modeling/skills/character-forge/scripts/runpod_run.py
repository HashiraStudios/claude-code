#!/usr/bin/env python3
"""RunPod orchestrator for Character Forge — deploy, feed, fetch, ALWAYS terminate.

  python runpod_run.py shape --views work/char/views --out work/char/shape.glb
  python runpod_run.py paint --mesh work/char/retopo.obj --ref work/char/concept.png --out work/char/painted.glb

Pattern (battle-tested over ~20 rounds): SECURE cloud RTX 4090, official
pytorch image, base64 boot script in dockerArgs, gpu fail-fast, in-pod
HTTP PUT upload endpoint, status.txt polling through the RunPod proxy,
deadline-bounded monitor that terminates the pod no matter what.
Requires RUNPOD_API_KEY."""
import argparse, base64, json, os, sys, time, urllib.request, urllib.error

KEY = os.environ.get("RUNPOD_API_KEY") or sys.exit("set RUNPOD_API_KEY")
GQL = "https://api.runpod.io/graphql"
HERE = os.path.dirname(os.path.abspath(__file__))

MODES = {
    "shape": dict(boot="boot_shape_mv.py",
                  image="pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime",
                  disk=40, await_status="await-views", result="hy_mv.glb",
                  errs=["err-gen.txt", "err-pip.txt"], deadline=2700),
    "paint": dict(boot="boot_paint_pbr.py",
                  image="pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel",
                  disk=60, await_status="await-files", result="pbr_textured.glb",
                  errs=["err-gen.txt", "err-rast.txt", "err-pip.txt"], deadline=3600),
}


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(GQL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {KEY}"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def deploy(mode, name):
    boot = open(os.path.join(HERE, MODES[mode]["boot"]), "rb").read()
    b64 = base64.b64encode(boot).decode()
    args = f"bash -c 'echo {b64} | base64 -d > /workspace/r.py; python /workspace/r.py'"
    q = ("mutation Deploy($args: String) {\n  podFindAndDeployOnDemand(input: {\n"
         "    cloudType: SECURE, gpuCount: 1, gpuTypeId: \"NVIDIA GeForce RTX 4090\",\n"
         f"    name: \"{name}\",\n    imageName: \"{MODES[mode]['image']}\",\n"
         f"    containerDiskInGb: {MODES[mode]['disk']}, volumeInGb: 0, ports: \"8000/http\",\n"
         "    dockerArgs: $args\n  }) { id machineId } }")
    d = gql(q, {"args": args})
    pod = d["data"]["podFindAndDeployOnDemand"]
    print(f"pod {pod['id']} on machine {pod['machineId']}")
    return pod["id"]


def http(url, data=None, method="GET", timeout=120):
    req = urllib.request.Request(url, data=data, method=method)
    return urllib.request.urlopen(req, timeout=timeout).read()


def put_file(base, remote_name, local_path):
    data = open(local_path, "rb").read()
    http(f"{base}/up/{remote_name}", data=data, method="PUT", timeout=180)
    print(f"  uploaded {remote_name} ({len(data)} bytes)")


def run(mode, uploads, out_path):
    pod = deploy(mode, f"charforge-{mode}-{int(time.time()) % 100000}")
    base = f"https://{pod}-8000.proxy.runpod.net"
    spec = MODES[mode]
    uploaded = False
    t0 = time.time()
    no_container_since = time.time()
    try:
        while time.time() - t0 < spec["deadline"]:
            try:
                st = http(f"{base}/status.txt", timeout=15).decode()[:120]
                no_container_since = None
            except Exception:
                st = "<no container>"
                if no_container_since is None:
                    no_container_since = time.time()
                elif time.time() - no_container_since > 720:
                    print("no container for 12 min — broken machine, aborting (re-run to re-roll)")
                    return False
            print(f"{time.strftime('%H:%M:%S')} {st}")
            if st == spec["await_status"] and not uploaded:
                for remote, local in uploads.items():
                    put_file(base, remote, local)
                http(f"{base}/up/done.txt", data=b"ok", method="PUT", timeout=30)
                uploaded = True
            if st == "done" or st.startswith("FAIL"):
                try:
                    data = http(f"{base}/{spec['result']}", timeout=600)
                    open(out_path, "wb").write(data)
                    print(f"fetched {out_path} ({len(data)} bytes)")
                except Exception as e:
                    print(f"result fetch failed: {e}")
                for err in spec["errs"]:
                    try:
                        open(out_path + "." + err, "wb").write(http(f"{base}/{err}", timeout=120))
                    except Exception:
                        pass
                # rc=-11 after writing the GLB is a benign bpy exit segfault:
                ok = os.path.exists(out_path) and os.path.getsize(out_path) > 300000
                print("RESULT OK" if ok else f"RESULT BAD (status {st}; see {out_path}.err-*.txt)")
                return ok
            time.sleep(30)
        print("deadline reached")
        return False
    finally:
        gql(f'mutation {{ podTerminate(input: {{podId: "{pod}"}}) }}')
        print(f"pod {pod} terminated")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["shape", "paint"])
    ap.add_argument("--views", help="shape: dir with front/left/back/right.png")
    ap.add_argument("--mesh", help="paint: retopo OBJ")
    ap.add_argument("--ref", help="paint: reference/concept image")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.mode == "shape":
        assert a.views, "--views required"
        uploads = {f"{v}.png": os.path.join(a.views, f"{v}.png")
                   for v in ("front", "left", "back", "right")}
    else:
        assert a.mesh and a.ref, "--mesh and --ref required"
        uploads = {"mesh.obj": a.mesh, "ref.png": a.ref}
    sys.exit(0 if run(a.mode, uploads, a.out) else 1)


if __name__ == "__main__":
    main()
