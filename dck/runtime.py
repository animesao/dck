import ctypes
import fcntl
import hashlib
import json
import os
import select
import shutil
import signal
import subprocess
import tarfile
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin

import requests

DCK_DIR = Path.home() / ".dck"
IMAGES_DIR = DCK_DIR / "images"
CONTAINERS_DIR = DCK_DIR / "containers"
LOGS_DIR = DCK_DIR / "logs"
OVERLAY_DIR = DCK_DIR / "overlay"
CGROUP_DIR = Path("/sys/fs/cgroup/dck")
EGGS_DIR = DCK_DIR / "eggs"
NET_IPS_FILE = DCK_DIR / "network_ips.json"
BRIDGE_NAME = "dck0"
BRIDGE_SUBNET = "10.0.0.0/24"
BRIDGE_GATEWAY = "10.0.0.1"
CGROUP_ENABLED = Path("/sys/fs/cgroup/cgroup.controllers").exists()

NS = {
    "mnt": 0x00020000, "pid": 0x20000000, "net": 0x40000000,
    "uts": 0x04000000, "ipc": 0x08000000, "cgroup": 0x02000000,
}


def _ensure(p):
    Path(p).mkdir(parents=True, exist_ok=True)


def _log(lf, msg):
    if lf:
        try:
            with open(lf, "a") as f:
                f.write(msg + "\n")
        except Exception:
            pass


# ── PRESETS ────────────────────────────────────────────────────────────

PRESETS = {
    "paper": {
        "image": "itzg/minecraft-server:latest",
        "ports": ["25565:25565/udp", "25565:25565"],
        "env": {
            "EULA": "TRUE", "TYPE": "PAPER",
            "MAX_PLAYERS": "{max_players or 20}",
            "DIFFICULTY": "{difficulty or normal}",
            "MODE": "{mode or survival}",
            "MEMORY": "{ram}",
            "VIEW_DISTANCE": "10",
            "ONLINE_MODE": "true",
            "PVP": "true",
            "ALLOW_FLIGHT": "false",
            "GENERATE_STRUCTURES": "true",
            "SPAWN_ANIMALS": "true",
            "SPAWN_MONSTERS": "true",
            "SPAWN_NPCS": "true",
            "LEVEL_TYPE": "default",
            "ENABLE_RCON": "false",
            "MAX_TICK_TIME": "-1",
        },
        "volumes": ["{volume or server_data}:/data"],
        "restart": "unless-stopped",
    },
    "purpur": {
        "image": "itzg/minecraft-server:latest",
        "ports": ["25565:25565/udp", "25565:25565"],
        "env": {
            "EULA": "TRUE", "TYPE": "PURPUR",
            "MAX_PLAYERS": "{max_players or 20}",
            "DIFFICULTY": "{difficulty or normal}",
            "MODE": "{mode or survival}",
            "MEMORY": "{ram}",
            "VIEW_DISTANCE": "10",
            "ONLINE_MODE": "true",
        },
        "volumes": ["{volume or server_data}:/data"],
        "restart": "unless-stopped",
    },
    "forge": {
        "image": "itzg/minecraft-server:latest",
        "ports": ["25565:25565/udp", "25565:25565"],
        "env": {
            "EULA": "TRUE", "TYPE": "FORGE",
            "VERSION": "{version or latest}",
            "MEMORY": "{ram}",
        },
        "volumes": ["{volume or server_data}:/data"],
        "restart": "unless-stopped",
    },
    "spigot": {
        "image": "itzg/minecraft-server:latest",
        "ports": ["25565:25565/udp", "25565:25565"],
        "env": {"EULA": "TRUE", "TYPE": "SPIGOT", "MEMORY": "{ram}"},
        "volumes": ["{volume or server_data}:/data"],
        "restart": "unless-stopped",
    },
    "nginx": {
        "image": "nginx:alpine",
        "env": {"NGINX_HOST": "{host or localhost}"},
    },
    "apache": {
        "image": "httpd:alpine",
    },
    "mariadb": {
        "image": "mariadb:10",
        "env": {
            "MYSQL_ROOT_PASSWORD": "{root_password}",
            "MYSQL_DATABASE": "{database or myapp}",
        },
        "volumes": ["{volume or db_data}:/var/lib/mysql"],
    },
    "postgres": {
        "image": "postgres:alpine",
        "env": {"POSTGRES_PASSWORD": "{password}", "POSTGRES_DB": "{database or myapp}"},
        "volumes": ["{volume or db_data}:/var/lib/postgresql/data"],
    },
    "redis": {
        "image": "redis:alpine",
        "env": {"REDIS_PASSWORD": "{password}"},
    },
    "node": {
        "image": "node:alpine",
        "workdir": "/app",
        "volumes": ["{volume or app_data}:/app"],
    },
    "python": {
        "image": "python:alpine",
        "workdir": "/app",
        "volumes": ["{volume or app_data}:/app"],
    },
    "golang": {
        "image": "golang:alpine",
        "workdir": "/app",
        "volumes": ["{volume or app_data}:/app"],
    },
    "lamp": {
        "image": "lamp:latest",
        "ports": ["80:80", "443:443"],
        "volumes": ["{volume or www_data}:/var/www/html"],
    },
    "rust": {
        "image": "didstopia/rust-server:latest",
        "ports": ["28015:28015/udp", "28016:28016"],
        "env": {"SERVER_NAME": "{server_name or Rust}", "MAX_PLAYERS": "{max_players or 50}"},
        "volumes": ["{volume or rust_data}:/steamcmd/rust"],
    },
    "factorio": {
        "image": "factoriotools/factorio:stable",
        "ports": ["34197:34197/udp"],
        "env": {"GAME_PASSWORD": "{game_password}"},
        "volumes": ["{volume or factorio_data}:/factorio"],
    },
    "terraria": {
        "image": "beardedio/terraria:latest",
        "ports": ["7777:7777/tcp", "7777:7777/udp"],
        "env": {"WORLD_NAME": "{world_name or Terraria}", "MAX_PLAYERS": "{max_players or 8}"},
        "volumes": ["{volume or terraria_data}:/root/.local/share/Terraria"],
    },
}


