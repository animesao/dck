# dck — Native Linux Container Runtime

A lightweight container runtime that pulls OCI images directly from Docker Hub and runs them using Linux namespaces, cgroups v2, and overlayfs. **No Docker daemon required.**

## Quick Install

```bash
curl -sSL https://gitlab.com/animesao/dck/-/raw/main/install.sh | bash
```

Or via pip:
```bash
pip install .
```

## Requirements

- **Linux** (x86_64)
- **root** (or CAP_SYS_ADMIN) for namespace creation
- **binaries**: `mount`, `umount`, `ip` (iproute2), `iptables`, `nsenter` (util-linux)
- **cgroups v2** (`/sys/fs/cgroup/cgroup.controllers` exists)
- **OverlayFS** support in kernel

Check readiness:

```bash
dck doctor
```

## Usage

### Images

```bash
dck pull nginx:alpine       # pull from Docker Hub
dck images                  # list pulled images
dck rmi nginx:alpine        # remove image
```

### Run Containers

```bash
dck run -d -p 8080:80 nginx:alpine               # web server (detached)
dck run -it --rm ubuntu bash                      # interactive shell
dck run --rm alpine echo hello                    # one-shot
dck run -d --name pg -v /data/pg:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=secret postgres:16         # database
dck run -d --name app -p 3000:3000 --ram 512m --cpu 0.5 node:20 npm start
```

### Container Lifecycle

```bash
dck ps                # list running containers
dck ps -a             # all containers (including stopped)
dck stop mycontainer  # stop (SIGTERM + SIGKILL after 10s)
dck start mycontainer # restart a stopped container
dck restart mycontainer
dck rm mycontainer    # remove
dck rm -f mycontainer # force remove (stop + remove)
```

### Connect & Debug

```bash
dck exec -it mycontainer /bin/sh      # run command
dck ssh mycontainer                    # alias for exec -it /bin/sh
dck logs mycontainer                   # show logs (last 50 lines)
dck logs -f mycontainer                # follow logs
dck inspect mycontainer                # show full config
```

### Interactive Create (with Paper Minecraft)

```bash
dck create --paper
# interactive prompts: version, ports, volumes, resources
# generates run.sh launcher for game servers
```

### Minecraft Paper Server

```bash
dck create --paper
# 1. select version
# 2. set port 25565
# 3. set volume /data/mc
# 4. run generated launcher:
cd /data/mc && ./run.sh
```

## Run Options

| Option | Description |
|--------|-------------|
| `-n, --name` | Container name |
| `--tag` | Image tag (default: latest) |
| `-p, --port` | Port mapping `host:container[/proto]` |
| `-v, --volume` | Volume mount `host:container` |
| `-e, --env` | Environment variable `KEY=value` |
| `--env-file` | Read environment from file |
| `-i, --interactive` | Keep STDIN open |
| `-t, --tty` | Allocate pseudo-TTY |
| `-d, --detach` | Run in background |
| `--rm` | Auto-remove on exit |
| `--ram` | Memory limit (`512m`, `2g`) |
| `--cpu` | CPU limit (`0.5`, `2`) |
| `--pids-limit` | PID limit (default: 1000) |
| `-w, --workdir` | Working directory |
| `-u, --user` | Username or UID |
| `--read-only` | Read-only root filesystem |
| `-h, --hostname` | Container hostname |
| `--entrypoint` | Override entrypoint |
| `--restart` | Restart policy (`no`, `always`, `on-failure`) |
| `--cap-add` | Add Linux capability |
| `--cap-drop` | Drop Linux capability |
| `--privileged` | Extended privileges |

## Architecture

```
dck pull nginx          dck run -p 8080:80 nginx
      │                        │
      ▼                        ▼
  ┌──────────┐           ┌──────────┐
  │  oci.py  │           │ cli.py   │
  │ pull     │           │ run cmd  │
  └────┬─────┘           └────┬─────┘
       │                      │
       ▼                      ▼
  ┌──────────┐           ┌──────────┐
  │  OCI     │           │runtime.py│
  │ Registry │           │Container │
  │  API v2  │           │ .create  │
  └──────────┘           │ .start   │
       │                 │ .stop    │
       ▼                 │ .exec    │
  ~/.dck/images/         │ .logs    │
   └── library_nginx/    └────┬─────┘
       └── alpine/            │
           ├── config.json    ├── overlayfs (upper/work/merged)
           ├── manifest.json  ├── cgroups v2  (memory.max, cpu.max)
           └── rootfs/        ├── namespaces (NS/NET/PID/UTS/IPC)
                              ├── veth pair + bridge + iptables
                              └── ~/.dck/containers/{id}.json

  network.py ─── dck0 bridge (10.0.0.0/24)
         ├── allocate_ip / release_ip
         ├── setup_veth (veth pair + nsenter)
         └── forward_port (iptables DNAT)
```

## Storage

All data stored in `~/.dck/`:

```
~/.dck/
├── images/          # pulled OCI images (rootfs per tag)
│   └── library_nginx/
│       └── alpine/
│           ├── config.json
│           ├── manifest.json
│           ├── layers/       # cached tar.gz layers
│           └── rootfs/       # extracted root filesystem
├── containers/      # container state files (*.json)
├── overlay/         # overlayfs upper/work/merged per container
├── logs/            # container stdout/stderr logs
└── network_ips.json # allocated IP pool
```

## System Commands

```bash
dck doctor     # check native runtime readiness
dck update     # update dck to latest version
dck uninstall  # remove dck completely
```

## Remote Access

dck does not include SSH server functionality. To access a container:

```bash
dck exec -it mycontainer /bin/sh   # interactive shell
dck ssh mycontainer                 # same thing
```

For persistent remote access, run an SSH server inside the container or use the host's SSH to manage containers.

## License

MIT
