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
# Cloudflare fronts the RunPod API and rejects the default Python-urllib
# agent with "error code: 1010" (403). curl passes, urllib does not — so
# every request here must carry a real User-Agent or nothing deploys.
UA = "curl/8.5.0"
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
    # Kit mode: many parts through ONE pod. The model load, pip install and
    # boot are paid once instead of once per part, which is what makes a
    # 10-part kit affordable at all.
    "shape_kit": dict(boot="boot_shape_kit.py",
                      image="pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime",
                      disk=60, await_status="await-views", result="kit.tar.gz",
                      errs=["err-gen.txt", "err-pip.txt", "err-fatal.txt",
                            "count.txt", "kit.txt"], deadline=9000),
}


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(GQL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {KEY}",
                                          "User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


# Tried in order. The 4090 is the cheapest card that fits these models, but
# SECURE capacity for it runs out and the API then returns a NULL pod
# instead of an error — which used to crash the orchestrator with a
# TypeError. Any 24GB+ card runs this pipeline.
GPUS = ["NVIDIA GeForce RTX 4090", "NVIDIA RTX A6000", "NVIDIA A40",
        "NVIDIA GeForce RTX 3090", "NVIDIA RTX A5000"]
# RunPod keeps handing back the same machine while it is the only free
# unit of a type — including a BROKEN one that never starts containers.
# The capacity fallback can't see that, so RUNPOD_GPUS lets a caller
# steer around a bad tier: a comma-separated list that overrides GPUS.
if os.environ.get("RUNPOD_GPUS"):
    GPUS = [g.strip() for g in os.environ["RUNPOD_GPUS"].split(",") if g.strip()]


def deploy(mode, name):
    boot = open(os.path.join(HERE, MODES[mode]["boot"]), "rb").read()
    b64 = base64.b64encode(boot).decode()
    args = f"bash -c 'echo {b64} | base64 -d > /workspace/r.py; python /workspace/r.py'"
    for gpu in GPUS:
        q = ("mutation Deploy($args: String) {\n  podFindAndDeployOnDemand(input: {\n"
             f"    cloudType: SECURE, gpuCount: 1, gpuTypeId: \"{gpu}\",\n"
             f"    name: \"{name}\",\n    imageName: \"{MODES[mode]['image']}\",\n"
             f"    containerDiskInGb: {MODES[mode]['disk']}, volumeInGb: 0, ports: \"8000/http\",\n"
             "    dockerArgs: $args\n  }) { id machineId } }")
        pod = (gql(q, {"args": args}).get("data") or {}).get("podFindAndDeployOnDemand")
        if pod:
            print(f"pod {pod['id']} on machine {pod['machineId']} ({gpu})")
            return pod["id"]
        print(f"no capacity for {gpu}, trying next")
    sys.exit("no GPU capacity on any candidate type — try again later")


def http(url, data=None, method="GET", timeout=120):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": UA})
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
                # Uploads are the only large payloads here and the proxy DOES
                # reset them mid-handshake. Never let that kill the run: the
                # pod is still waiting, so a failure just retries next poll.
                # (An unguarded upload once crashed the orchestrator, whose
                # finally-block then terminated a perfectly healthy pod.)
                try:
                    for remote, local in uploads.items():
                        put_file(base, remote, local)
                    http(f"{base}/up/done.txt", data=b"ok", method="PUT", timeout=30)
                    uploaded = True
                except Exception as e:
                    print(f"  upload failed ({e}) — retrying next poll")
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
                floor = 20000 if mode == "shape_kit" else 300000
                ok = os.path.exists(out_path) and os.path.getsize(out_path) > floor
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
    ap.add_argument("mode", choices=["shape", "paint", "shape_kit"])
    ap.add_argument("--kit", help="shape_kit: dir with <part>/views/*.png")
    ap.add_argument("--views", help="shape: dir with front/left/back/right.png")
    ap.add_argument("--mesh", help="paint: retopo OBJ")
    ap.add_argument("--ref", help="paint: reference/concept image")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.mode == "shape_kit":
        assert a.kit, "--kit required"
        parts = sorted(d for d in os.listdir(a.kit)
                       if os.path.isdir(os.path.join(a.kit, d, "views")))
        assert parts, f"no parts with views/ under {a.kit}"
        uploads = {}
        for p in parts:
            for v in ("front", "left", "back", "right"):
                uploads[f"{p}_{v}.png"] = os.path.join(a.kit, p, "views", f"{v}.png")
        manifest = os.path.join(a.kit, "parts.txt")
        open(manifest, "w").write("\n".join(parts))
        uploads["parts.txt"] = manifest
        print(f"kit: {len(parts)} parts, {len(uploads)} files")
    elif a.mode == "shape":
        assert a.views, "--views required"
        uploads = {f"{v}.png": os.path.join(a.views, f"{v}.png")
                   for v in ("front", "left", "back", "right")}
    else:
        assert a.mesh and a.ref, "--mesh and --ref required"
        uploads = {"mesh.obj": a.mesh, "ref.png": a.ref}
    sys.exit(0 if run(a.mode, uploads, a.out) else 1)


if __name__ == "__main__":
    main()