def resolve_preset(name, params=None):
    if name not in PRESETS:
        raise RuntimeError(f"Unknown preset: {name}. Available: {', '.join(PRESETS)}")
    base = json.loads(json.dumps(PRESETS[name]))
    if not params:
        params = {}
    def fill(v):
        if isinstance(v, str) and "{" in v:
            import re
            return re.sub(r"\{(\w+)\s+or\s+([^}]+)\}", lambda m: str(params.get(m.group(1), m.group(2))), v)
        return v
    for k in ("env",):
        if k in base:
            base[k] = {k2: fill(v2) for k2, v2 in base[k].items()}
    for k in ("ports", "volumes"):
        if k in base:
            base[k] = [fill(v) for v in base[k]]
    return base


# ── EGG (Pterodactyl-style) ───────────────────────────────────────────

def validate_egg(data):
    errors = []
    if "startup" not in data:
        errors.append("Missing 'startup'")
    if "image" not in data:
        errors.append("Missing 'image'")
    for var in data.get("variables", []):
        rules = var.get("rules", "")
        if "required" in rules and "default_value" not in var:
            errors.append(f"Variable '{var.get('env_variable')}' is required but has no default")
    return errors


def apply_egg(egg_data, user_env):
    startup = egg_data["startup"]
    env = dict(egg_data.get("environment", {}))
    env.update(user_env)
    for var in egg_data.get("variables", []):
        e = var["env_variable"]
        default = var.get("default_value", "")
        val = user_env.get(e, default)
        env[e] = val
        startup = startup.replace(f"{{{e}}}", str(val))
    image = egg_data.get("image", "alpine:latest")
    ports = egg_data.get("ports", [])
    volumes = {}
    for k, v in egg_data.get("volumes", {}).items():
        volumes[k] = v
    return {
        "image": image,
        "command": ["/bin/sh", "-c", startup],
        "env": env,
        "ports": ports,
        "volumes": volumes,
    }


def builtin_eggs():
    return {
        "paper": {
            "meta": {"author": "dck", "version": "1.0", "description": "Paper Minecraft server"},
            "startup": "java -Xms{MEMORY}M -Xmx{MEMORY}M -jar server.jar --nogui",
            "stop": "stop",
            "image": "itzg/minecraft-server:latest",
            "environment": {"MEMORY": "1024", "MAX_PLAYERS": "20", "DIFFICULTY": "normal"},
            "variables": [
                {"name": "Memory", "env_variable": "MEMORY", "default_value": "1024",
                 "rules": "required|integer|min:512|max:65536"},
                {"name": "Max Players", "env_variable": "MAX_PLAYERS", "default_value": "20",
                 "rules": "required|integer|min:1|max:100"},
                {"name": "Difficulty", "env_variable": "DIFFICULTY", "default_value": "normal",
                 "rules": "required|string|in:peaceful,easy,normal,hard"},
            ],
            "volumes": {"server_data": "/data"},
        },
        "nginx": {
            "meta": {"author": "dck", "version": "1.0", "description": "Nginx web server"},
            "startup": "nginx -g 'daemon off;'",
            "stop": "quit",
            "image": "nginx:alpine",
            "environment": {"NGINX_HOST": "localhost"},
            "variables": [
                {"name": "Server Name", "env_variable": "NGINX_HOST", "default_value": "localhost",
                 "rules": "required|string"},
            ],
            "volumes": {"html": "/usr/share/nginx/html"},
        },
        "mariadb": {
            "meta": {"author": "dck", "version": "1.0", "description": "MariaDB database"},
            "startup": "mysqld",
            "stop": "shutdown",
            "image": "mariadb:10",
            "environment": {"MYSQL_ROOT_PASSWORD": "root", "MYSQL_DATABASE": "myapp"},
            "variables": [
                {"name": "Root Password", "env_variable": "MYSQL_ROOT_PASSWORD", "default_value": "root",
                 "rules": "required|string"},
                {"name": "Database", "env_variable": "MYSQL_DATABASE", "default_value": "myapp",
                 "rules": "required|string"},
            ],
            "volumes": {"db_data": "/var/lib/mysql"},
        },
    }


