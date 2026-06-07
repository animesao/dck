"""OCI image puller: download images from Docker Hub without Docker daemon."""

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

from dck.i18n import t

DCK_DIR = Path.home() / ".dck"
IMAGES_DIR = DCK_DIR / "images"
AUTH_URL = "https://auth.docker.io/token"
REGISTRY_URL = "https://registry-1.docker.io/v2"


def _get_auth_token(image, scope="pull"):
    realm = "https://auth.docker.io/token"
    service = "registry.docker.io"
    url = f"{realm}?service={service}&scope=repository:{image}:{scope}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()["token"]
    except Exception as e:
        raise RuntimeError(f"Auth failed for {image}: {e}")


def _registry_get(path, image, token=None):
    if not token:
        token = _get_auth_token(image)
    url = urljoin(REGISTRY_URL + "/", f"{image}/{path}")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json",
    }
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 401:
        token = _get_auth_token(image)
        headers["Authorization"] = f"Bearer {token}"
        r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r, token


def _get_blob(image, digest, token):
    """Download a blob (layer/config) by digest."""
    r, token = _registry_get(f"blobs/{digest}", image, token)
    return r.content, token


def _ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def _extract_tar(tar_path, dest):
    """Extract a tar.gz file to destination."""
    import tarfile
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=dest)


def pull_image(image, tag="latest", progress_callback=None):
    """Pull an OCI image from Docker Hub and extract layers."""
    image = image.replace("docker.io/", "").replace("library/", "")
    if "/" not in image:
        image = f"library/{image}"

    img_dir = IMAGES_DIR / image.replace("/", "_") / tag
    layers_dir = img_dir / "layers"
    rootfs_dir = img_dir / "rootfs"
    _ensure_dir(layers_dir)
    _ensure_dir(rootfs_dir)

    if progress_callback:
        progress_callback(f"Authenticating...")

    token = _get_auth_token(image)

    if progress_callback:
        progress_callback(f"Fetching manifest...")

    manifest_data, token = _registry_get(f"manifests/{tag}", image, token)
    if isinstance(manifest_data, tuple):
        manifest_data = manifest_data[0]
    manifest = manifest_data.json() if hasattr(manifest_data, 'json') else json.loads(manifest_data)

    if manifest.get("mediaType") == "application/vnd.docker.distribution.manifest.list.v2+json" or manifest.get("mediaType") == "application/vnd.oci.image.index.v1+json":
        amd64 = [m for m in manifest.get("manifests", [])
                 if m.get("platform", {}).get("architecture") == "amd64"]
        if not amd64:
            raise RuntimeError("No amd64 image found in manifest list")
        digest = amd64[0]["digest"]
        manifest, token = _registry_get(f"manifests/{digest}", image, token)
        manifest = manifest.json() if hasattr(manifest, 'json') else manifest

    if progress_callback:
        progress_callback(f"Downloading config...")

    config_digest = manifest["config"]["digest"]
    config_data, token = _get_blob(image, config_digest, token)
    config = json.loads(config_data)

    img_dir = IMAGES_DIR / image.replace("/", "_") / tag
    (img_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (img_dir / "config.json").write_text(json.dumps(config, indent=2))

    layers = manifest.get("layers", [])
    total = len(layers)

    for i, layer in enumerate(layers):
        digest = layer["digest"]
        short_digest = digest.split(":")[1][:12]
        layer_file = layers_dir / digest.replace(":", "_")

        if progress_callback:
            progress_callback(f"Layer {i+1}/{total}: {short_digest}")

        if not layer_file.exists():
            data, token = _get_blob(image, digest, token)
            layer_file.write_bytes(data)

        if layer.get("mediaType", "").endswith("tar.gzip") or layer.get("mediaType", "").endswith("gzip"):
            if progress_callback:
                progress_callback(f"Extracting layer {i+1}/{total}: {short_digest}")
            import tarfile
            import io
            with tarfile.open(fileobj=io.BytesIO(layer_file.read_bytes()), mode="r:gz") as tar:
                tar.extractall(path=str(rootfs_dir))

    if progress_callback:
        progress_callback(f"Done")

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
    """List locally stored images."""
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
    """Remove a locally stored image."""
    img_dir = IMAGES_DIR / image.replace("/", "_") / tag
    if not img_dir.exists():
        return False
    import shutil
    shutil.rmtree(str(img_dir))
    return True
