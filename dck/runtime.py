"""Container runtime: Linux namespaces, cgroups v2, overlayfs."""

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

DCK_DIR = Path.home() / ".dck"
CONTAINERS_DIR = DCK_DIR / "containers"
CGROUP_ROOT = Path("/sys/fs/cgroup")
DCK_CGROUP = CGROUP_ROOT / "dck"


def _ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def _cgroup_path(name):
    return DCK_CGROUP / name


def _setup_overlayfs(container_id, rootfs_path):
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
    cg_path = _cgroup_path(container_id)
    if cg_path.exists():
        try:
            shutil.rmtree(str(cg_path))
        except Exception:
            pass


def _parse_memory(mem_str):
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


def _netns_inode(pid):
    try:
        return os.stat(f"/proc/{pid}/ns/net").st_ino
    except OSError:
        return None


def _wait_for_netns(pid, parent_inode, timeout=5):
    for _ in range(timeout * 10):
        inode = _netns_inode(pid)
        if inode is not None and inode != parent_inode:
            return True
        time.sleep(0.1)
    return False


def _parse_user_group(user_str):
    import pwd
    uid = None
    gid = None
    if user_str is None:
        return uid, gid
    if user_str.isdigit():
        uid = int(user_str)
    else:
        try:
            pw = pwd.getpwnam(user_str)
            uid = pw.pw_uid
            gid = pw.pw_gid
        except KeyError:
            uid = 0
    return uid, gid


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
            "hostname": self.config.get("hostname", ""),
            "user": self.config.get("user", ""),
            "workdir": self.config.get("workdir", ""),
            "entrypoint": self.config.get("entrypoint", ""),
            "tty": self.config.get("tty", False),
            "interactive": self.config.get("interactive", False),
            "detach": self.config.get("detach", False),
            "rm": self.config.get("rm", False),
            "read_only": self.config.get("read_only", False),
            "restart": self.config.get("restart", "no"),
            "labels": self.config.get("labels", {}),
            "cap_add": self.config.get("cap_add", []),
            "cap_drop": self.config.get("cap_drop", []),
            "privileged": self.config.get("privileged", False),
        }

    def create(self):
        rootfs = self.config.get("rootfs", "")
        if not rootfs or not Path(rootfs).exists():
            raise RuntimeError(f"Rootfs not found: {rootfs}")

        merged = _setup_overlayfs(self.id, rootfs)
        self.config["merged_rootfs"] = str(merged)

        cg_path = _setup_cgroup(self.id, self.config.get("ram"), self.config.get("cpu"))
        self.config["cgroup"] = str(cg_path)

        log_file = DCK_DIR / "logs" / f"{self.id}.log"
        _ensure_dir(str(log_file.parent))
        self.config["log_file"] = str(log_file)
        self.config["status"] = "created"
        self.config["created"] = time.time()
        self.save_state()
        return self

    def start(self):
        mode = "detach" if self.config.get("detach") else \
               "tty" if self.config.get("tty") else \
               "interactive" if self.config.get("interactive") else \
               "normal"

        rootfs = self.config.get("merged_rootfs", "")
        command = self.config.get("command", ["/bin/sh"])
        env = self.config.get("env", {})
        volumes = self.config.get("volumes", {})
        log_file = self.config.get("log_file", "")

        # Determine if we need networking
        needs_net = bool(self.config.get("ports")) or \
                    self.config.get("network", {}).get("mode", "bridge") != "none"

        container_ip = None
        if needs_net:
            from dck.network import ensure_bridge, allocate_ip
            ensure_bridge()
            container_ip = allocate_ip()
            self.config["network"] = {"ip": container_ip, "mode": "bridge"}
            self.save_state()

        if mode == "tty" or mode == "interactive":
            return self._start_pty(rootfs, command, env, volumes, log_file, needs_net, container_ip)
        elif mode == "detach":
            return self._start_detach(rootfs, command, env, volumes, log_file, needs_net, container_ip)
        else:
            return self._start_normal(rootfs, command, env, volumes, log_file, needs_net, container_ip)

    def _run_child(self, rootfs, command, env, volumes, log_file, needs_net, container_ip, master_fd=None, ready_fd=None):
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

        # Set hostname
        hostname = self.config.get("hostname") or self.name[:64]
        try:
            libc.sethostname(hostname.encode(), len(hostname))
        except Exception:
            pass

        # Mount loopback
        try:
            subprocess.run(["ip", "link", "set", "lo", "up"],
                           check=False, capture_output=True, timeout=5)
        except Exception:
            pass

        # Mount proc, sys, dev, tmp
        try:
            os.chdir(rootfs)
            subprocess.run(["mount", "--make-rprivate", "/"],
                           check=True, capture_output=True, timeout=5)

            old_root = Path(rootfs) / ".old_root"
            old_root.mkdir(exist_ok=True)

            libc.pivot_root(rootfs.encode(), str(old_root).encode())
            os.chdir("/")
            os.chroot(".")

            subprocess.run(["mount", "-t", "proc", "proc", "/proc"],
                           check=False, capture_output=True, timeout=5)
            subprocess.run(["mount", "-t", "sysfs", "sys", "/sys"],
                           check=False, capture_output=True, timeout=5)
            subprocess.run(["mount", "-t", "tmpfs", "tmpfs", "/tmp"],
                           check=False, capture_output=True, timeout=5)
            subprocess.run(["mount", "-t", "devtmpfs", "dev", "/dev"],
                           check=False, capture_output=True, timeout=5)
            subprocess.run(["mount", "-t", "devpts", "devpts", "/dev/pts"],
                           check=False, capture_output=True, timeout=5)

            try:
                shutil.rmtree("/.old_root")
            except Exception:
                pass
        except Exception as e:
            msg = f"Mount setup error: {e}\n"
            if isinstance(e, OSError) and e.errno == 12:
                msg += "  ENOMEM — try: sysctl -w kernel.keys.root_maxkeys=1000000; sysctl -w kernel.keys.root_maxbytes=25000000\n"
            self._write_log(log_file, msg)
            raise

        # Bind mount volumes
        for h_path, c_path in volumes.items():
            Path(c_path).mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(["mount", "--bind", str(h_path), str(c_path)],
                               check=True, capture_output=True, timeout=5)
            except subprocess.CalledProcessError:
                pass

        # Read-only rootfs
        if self.config.get("read_only"):
            try:
                subprocess.run(["mount", "-o", "remount,ro", "/"],
                               check=False, capture_output=True, timeout=5)
                _ensure_dir("/tmp")
                _ensure_dir("/run")
                subprocess.run(["mount", "-t", "tmpfs", "tmpfs", "/run"],
                               check=False, capture_output=True, timeout=5)
            except Exception:
                pass

        # Change to workdir
        workdir = self.config.get("workdir", "")
        if workdir:
            try:
                os.chdir(workdir)
            except Exception:
                pass

        # Build final command
        entrypoint = self.config.get("entrypoint", "")
        cmd = command if isinstance(command, list) else command.split()
        if entrypoint:
            if isinstance(entrypoint, str):
                entry_cmd = entrypoint.split()
            else:
                entry_cmd = list(entrypoint)
            cmd = entry_cmd + cmd

        # Set up environment
        env_list = os.environ.copy()
        for k, v in env.items():
            if v is not None:
                env_list[k] = str(v)

        # Redirect stdout/stderr to log file (only if not TTY/interactive)
        if master_fd is None:
            if log_file:
                log_fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                os.dup2(log_fd, 1)
                os.dup2(log_fd, 2)
                if log_fd > 2:
                    os.close(log_fd)

        # Drop privileges
        user = self.config.get("user", "")
        if user:
            uid, gid = _parse_user_group(user)
            if gid is not None:
                try:
                    os.setgid(gid)
                except Exception:
                    pass
            if uid is not None:
                try:
                    os.setuid(uid)
                except Exception:
                    pass

        # Signal readiness before exec (for detach mode)
        if ready_fd is not None:
            try:
                os.write(ready_fd, b"1")
                os.close(ready_fd)
            except OSError:
                pass

        try:
            os.execvpe(cmd[0], cmd, env_list)
        except Exception as e:
            err_msg = f"exec failed: {e}\n"
            if master_fd is not None:
                os.write(master_fd, err_msg.encode())
            else:
                with open(log_file or "/dev/null", "a") as f:
                    f.write(err_msg)
            os._exit(1)

    def _write_log(self, log_file, msg):
        if log_file:
            try:
                with open(log_file, "a") as f:
                    f.write(msg)
            except Exception:
                pass

    def _start_pty(self, rootfs, command, env, volumes, log_file, needs_net, container_ip):
        master_fd, slave_fd = os.openpty()

        pid = os.fork()
        if pid == 0:
            os.close(master_fd)
            try:
                os.setsid()
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)
                self._run_child(rootfs, command, env, volumes, log_file,
                               needs_net, container_ip, master_fd=slave_fd)
            except Exception as e:
                self._write_log(log_file, f"PTY child init failed: {e}\n")
                os._exit(1)
        else:
            os.close(slave_fd)
            self.config["pid"] = pid
            self.config["status"] = "running"
            self.save_state()
            self._add_to_cgroup(pid)

            # Set up networking
            if needs_net and container_ip:
                self._setup_container_net(pid, container_ip)

            original_handler = signal.signal(signal.SIGWINCH, signal.SIG_DFL)
            try:
                import select
                stdin_fd = sys.stdin.fileno()
                stdout_fd = sys.stdout.fileno()

                # Set stdin to raw mode
                import tty
                import termios
                old_tc = None
                try:
                    old_tc = termios.tcgetattr(stdin_fd)
                    tty.setraw(stdin_fd)
                except Exception:
                    pass

                try:
                    while True:
                        r, _, _ = select.select([stdin_fd, master_fd], [], [])
                        if stdin_fd in r:
                            try:
                                data = os.read(stdin_fd, 1024)
                                if not data:
                                    break
                                os.write(master_fd, data)
                            except OSError:
                                break
                        if master_fd in r:
                            try:
                                data = os.read(master_fd, 1024)
                                if not data:
                                    break
                                os.write(stdout_fd, data)
                            except OSError:
                                break
                finally:
                    if old_tc:
                        try:
                            termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, old_tc)
                        except Exception:
                            pass
            except (ImportError, KeyboardInterrupt, OSError):
                pass
            finally:
                signal.signal(signal.SIGWINCH, original_handler)
                try:
                    os.close(master_fd)
                except Exception:
                    pass

            # Wait for child
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass

            self._cleanup_after_exit()

        return pid

    def _start_detach(self, rootfs, command, env, volumes, log_file, needs_net, container_ip):
        sync_r, sync_w = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(sync_r)
            try:
                self._run_child(rootfs, command, env, volumes, log_file,
                               needs_net, container_ip, ready_fd=sync_w)
            except Exception as e:
                self._write_log(log_file, f"Detached start failed: {e}\n")
                os._exit(1)
        else:
            os.close(sync_w)
            import select
            ready, _, _ = select.select([sync_r], [], [], 5)
            data = None
            if ready:
                try:
                    data = os.read(sync_r, 1)
                except OSError:
                    pass
            os.close(sync_r)

            if not ready or not data:
                try:
                    os.waitpid(pid, 0)
                except OSError:
                    pass
                raise RuntimeError("Container failed during startup (check logs with: dck logs)")

            self.config["pid"] = pid
            self.config["status"] = "running"
            self.save_state()
            self._add_to_cgroup(pid)

            if needs_net and container_ip:
                self._setup_container_net(pid, container_ip)

        return pid

    def _start_normal(self, rootfs, command, env, volumes, log_file, needs_net, container_ip):
        pid = os.fork()
        if pid == 0:
            try:
                self._run_child(rootfs, command, env, volumes, log_file,
                               needs_net, container_ip)
            except Exception as e:
                self._write_log(log_file, f"Start failed: {e}\n")
                os._exit(1)
        else:
            self.config["pid"] = pid
            self.config["status"] = "running"
            self.save_state()
            self._add_to_cgroup(pid)

            if needs_net and container_ip:
                self._setup_container_net(pid, container_ip)

            try:
                os.waitpid(pid, 0)
            except OSError:
                pass

            self._cleanup_after_exit()

        return pid

    def _setup_container_net(self, pid, container_ip):
        parent_inode = _netns_inode(os.getpid())
        if not _wait_for_netns(pid, parent_inode, timeout=5):
            return

        from dck.network import setup_veth
        try:
            setup_veth(pid, container_ip)
        except Exception:
            pass

        # Port forwarding
        ports = self.config.get("ports", {})
        for c_port, h_port in ports.items():
            c_num = c_port.split("/")[0]
            proto = c_port.split("/")[1] if "/" in c_port else "tcp"
            from dck.network import forward_port
            try:
                forward_port(h_port, container_ip, c_num, proto)
            except Exception:
                pass

    def _add_to_cgroup(self, pid):
        cg_path = self.config.get("cgroup", "")
        if cg_path:
            try:
                cg_procs = Path(str(cg_path)) / "cgroup.procs"
                cg_procs.write_text(str(pid))
            except Exception:
                pass

    def _cleanup_after_exit(self):
        self.config["status"] = "stopped"
        self.config["pid"] = None
        self.save_state()

        # Cleanup networking
        network = self.config.get("network", {})
        container_ip = network.get("ip")
        if container_ip:
            from dck.network import release_ip
            try:
                release_ip(container_ip)
            except Exception:
                pass

        # Remove port forwarding rules
        ports = self.config.get("ports", {})
        for c_port, h_port in ports.items():
            c_num = c_port.split("/")[0]
            proto = c_port.split("/")[1] if "/" in c_port else "tcp"
            from dck.network import remove_port_forward
            try:
                remove_port_forward(h_port, container_ip or "", c_num, proto)
            except Exception:
                pass

        if self.config.get("rm"):
            try:
                self.remove()
            except Exception:
                pass

    def stop(self, timeout=10):
        pid = self.config.get("pid")
        if not pid:
            if self.config.get("status") != "stopped":
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

        network = self.config.get("network", {})
        container_ip = network.get("ip")
        if container_ip:
            from dck.network import release_ip
            try:
                release_ip(container_ip)
            except Exception:
                pass

        ports = self.config.get("ports", {})
        for c_port, h_port in ports.items():
            c_num = c_port.split("/")[0]
            proto = c_port.split("/")[1] if "/" in c_port else "tcp"
            from dck.network import remove_port_forward
            try:
                remove_port_forward(h_port, container_ip or "", c_num, proto)
            except Exception:
                pass

    def start_existing(self):
        """Restart a previously stopped container."""
        status = self.get_status()
        if status == "running":
            return

        rootfs = self.config.get("rootfs", "")
        if not rootfs or not Path(rootfs).exists():
            raise RuntimeError(f"Rootfs not found: {rootfs}")

        merged = _setup_overlayfs(self.id, rootfs)
        self.config["merged_rootfs"] = str(merged)

        cg_path = _setup_cgroup(self.id, self.config.get("ram"), self.config.get("cpu"))
        self.config["cgroup"] = str(cg_path)

        log_file = DCK_DIR / "logs" / f"{self.id}.log"
        _ensure_dir(str(log_file.parent))
        self.config["log_file"] = str(log_file)

        self.config["status"] = "created"
        self.config["pid"] = None
        self.config.pop("network", None)
        self.save_state()

        self.start()

    def restart(self, timeout=10):
        """Stop and restart the container."""
        self.stop(timeout=timeout)
        self.start_existing()

    def remove(self):
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

    def exec_run(self, cmd, interactive=False, tty=False):
        pid = self.config.get("pid")
        if not pid:
            raise RuntimeError("Container not running")

        ns_types = ["mnt", "pid", "net", "uts", "ipc"]
        ns_args = []
        for ns in ns_types:
            ns_path = f"/proc/{pid}/ns/{ns}"
            if Path(ns_path).exists():
                ns_args += ["--target", str(pid), f"--{ns}"]

        if interactive or tty:
            full_cmd = ["nsenter"] + ns_args + list(cmd)
            subprocess.run(full_cmd)
        else:
            result = subprocess.run(
                ["nsenter"] + ns_args + list(cmd),
                capture_output=True, text=True, timeout=60,
            )
            return result.returncode, result.stdout, result.stderr

    def get_status(self):
        pid = self.config.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                return "running"
            except OSError:
                pass
        return self.config.get("status", "stopped")


def list_containers(all_containers=False):
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