def load_egg(name_or_path):
    p = Path(name_or_path)
    if p.exists():
        return json.loads(p.read_text())
    eggs = builtin_eggs()
    if name_or_path in eggs:
        return eggs[name_or_path]
    # check ~/.dck/eggs/
    for ext in (".json", ".toml"):
        ep = EGGS_DIR / name_or_path / f"egg{ext}"
        if ep.exists():
            return _load_config(ep)
    raise RuntimeError(f"Egg not found: {name_or_path}")


# ── CONFIG LOADER (json/toml/yaml) ────────────────────────────────────

def _load_config(path):
    text = Path(path).read_text()
    ext = Path(path).suffix.lower()
    if ext == ".json":
        return json.loads(text)
    elif ext in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text)
    elif ext == ".toml":
        import tomllib
        return tomllib.loads(text)
    raise RuntimeError(f"Unsupported config format: {ext}")


def _write_config(data, path):
    ext = Path(path).suffix.lower()
    if ext == ".json":
        Path(path).write_text(json.dumps(data, indent=2))
    elif ext in (".yaml", ".yml"):
        import yaml
        Path(path).write_text(yaml.dump(data, default_flow_style=False))
    elif ext == ".toml":
        import tomli_w
        Path(path).write_text(tomli_w.dumps(data))
    else:
        raise RuntimeError(f"Unsupported format: {ext}")


# ── IMAGE PULL (OCI from Docker Hub) ──────────────────────────────────

