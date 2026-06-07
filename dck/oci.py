import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

DCK_DIR = Path.home() / ".dck"
IMAGES_DIR = DCK_DIR / "images"
REGISTRY_URL = "https://registry-1.docker.io/v2"


def _get_auth_token(image, scope="pull"):
    url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{image}:{scope}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()["token"]
    except Exception as e:
        raise RuntimeError(f"Auth failed for {image}: {e}")


def _registry_request(method, path, image, token, headers=None, stream=False, timeout=30):
    if not token:
        token = _get_auth_token(image)
    url = urljoin(REGISTRY_URL + "/", f"{image}/{path}")
    req_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json",
    }
    if headers:
        req_headers.update(headers)
    r = requests.request(method, url, headers=req_headers, stream=stream, timeout=timeout)
    if r.status_code == 401:
        token = _get_auth_token(image)
        req_headers["Authorization"] = f"Bearer {token}"
        r = requests.request(method, url, headers=req_headers, stream=stream, timeout=timeout)
    r.raise_for_status()
    return r, token


def _stream_blob(image, digest, token, dest_path, progress_callback=None):
    url = urljoin(REGISTRY_URL + "/", f"{image}/blobs/{digest}")
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, stream=True, timeout=60)
    if r.status_code == 401:
        token = _get_auth_token(image)
        headers["Authorization"] = f"Bearer {token}"
        r = requests.get(url, headers=headers, stream=True, timeout=60)
    r.raise_for_status()

    total = int(r.headers.get("Content-Length", 0))
    downloaded = 0
    start = time.time()

    digest_short = digest.split(":")[1][:12]
    size_mb = total / 1024 / 1024
    last_report = [0.0]

    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if progress_callback and total > 0 and (now - last_report[0] >= 1.0 or downloaded == total):
                    last_report[0] = now
                    elapsed = now - start
                    speed = downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    pct = downloaded * 100 / total
                    done_mb = downloaded / 1024 / 1024
                    progress_callback(f"[{done_mb:.1f}/{size_mb:.1f}MB] {digest_short} ({pct:.0f}% @ {speed:.1f}MB/s)")

    return token


def _ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def pull_image(image, tag="latest", progress_callback=None):
    image = image.replace("docker.io/", "").replace("library/", "")
    if "/" not in image:
        image = f"library/{image}"

    img_dir = IMAGES_DIR / image.replace("/", "_") / tag
    layers_dir = img_dir / "layers"
    rootfs_dir = img_dir / "rootfs"
    _ensure_dir(layers_dir)
    _ensure_dir(rootfs_dir)

    if progress_callback:
        progress_callback("Authenticating...")
    token = _get_auth_token(image)

    if progress_callback:
        progress_callback("Fetching manifest...")
    r, token = _registry_request("GET", f"manifests/{tag}", image, token)
    manifest = r.json()

    if manifest.get("mediaType") in (
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.index.v1+json",
    ):
        amd64 = [m for m in manifest.get("manifests", [])
                 if m.get("platform", {}).get("architecture") == "amd64"]
        if not amd64:
            raise RuntimeError("No amd64 image found in manifest list")
        r, token = _registry_request("GET", f"manifests/{amd64[0]['digest']}", image, token)
        manifest = r.json()

    if progress_callback:
        progress_callback("Downloading config...")
    config_digest = manifest["config"]["digest"]
    cfg_path = layers_dir / config_digest.replace(":", "_")
    _stream_blob(image, config_digest, token, cfg_path, progress_callback=None)
    config = json.loads(cfg_path.read_bytes())

    (img_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (img_dir / "config.json").write_text(json.dumps(config, indent=2))

    layers = manifest.get("layers", [])
    total = len(layers)

    for i, layer in enumerate(layers):
        digest = layer["digest"]
        short_digest = digest.split(":")[1][:12]
        layer_file = layers_dir / digest.replace(":", "_")

        if not layer_file.exists():
            if progress_callback:
                progress_callback(f"Downloading layer {i+1}/{total}: {short_digest}...")
            token = _stream_blob(image, digest, token, layer_file, progress_callback=progress_callback)

        if layer.get("mediaType", "").endswith("tar.gzip") or layer.get("mediaType", "").endswith("gzip"):
            if progress_callback:
                progress_callback(f"Extracting layer {i+1}/{total}: {short_digest}...")
            import tarfile
            with tarfile.open(str(layer_file), "r:gz") as tar:
                tar.extractall(path=str(rootfs_dir))

    if progress_callback:
        progress_callback("Done")

    return {
        "image": image,
        "tag": tag,
        "config": config,
        "manifest": manifest,
        "rootfs": str(rootfs_dir),
        "cmd": config.get("config", {}).get("Cmd", []),
        "env": config.get("config", {}).get("Env", []),
        "working_dir": config.get("config", {}).get("WorkingDir", "/"),
        "entrypoint": config.get("config", {}).get("Entrypoint", []),
        "exposed_ports": config.get("config", {}).get("ExposedPorts", {}),
    }


def list_images():
    images = []
    if not IMAGES_DIR.exists():
        return images
    for img_dir in sorted(IMAGES_DIR.iterdir()):
        if not img_dir.is_dir():
            continue
        for tag_dir in sorted(img_dir.iterdir()):
            if not tag_dir.is_dir():
                continue
            config_file = tag_dir / "config.json"
            config = {}
            if config_file.exists():
                try:
                    config = json.loads(config_file.read_text())
                except Exception:
                    pass
            cmd = config.get("config", {}).get("Cmd", [])
            images.append({
                "name": img_dir.name.replace("_", "/"),
                "tag": tag_dir.name,
                "cmd": " ".join(cmd) if cmd else "-",
                "rootfs": str(tag_dir / "rootfs"),
            })
    return images


def remove_image(image, tag="latest"):
    img_dir = IMAGES_DIR / image.replace("/", "_") / tag
    if not img_dir.exists():
        return False
    import shutil
    shutil.rmtree(str(img_dir))
    return True
