"""Container runtime: Linux namespaces, cgroups v2, overlayfs."""

import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

from dck.i18n import t

DCK_DIR = Path.home() / ".dck"
CONTAINERS_DIR = DCK_DIR / "containers"
CGROUP_ROOT = Path("/sys/fs/cgroup")
DCK_CGROUP = CGROUP_ROOT / "dck"


def _ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def _cgroup_path(name):
    return DCK_CGROUP / name


def _setup_overlayfs(container_id, rootfs_path):
    """Create overlayfs mount for container root."""
    overlay_dir = DCK_DIR / "overlay" / container_id
    upper_dir = overlay_dir / "upper"
    work_dir = overlay_dir / "work"
    merged_dir = overlay_dir / "merged"
    _ensure_dir(upper_dir)
    _ensure_dir(work_dir)
    _ensure_dir(merged_dir)

    lower = rootfs_path
    upper = str(upper_dir)
    work = str(work_dir)
    merged = str(merged_dir)

    try:
        subprocess.run(
            ["mount", "-t", "overlay", "overlay",
             "-o", f"lowerdir={lower},upperdir={upper},workdir={work}",
             merged],
            check=True, capture_output=True, timeout=10,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Overlay mount failed: {e.stderr.decode()}")

    return merged_dir


def _teardown_overlayfs(container_id):
    """Unmount and remove overlayfs."""
    overlay_dir = DCK_DIR / "overlay" / container_id
    merged_dir = overlay_dir / "merged"

    if merged_dir.exists():
        try:
            subprocess.run(["umount", str(merged_dir)], check=False, capture_output=True, timeout=5)
        except Exception:
            pass

        try:
            shutil.rmtree(str(overlay_dir))
        except Exception:
            pass


def _setup_cgroup(container_id, ram=None, cpu=None, pids=1000):
    """Create cgroup for container."""
    cg_path = _cgroup_path(container_id)
    _ensure_dir(str(cg_path))

    if ram:
        ram_bytes = _parse_memory(ram)
        if ram_bytes:
            try:
                (cg_path / "memory.max").write_text(str(ram_bytes))
                (cg_path / "memory.high").write_text(str(int(ram_bytes * 0.9)))
            except Exception:
                pass

    if cpu:
        try:
            cpu_val = int(float(cpu) * 100000)
            (cg_path / "cpu.max").write_text(f"{cpu_val} 100000")
        except Exception:
            pass

    if pids:
        try:
            (cg_path / "pids.max").write_text(str(pids))
        except Exception:
            pass

    return cg_path


def _teardown_cgroup(container_id):
    """Remove cgroup for container."""
    cg_path = _cgroup_path(container_id)
    if cg_path.exists():
        try:
            for proc_file in cg_path.glob("cgroup.procs"):
                pass
            shutil.rmtree(str(cg_path))
        except Exception:
            pass


def _parse_memory(mem_str):
    """Parse memory string like 512m, 2g to bytes."""
    if not mem_str:
        return None
    mem_str = str(mem_str).strip().lower()
    if mem_str[-1].isdigit():
        mem_str += "m"
    unit = mem_str[-1]
    num = mem_str[:-1]
    if not num.isdigit():
        return None
    multipliers = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    return int(num) * multipliers.get(unit, 1)


class Container:
    def __init__(self, name=None, config=None):
        self.id = uuid.uuid4().hex[:12]
        self.name = name or f"dck-{self.id}"
        self.config = config or {}
        self.state_file = CONTAINERS_DIR / f"{self.id}.json"
        self.mounts = []

    def save_state(self):
        _ensure_dir(str(CONTAINERS_DIR))
        self.state_file.write_text(json.dumps(self._get_state(), indent=2))

    def load_state(self):
        if self.state_file.exists():
            data = json.loads(self.state_file.read_text())
            self.id = data.get("id", self.id)
            self.name = data.get("name", self.name)
            self.config = data.get("config", self.config)
            return data
        return None

    def _get_state(self):
        return {
            "id": self.id,
            "name": self.name,
            "image": self.config.get("image", ""),
            "pid": self.config.get("pid"),
            "status": self.config.get("status", "created"),
            "created": self.config.get("created", time.time()),
            "command": self.config.get("command", []),
            "ports": self.config.get("ports", {}),
            "volumes": self.config.get("volumes", {}),
            "env": self.config.get("env", {}),
            "ram": self.config.get("ram"),
            "cpu": self.config.get("cpu"),
            "rootfs": self.config.get("rootfs", ""),
            "cgroup": str(self.config.get("cgroup", "")),
            "log_file": self.config.get("log_file", ""),
            "network": self.config.get("network", {}),
        }

    def create(self):
        """Prepare container: overlayfs, cgroup, save state."""
        rootfs = self.config.get("rootfs", "")

        if not rootfs or not Path(rootfs).exists():
            raise RuntimeError(f"Rootfs not found: {rootfs}")

        merged = _setup_overlayfs(self.id, rootfs)
        self.config["merged_rootfs"] = str(merged)

        cg_path = _setup_cgroup(self.id, self.config.get("ram"), self.config.get("cpu"))
        self.config["cgroup"] = cg_path

        log_file = DCK_DIR / "logs" / f"{self.id}.log"
        _ensure_dir(str(log_file.parent))
        self.config["log_file"] = str(log_file)
        self.config["status"] = "created"
        self.config["created"] = time.time()
        self.save_state()

        return self

    def start(self):
        """Start the container process with namespaces."""
        rootfs = self.config.get("merged_rootfs", "")
        command = self.config.get("command", ["/bin/sh"])
        env = self.config.get("env", {})
        volumes = self.config.get("volumes", {})
        cg_path = self.config.get("cgroup", "")
        log_file = self.config.get("log_file", "")

        pid = os.fork()
        if pid == 0:
            try:
                self._run_child(rootfs, command, env, volumes, log_file)
            except Exception as e:
                with open(log_file, "a") as f:
                    f.write(f"Container init failed: {e}\n")
                os._exit(1)
        else:
            self.config["pid"] = pid
            self.config["status"] = "running"
            self.save_state()

            if cg_path:
                cg_procs = Path(str(cg_path)) / "cgroup.procs"
                try:
                    cg_procs.write_text(str(pid))
                except Exception:
                    pass

        return pid

    def _run_child(self, rootfs, command, env, volumes, log_file):
        """Child process: set up namespaces, mounts, exec."""
        import ctypes

        libc = ctypes.CDLL("libc.so.6")

        CLONE_NEWNS = 0x00020000
        CLONE_NEWPID = 0x20000000
        CLONE_NEWNET = 0x40000000
        CLONE_NEWUTS = 0x04000000
        CLONE_NEWIPC = 0x08000000

        flags = CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWUTS | CLONE_NEWIPC

        try:
            ret = libc.unshare(flags)
            if ret != 0:
                raise RuntimeError(f"unshare failed: {os.strerror(ctypes.get_errno())}")
        except Exception as e:
            raise RuntimeError(f"Namespace setup failed: {e}")

        hostname = self.name[:64]
        try:
            libc.sethostname(hostname.encode(), len(hostname))
        except Exception:
            pass

        for h_path, c_path in volumes.items():
            Path(c_path).mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["mount", "--bind", str(h_path), str(c_path)],
                    check=True, capture_output=True, timeout=5,
                )
            except subprocess.CalledProcessError:
                pass

        try:
            os.chdir(rootfs)

            subprocess.run(
                ["mount", "--make-rprivate", "/"],
                check=True, capture_output=True, timeout=5,
            )

            old_root = Path(rootfs) / ".old_root"
            old_root.mkdir(exist_ok=True)

            libc.pivot_root(rootfs.encode(), str(old_root).encode())

            os.chdir("/")

            os.chroot(".")

            subprocess.run(
                ["mount", "-t", "proc", "proc", "/proc"],
                check=False, capture_output=True, timeout=5,
            )

            subprocess.run(
                ["mount", "-t", "sysfs", "sys", "/sys"],
                check=False, capture_output=True, timeout=5,
            )

            subprocess.run(
                ["mount", "-t", "tmpfs", "tmpfs", "/tmp"],
                check=False, capture_output=True, timeout=5,
            )

            subprocess.run(
                ["mount", "-t", "devtmpfs", "dev", "/dev"],
                check=False, capture_output=True, timeout=5,
            )

            try:
                shutil.rmtree("/.old_root")
            except Exception:
                pass

        except Exception as e:
            with open(log_file, "a") as f:
                f.write(f"Mount setup error: {e}\n")

        cmd = command if isinstance(command, list) else command.split()

        if log_file:
            log_fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.dup2(log_fd, 1)
            os.dup2(log_fd, 2)
            if log_fd > 2:
                os.close(log_fd)

        env_list = os.environ.copy()
        for k, v in env.items():
            if v is not None:
                env_list[k] = str(v)

        try:
            os.execvpe(cmd[0], cmd, env_list)
        except Exception as e:
            with open("/dev/console", "w") if os.path.exists("/dev/console") else open("/dev/null", "w") as f:
                f.write(f"exec failed: {e}\n")
            os._exit(1)

    def stop(self, timeout=10):
        """Stop the container."""
        pid = self.config.get("pid")
        if not pid:
            self.config["status"] = "stopped"
            self.save_state()
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

        self.config["status"] = "stopped"
        self.config["pid"] = None
        self.save_state()

    def remove(self):
        """Remove container state and cleanup."""
        try:
            if self.config.get("status") == "running":
                self.stop()
        except Exception:
            pass

        _teardown_overlayfs(self.id)
        _teardown_cgroup(self.id)

        if self.state_file.exists():
            self.state_file.unlink()

    def logs(self, tail=50, follow=False):
        """Read container logs."""
        log_file = self.config.get("log_file", "")
        if not log_file or not Path(log_file).exists():
            return ""

        if follow:
            try:
                subprocess.run(["tail", "-n", str(tail), "-f", log_file])
            except KeyboardInterrupt:
                pass
            return ""

        try:
            with open(log_file) as f:
                lines = f.readlines()
            return "".join(lines[-tail:])
        except Exception:
            return ""

    def exec_run(self, cmd):
        """Execute a command in the container's namespaces."""
        pid = self.config.get("pid")
        if not pid:
            raise RuntimeError("Container not running")

        ns_types = ["mnt", "pid", "net", "uts", "ipc"]
        ns_args = []
        for ns in ns_types:
            ns_path = f"/proc/{pid}/ns/{ns}"
            if Path(ns_path).exists():
                ns_args += ["--target", str(pid), f"--{ns}"]

        full_cmd = ["nsenter"] + ns_args + list(cmd) if isinstance(cmd, list) else cmd
        subprocess.run(full_cmd)

    def get_status(self):
        """Get current container status."""
        pid = self.config.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                return "running"
            except OSError:
                pass
        return self.config.get("status", "stopped")


def list_containers(all_containers=False):
    """List all containers from state."""
    containers = []
    if not CONTAINERS_DIR.exists():
        return containers

    for state_file in sorted(CONTAINERS_DIR.iterdir(), reverse=True):
        if not state_file.name.endswith(".json"):
            continue
        try:
            data = json.loads(state_file.read_text())
            c = Container(name=data.get("name"), config=data)
            status = c.get_status()
            if all_containers or status == "running":
                data["live_status"] = status
                containers.append(data)
        except Exception:
            pass

    return containers


def get_container(container_id_or_name):
    """Get container by ID or name."""
    if not CONTAINERS_DIR.exists():
        return None

    for state_file in CONTAINERS_DIR.iterdir():
        if not state_file.name.endswith(".json"):
            continue
        try:
            data = json.loads(state_file.read_text())
            if data.get("id") == container_id_or_name or data.get("name") == container_id_or_name:
                c = Container(name=data.get("name"), config=data)
                c.state_file = state_file
                data["live_status"] = c.get_status()
                return c, data
        except Exception:
            pass

    return None