def pull_image(image, tag="latest", progress=None):
    image = image.replace("docker.io/", "").replace("library/", "")
    if "/" not in image:
        image = f"library/{image}"
    img_dir = IMAGES_DIR / image.replace("/", "_") / tag
    layers_dir = img_dir / "layers"
    rootfs_dir = img_dir / "rootfs"
    _ensure(layers_dir)
    _ensure(rootfs_dir)

    def auth():
        r = requests.get(
            f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{image}:pull",
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["token"]

    def req(method, path, token, **kw):
        url = urljoin("https://registry-1.docker.io/v2/", f"{image}/{path}")
        h = {"Authorization": f"Bearer {token}",
             "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json"}
        h.update(kw.pop("headers", {}))
        r = requests.request(method, url, headers=h, timeout=30, **kw)
        if r.status_code == 401:
            token = auth()
            h["Authorization"] = f"Bearer {token}"
            r = requests.request(method, url, headers=h, timeout=30, **kw)
        r.raise_for_status()
        return r, token

    def stream(digest, token, dest):
        h = {"Authorization": f"Bearer {token}"}
        url = urljoin("https://registry-1.docker.io/v2/", f"{image}/blobs/{digest}")
        r = requests.get(url, headers=h, stream=True, timeout=(10, 120))
        if r.status_code == 401:
            token = auth()
            h["Authorization"] = f"Bearer {token}"
            r = requests.get(url, headers=h, stream=True, timeout=(10, 120))
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        dl, start = 0, time.time()
        short = digest.split(":")[1][:12]
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)
                    dl += len(chunk)
                    now = time.time()
                    if progress and total > 0 and (now - start >= 1 or dl == total):
                        pct = dl * 100 / total
                        speed = dl / (now - start) / 1024 / 1024 if now > start else 0
                        progress(f"[{dl/1024/1024:.1f}/{total/1024/1024:.1f}MB] {short} ({pct:.0f}% @ {speed:.1f}MB/s)")
        return token

    if progress:
        progress("Authenticating...")
    token = auth()
    if progress:
        progress("Fetching manifest...")
    r, token = req("GET", f"manifests/{tag}", token)
    manifest = r.json()
    if manifest.get("mediaType") in (
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.index.v1+json",
    ):
        amd = [m for m in manifest.get("manifests", []) if m.get("platform", {}).get("architecture") == "amd64"]
        if not amd:
            raise RuntimeError("No amd64 image in manifest list")
        r, token = req("GET", f"manifests/{amd[0]['digest']}", token)
        manifest = r.json()
    if progress:
        progress("Downloading config...")
    cd = manifest["config"]["digest"]
    stream(cd, token, layers_dir / cd.replace(":", "_"))
    config = json.loads((layers_dir / cd.replace(":", "_")).read_bytes())
    (img_dir / ".image-name").write_text(image)
    (img_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (img_dir / "config.json").write_text(json.dumps(config, indent=2))
    layers = manifest.get("layers", [])
    for i, layer in enumerate(layers):
        digest = layer["digest"]
        short = digest.split(":")[1][:12]
        lf = layers_dir / digest.replace(":", "_")
        if not lf.exists():
            if progress:
                progress(f"Downloading layer {i+1}/{len(layers)}: {short}...")
            token = stream(digest, token, lf, progress)
        if layer.get("mediaType", "").endswith("tar.gzip") or layer.get("mediaType", "").endswith("gzip"):
            if progress:
                progress(f"Extracting layer {i+1}/{len(layers)}: {short}...")
            with tarfile.open(str(lf), "r:gz") as tar:
                for m in tar.getmembers():
                    p = Path(m.name)
                    if p.is_absolute() or ".." in p.parts:
                        continue
                    tar.extract(m, path=str(rootfs_dir))
    if progress:
        progress("Done")
    return {"name": image, "tag": tag, "rootfs": str(rootfs_dir)}


def list_images():
    imgs = []
    if not IMAGES_DIR.exists():
        return imgs
    for d in sorted(IMAGES_DIR.iterdir()):
        if not d.is_dir():
            continue
        nf = d / ".image-name"
        name = nf.read_text().strip() if nf.exists() else d.name.replace("_", "/")
        for td in sorted(d.iterdir()):
            if not td.is_dir():
                continue
            cf = td / "config.json"
            cmd = ""
            if cf.exists():
                try:
                    cfg = json.loads(cf.read_text())
                    cmd = " ".join(cfg.get("config", {}).get("Cmd", []))
                except Exception:
                    pass
            display = name
            if display.startswith("library/"):
                display = display[len("library/"):]
            imgs.append({"name": display, "tag": td.name, "cmd": cmd, "rootfs": str(td / "rootfs")})
    return imgs


def remove_image(image, tag="latest"):
    if "/" not in image:
        image = f"library/{image}"
    d = IMAGES_DIR / image.replace("/", "_") / tag
    if d.exists():
        shutil.rmtree(str(d))
        return True
    return False


def save_image(image, tag, output_path):
    d = IMAGES_DIR / image.replace("/", "_") / tag
    if not d.exists():
        raise RuntimeError(f"Image {image}:{tag} not found")
    with tarfile.open(str(output_path), "w:gz") as tar:
        tar.add(str(d), arcname=f"{image.replace('/', '_')}_{tag}")
    return True


def load_image(input_path):
    with tarfile.open(str(input_path), "r:gz") as tar:
        tar.extractall(path=str(IMAGES_DIR))
    return True


# ── NETWORKING ────────────────────────────────────────────────────────

def _ip(cmd, check=True, timeout=10):
    r = subprocess.run(["ip"] + cmd, check=False, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"ip {' '.join(cmd)}: {r.stderr.strip()}")
    return r


def _ipt(cmd, check=True):
    r = subprocess.run(["iptables"] + cmd, check=False, capture_output=True, text=True, timeout=10)
    if check and r.returncode != 0:
        raise RuntimeError(f"iptables {' '.join(cmd)}: {r.stderr.strip()}")
    return r


def _rule_exists(cmd):
    return _ipt(cmd + ["-C"], check=False).returncode == 0


def ensure_bridge():
    r = _ip(["link", "show", BRIDGE_NAME], check=False)
    if r.returncode != 0:
        _ip(["link", "add", BRIDGE_NAME, "type", "bridge"])
        _ip(["addr", "add", f"{BRIDGE_GATEWAY}/24", "dev", BRIDGE_NAME])
        _ip(["link", "set", BRIDGE_NAME, "up"])
    for rule in [
        ["-t", "nat", "-A", "POSTROUTING", "-s", BRIDGE_SUBNET, "!", "-o", BRIDGE_NAME, "-j", "MASQUERADE"],
        ["-A", "FORWARD", "-i", BRIDGE_NAME, "-j", "ACCEPT"],
        ["-A", "FORWARD", "-o", BRIDGE_NAME, "-j", "ACCEPT"],
    ]:
        if not _rule_exists(rule):
            _ipt(rule)


def alloc_ip():
    _ensure(NET_IPS_FILE.parent)
    fd = os.open(str(NET_IPS_FILE), os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        data = os.read(fd, 65536) if os.path.getsize(NET_IPS_FILE) > 0 else b"[]"
        used = set(json.loads(data)) if data.strip() else set()
        for i in range(2, 255):
            ip = f"10.0.0.{i}"
            if ip not in used:
                used.add(ip)
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, json.dumps(list(used)).encode())
                return ip
        raise RuntimeError("No free IPs")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def free_ip(ip):
    if not NET_IPS_FILE.exists():
        return
    fd = os.open(str(NET_IPS_FILE), os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        data = os.read(fd, 65536)
        used = set(json.loads(data)) if data.strip() else set()
        used.discard(ip)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(list(used)).encode())
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def setup_veth(pid, ip):
    host = f"v{pid:x}"[:12]
    _ip(["link", "add", host, "type", "veth", "peer", "name", "eth0"])
    _ip(["link", "set", host, "master", BRIDGE_NAME])
    _ip(["link", "set", host, "up"])
    _ip(["link", "set", "eth0", "netns", str(pid)])
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "addr", "add", f"{ip}/24", "dev", "eth0"], timeout=5)
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "link", "set", "eth0", "up"], timeout=5)
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "link", "set", "lo", "up"], timeout=5)
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "route", "add", "default", "via", BRIDGE_GATEWAY], timeout=5)
    return host


def del_veth(name):
    _ip(["link", "delete", name], check=False)


def forward_port(hp, cip, cp, proto="tcp"):
    rule = ["-t", "nat", "-A", "PREROUTING", "-p", proto, "--dport", str(hp),
            "-j", "DNAT", "--to-destination", f"{cip}:{cp}"]
    if not _rule_exists(rule):
        _ipt(rule)
    rule2 = ["-A", "FORWARD", "-p", proto, "--dport", str(cp), "-d", cip, "-j", "ACCEPT"]
    if not _rule_exists(rule2):
        _ipt(rule2)


def unforward_port(hp, cip, cp, proto="tcp"):
    _ipt(["-t", "nat", "-D", "PREROUTING", "-p", proto, "--dport", str(hp),
          "-j", "DNAT", "--to-destination", f"{cip}:{cp}"], check=False)
    _ipt(["-D", "FORWARD", "-p", proto, "--dport", str(cp), "-d", cip, "-j", "ACCEPT"], check=False)


# ── CONTAINER ─────────────────────────────────────────────────────────

class Container:
    def __init__(self, name=None, config=None):
        self.id = uuid.uuid4().hex[:12]
        self.name = name or f"dck-{self.id}"
        self.cfg = config or {}
        self.state_file = CONTAINERS_DIR / f"{self.id}.json"

    def save(self):
        _ensure(CONTAINERS_DIR)
        self.state_file.write_text(json.dumps(self._data(), indent=2))

    def _data(self):
        return {
            "id": self.id, "name": self.name,
            "image": self.cfg.get("image", ""),
            "pid": self.cfg.get("pid"),
            "status": self.cfg.get("status", "created"),
            "created": self.cfg.get("created", time.time()),
            "cmd": self.cfg.get("cmd", []),
            "ports": self.cfg.get("ports", {}),
            "volumes": self.cfg.get("volumes", {}),
            "env": self.cfg.get("env", {}),
            "rootfs": self.cfg.get("rootfs", ""),
            "cgroup": str(self.cfg.get("cgroup", "")),
            "log": self.cfg.get("log", ""),
            "hostname": self.cfg.get("hostname", ""),
            "tty": self.cfg.get("tty", False),
            "interactive": self.cfg.get("interactive", False),
            "detach": self.cfg.get("detach", False),
            "rm": self.cfg.get("rm", False),
            "ram": self.cfg.get("ram"),
            "cpu": self.cfg.get("cpu"),
            "network": self.cfg.get("network", {}),
            "veth": self.cfg.get("veth"),
        }

    def load(self):
        if self.state_file.exists():
            d = json.loads(self.state_file.read_text())
            self.cfg.update(d)
            return d
        return None

    def create(self, image_cfg=None):
        rootfs = self.cfg.get("rootfs", "")
        if not rootfs or not Path(rootfs).exists():
            raise RuntimeError(f"Rootfs not found: {rootfs}")

        # overlay
        d = OVERLAY_DIR / self.id
        _ensure(d / "upper")
        _ensure(d / "work")
        merged = str(d / "merged")
        subprocess.run(["mount", "-t", "overlay", "overlay",
                        "-o", f"lowerdir={rootfs},upperdir={d / 'upper'},workdir={d / 'work'}",
                        merged], check=True, capture_output=True, timeout=10)
        self.cfg["merged"] = merged

        # cgroup
        if CGROUP_ENABLED:
            cg = CGROUP_DIR / self.id
            _ensure(str(cg))
            ram = self.cfg.get("ram")
            if ram:
                self._set_cg(cg / "memory.max", self._parse_mem(ram))
            cpu = self.cfg.get("cpu")
            if cpu:
                self._set_cg(cg / "cpu.max", f"{int(float(cpu) * 100000)} 100000")
            self.cfg["cgroup"] = str(cg)

        # log
        lf = LOGS_DIR / f"{self.id}.log"
        _ensure(LOGS_DIR)
        self.cfg["log"] = str(lf)
        self.cfg["status"] = "created"
        self.cfg["created"] = time.time()
        self.save()
        return self

    def _set_cg(self, p, val):
        try:
            p.write_text(str(val))
        except Exception:
            pass

    def _parse_mem(self, s):
        if not s:
            return None
        s = str(s).strip().lower()
        if s[-1].isdigit():
            s += "m"
        u = s[-1]
        n = s[:-1]
        if not n.isdigit():
            return None
        mul = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
        return int(n) * mul.get(u, 1)

    def start(self):
        mode = "detach" if self.cfg.get("detach") else \
               "tty" if self.cfg.get("tty") else \
               "interactive" if self.cfg.get("interactive") else "normal"

        merged = self.cfg.get("merged", "")
        cmd = self.cfg.get("cmd", ["/bin/sh"])
        env = self.cfg.get("env", {})
        vols = self.cfg.get("volumes", {})
        logf = self.cfg.get("log", "")

        has_ports = bool(self.cfg.get("ports"))
        needs_net = has_ports or self.cfg.get("network", {}).get("mode", "bridge") != "none"

        cip = None
        if needs_net:
            ensure_bridge()
            cip = alloc_ip()
            self.cfg["network"] = {"ip": cip, "mode": "bridge"}
            self.save()

        if mode in ("tty", "interactive"):
            return self._run_pty(merged, cmd, env, vols, logf, needs_net, cip)
        elif mode == "detach":
            return self._run_detach(merged, cmd, env, vols, logf, needs_net, cip)
        else:
            return self._run_normal(merged, cmd, env, vols, logf, needs_net, cip)

    def _child(self, merged, cmd, env, vols, logf, needs_net, cip, ready_fd=None, pty_fd=None):
        libc = ctypes.CDLL("libc.so.6")
        flags = NS["mnt"] | NS["pid"] | NS["net"] | NS["uts"] | NS["ipc"]
        if CGROUP_ENABLED:
            flags |= NS["cgroup"]

        ret = libc.unshare(flags)
        if ret != 0:
            e = ctypes.get_errno()
            msg = f"unshare: {os.strerror(e)}"
            _log(logf, msg)
            os._exit(1)

        hn = (self.cfg.get("hostname") or self.name)[:64]
        libc.sethostname(hn.encode(), len(hn))
        subprocess.run(["ip", "link", "set", "lo", "up"], check=False, capture_output=True, timeout=5)

        try:
            os.chdir(merged)
            subprocess.run(["mount", "--make-rprivate", "/"], check=True, capture_output=True, timeout=5)
            os.chroot(".")
            os.chdir("/")

            subs = [("proc", "/proc", "proc"), ("sysfs", "/sys", "sysfs"),
                    ("tmpfs", "/tmp", "tmpfs"), ("devtmpfs", "/dev", "devtmpfs"),
                    ("devpts", "/dev/pts", "devpts")]
            for fs, target, fstype in subs:
                r = subprocess.run(["mount", "-t", fstype, fs, target], check=False,
                                   capture_output=True, timeout=5)
                if r.returncode != 0:
                    _log(logf, f"mount {target}: {r.stderr.decode().strip()}")
        except Exception as e:
            _log(logf, f"mount: {e}")
            os._exit(1)

        for hp, cp in vols.items():
            Path(cp).mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", "--bind", str(hp), str(cp)], check=False, capture_output=True, timeout=5)

        # environment — clean
        env_list = {}
        for k, v in os.environ.items():
            if any(k.startswith(p) for p in ("XDG_", "DBUS_", "SYSTEMD_", "LC_", "LD_")) or \
               k in ("PATH", "HOME", "LOGNAME", "USER", "SHELL", "LANG", "LANGUAGE"):
                continue
            env_list[k] = v
        env_list.update(env)
        env_list.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        env_list.setdefault("HOME", "/root")
        env_list.setdefault("TERM", "xterm")

        wd = self.cfg.get("workdir", "")
        if wd:
            try:
                os.chdir(wd)
            except Exception:
                pass

        ep = self.cfg.get("entrypoint", "")
        if isinstance(cmd, str):
            cmd = cmd.split()
        if ep:
            cmd = (ep.split() if isinstance(ep, str) else list(ep)) + cmd

        if pty_fd is None and logf:
            fd = os.open(logf, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.dup2(fd, 1)
            os.dup2(fd, 2)
            if fd > 2:
                os.close(fd)

        if ready_fd is not None:
            try:
                os.write(ready_fd, b"1")
                os.close(ready_fd)
            except OSError:
                pass

        try:
            os.execvpe(cmd[0], cmd, env_list)
        except Exception as e:
            _log(logf, f"exec: {e}")
            os._exit(1)

    def _run_normal(self, merged, cmd, env, vols, logf, needs_net, cip):
        return self._run_detach(merged, cmd, env, vols, logf, needs_net, cip)

    def _run_detach(self, merged, cmd, env, vols, logf, needs_net, cip):
        sr, sw = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(sr)
            self._child(merged, cmd, env, vols, logf, needs_net, cip, ready_fd=sw)
            os._exit(1)
        else:
            os.close(sw)
            r, _, _ = select.select([sr], [], [], 5)
            data = None
            if r:
                try:
                    data = os.read(sr, 1)
                except OSError:
                    pass
            os.close(sr)
            if not r or not data:
                os.waitpid(pid, 0)
                raise RuntimeError("Container failed (check logs)")

            self.cfg["pid"] = pid
            self.cfg["status"] = "running"
            self.save()
            self._add_cg(pid)
            if needs_net and cip:
                self._setup_net(pid, cip)
            return pid

    def _run_pty(self, merged, cmd, env, vols, logf, needs_net, cip):
        mfd, sfd = os.openpty()
        sr, sw = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(mfd)
            os.close(sr)
            os.setsid()
            os.dup2(sfd, 0)
            os.dup2(sfd, 1)
            os.dup2(sfd, 2)
            if sfd > 2:
                os.close(sfd)
            self._child(merged, cmd, env, vols, logf, needs_net, cip, ready_fd=sw, pty_fd=sfd)
            os._exit(1)
        else:
            os.close(sfd)
            os.close(sw)
            r, _, _ = select.select([sr], [], [], 5)
            data = None
            if r:
                try:
                    data = os.read(sr, 1)
                except OSError:
                    pass
            os.close(sr)
            if not r or not data:
                os.waitpid(pid, 0)
                raise RuntimeError("Container failed (check logs)")

            self.cfg["pid"] = pid
            self.cfg["status"] = "running"
            self.save()
            self._add_cg(pid)
            if needs_net and cip:
                self._setup_net(pid, cip)

            import termios, tty as tty_mod
            old = None
            try:
                old = termios.tcgetattr(0)
                tty_mod.setraw(0)
            except Exception:
                pass
            sig_old = signal.signal(signal.SIGWINCH, signal.SIG_DFL)
            try:
                while True:
                    rr, _, _ = select.select([0, mfd], [], [])
                    if 0 in rr:
                        d = os.read(0, 1024)
                        if not d:
                            break
                        os.write(mfd, d)
                    if mfd in rr:
                        d = os.read(mfd, 1024)
                        if not d:
                            break
                        os.write(1, d)
            except (KeyboardInterrupt, OSError):
                pass
            finally:
                if old:
                    try:
                        termios.tcsetattr(0, termios.TCSAFLUSH, old)
                    except Exception:
                        pass
                signal.signal(signal.SIGWINCH, sig_old)
                os.close(mfd)
                os.waitpid(pid, 0)
                self._cleanup()
            return pid

    def _setup_net(self, pid, cip):
        for _ in range(50):
            try:
                ino = os.stat(f"/proc/{pid}/ns/net").st_ino
                if ino != os.stat("/proc/self/ns/net").st_ino:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        else:
            _log(self.cfg.get("log", ""), "netns timeout")
            return
        try:
            veth = setup_veth(pid, cip)
            self.cfg["veth"] = veth
            self.save()
        except Exception as e:
            _log(self.cfg.get("log", ""), f"veth: {e}")
        for cp, hp in self.cfg.get("ports", {}).items():
            cn = cp.split("/")[0]
            proto = cp.split("/")[1] if "/" in cp else "tcp"
            try:
                forward_port(hp, cip, cn, proto)
            except Exception as e:
                _log(self.cfg.get("log", ""), f"port {hp}:{cn}: {e}")

    def _add_cg(self, pid):
        cg = self.cfg.get("cgroup", "")
        if cg:
            try:
                (Path(cg) / "cgroup.procs").write_text(str(pid))
            except Exception:
                pass

    def _cleanup(self):
        self.cfg["status"] = "stopped"
        self.cfg["pid"] = None
        self.save()
        net = self.cfg.get("network", {})
        cip = net.get("ip")
        if cip:
            free_ip(cip)
        veth = self.cfg.get("veth")
        if veth:
            del_veth(veth)
        for cp, hp in self.cfg.get("ports", {}).items():
            cn = cp.split("/")[0]
            proto = cp.split("/")[1] if "/" in cp else "tcp"
            unforward_port(hp, cip or "", cn, proto)
        if self.cfg.get("rm"):
            try:
                self.remove()
            except Exception:
                pass

    def stop(self, timeout=10):
        pid = self.cfg.get("pid")
        if not pid:
            self.cfg["status"] = "stopped"
            self.save()
            return
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(timeout):
                try:
                    os.kill(pid, 0)
                    time.sleep(1)
                except OSError:
                    break
            else:
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
        except OSError:
            pass
        self._cleanup()

    def remove(self):
        if self.cfg.get("status") == "running":
            self.stop()
        merged = self.cfg.get("merged", "")
        if merged:
            subprocess.run(["umount", merged], check=False, capture_output=True, timeout=5)
            shutil.rmtree(str(OVERLAY_DIR / self.id), ignore_errors=True)
        cg = self.cfg.get("cgroup", "")
        if cg:
            shutil.rmtree(cg, ignore_errors=True)
        veth = self.cfg.get("veth")
        if veth:
            del_veth(veth)
        if self.state_file.exists():
            self.state_file.unlink()

    def commit(self, new_image, tag="latest"):
        merged = self.cfg.get("merged", "")
        if not merged:
            raise RuntimeError("Container has no merged rootfs")
        img_dir = IMAGES_DIR / new_image.replace("/", "_") / tag
        rootfs_dir = img_dir / "rootfs"
        _ensure(rootfs_dir)
        for item in Path(merged).iterdir():
            if item.name != ".old_root":
                dst = rootfs_dir / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dst), symlinks=True, ignore_dangling_symlinks=True)
                else:
                    shutil.copy2(str(item), str(dst))
        cfg = {"config": {"Cmd": self.cfg.get("cmd", []), "Env": []}}
        (img_dir / "config.json").write_text(json.dumps(cfg, indent=2))
        (img_dir / ".image-name").write_text(new_image)
        return new_image

    def status(self):
        pid = self.cfg.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                return "running"
            except OSError:
                pass
        return self.cfg.get("status", "stopped")

    def logs(self, tail=50, follow=False):
        lf = self.cfg.get("log", "")
        if not lf or not Path(lf).exists():
            return ""
        if follow:
            try:
                subprocess.run(["tail", "-n", str(tail), "-f", lf])
            except KeyboardInterrupt:
                pass
            return ""
        try:
            lines = Path(lf).read_text().splitlines()
            return "\n".join(lines[-tail:])
        except Exception:
            return ""

    def exec_run(self, cmd, interactive=False, tty=False):
        pid = self.cfg.get("pid")
        if not pid:
            raise RuntimeError("Container not running")
        ns = []
        for ns_type in ("mnt", "pid", "net", "uts", "ipc"):
            p = f"/proc/{pid}/ns/{ns_type}"
            if Path(p).exists():
                ns += ["--target", str(pid), f"--{ns_type}"]
        full = ["nsenter"] + ns + list(cmd)
        if interactive or tty:
            subprocess.run(full)
        else:
            r = subprocess.run(full, capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout, r.stderr


# ── HELPERS ───────────────────────────────────────────────────────────

def list_containers(all_=False):
    result = []
    if not CONTAINERS_DIR.exists():
        return result
    for f in sorted(CONTAINERS_DIR.iterdir(), reverse=True):
        if not f.name.endswith(".json"):
            continue
        try:
            d = json.loads(f.read_text())
            c = Container(config=d)
            st = c.status()
            if all_ or st == "running":
                d["live_status"] = st
                result.append(d)
        except Exception:
            pass
    return result


def get_container(name_or_id):
    if not CONTAINERS_DIR.exists():
        return None
    for f in CONTAINERS_DIR.iterdir():
        if not f.name.endswith(".json"):
            continue
        try:
            d = json.loads(f.read_text())
            if d.get("id") == name_or_id or d.get("name") == name_or_id:
                c = Container(config=d)
                c.state_file = f
                c.name = d.get("name", c.name)
                return c
        except Exception:
            pass
    return None


def system_prune(all_=False):
    removed = {"containers": 0, "images": 0, "overlay": 0}
    for f in list(CONTAINERS_DIR.iterdir()) if CONTAINERS_DIR.exists() else []:
        if f.name.endswith(".json"):
            try:
                d = json.loads(f.read_text())
                c = Container(config=d)
                c.remove()
                removed["containers"] += 1
            except Exception:
                pass
    if all_:
        for d in list(IMAGES_DIR.iterdir()) if IMAGES_DIR.exists() else []:
            if d.is_dir():
                shutil.rmtree(str(d), ignore_errors=True)
                removed["images"] += 1
    for d in list(OVERLAY_DIR.iterdir()) if OVERLAY_DIR.exists() else []:
        if d.is_dir() and d.name != ".gitkeep":
            shutil.rmtree(str(d), ignore_errors=True)
            removed["overlay"] += 1
    for f in [LOGS_DIR, OVERLAY_DIR, NET_IPS_FILE]:
        p = Path(f)
        if p.is_dir():
            shutil.rmtree(str(p), ignore_errors=True)
        elif p.exists():
            p.unlink()
    return removed


# ── DOCTOR ────────────────────────────────────────────────────────────

def doctor():
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {msg}")
        if not cond:
            ok = False
    def warn(cond, msg):
        if not cond:
            print(f"  ⚠ {msg}")
    print("dck doctor — system check\n")
    check(os.geteuid() == 0, "root")
    check(os.path.exists("/proc/self/ns"), "namespaces")
    check(CGROUP_ENABLED, "cgroups v2")
    check(Path("/proc/filesystems").read_text().find("overlay") >= 0, "overlayfs")
    r = subprocess.run(["which", "ip", "iptables", "nsenter"], capture_output=True)
    check(r.returncode == 0, "ip + iptables + nsenter")
    print()
    print("System ready" if ok else "Some checks failed")
    return ok
