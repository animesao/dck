# dck — Native Linux Container Runtime

A lightweight container runtime that pulls OCI images directly from Docker Hub and runs them using Linux namespaces, cgroups v2, and overlayfs. **No Docker daemon required.**

## Quick Install

```bash
curl -sSL https://raw.githubusercontent.com/animesao/dck/main/install.sh | bash
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
dck save nginx:alpine nginx.tar.gz   # save image to archive
dck load nginx.tar.gz                # load image from archive
dck commit mycontainer myimage:tag   # commit container to new image
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
dck exec -it mycontainer /bin/sh      # run command in running container
dck ssh mycontainer                   # interactive shell
dck logs mycontainer                  # show logs (last 50 lines)
dck logs -f mycontainer               # follow logs
dck inspect mycontainer               # show full config
```

### Config File (up/down)

Define services in `dck.json`, `dck.toml`, or `dck.yaml`:

```json
{
  "services": {
    "web": {
      "image": "nginx:alpine",
      "ports": {"80/tcp": 8080},
      "volumes": {"./html": "/usr/share/nginx/html"},
      "restart": "always"
    },
    "db": {
      "image": "mariadb:10",
      "env": {"MYSQL_ROOT_PASSWORD": "secret"},
      "volumes": {"db_data": "/var/lib/mysql"}
    }
  }
}
```

```bash
dck up        # start all services from config
dck down      # stop all services from config
dck up -f myconfig.json   # use specific config file
```

### Presets

Built-in one-command presets for common applications:

```bash
dck preset list                  # list all presets
dck preset info paper            # show preset details
dck preset apply -d paper       # run Paper Minecraft server
```

Available presets: `paper`, `purpur`, `forge`, `spigot`, `nginx`, `apache`, `mariadb`, `postgres`, `redis`, `node`, `python`, `golang`, `lamp`, `rust`, `factorio`, `terraria`.

Preset parameters use `{param or default}` syntax:

```bash
dck preset apply -d paper -P ram=4096 -P max_players=50 -P difficulty=hard
```

### Pterodactyl Eggs

Create and apply Pterodactyl-compatible server eggs:

```bash
dck egg list                        # list available eggs
dck egg validate egg.json           # validate an egg file
dck egg create myegg -f egg.json    # save an egg
dck egg install myegg mycontainer   # apply egg to container
```

Egg format (JSON/TOML):

```json
{
  "meta": {"author": "dck", "version": "1.0", "description": "Paper server"},
  "startup": "java -Xms{MEMORY}M -Xmx{MEMORY}M -jar server.jar --nogui",
  "stop": "stop",
  "image": "itzg/minecraft-server:latest",
  "environment": {"MEMORY": "1024"},
  "variables": [
    {"name": "Memory", "env_variable": "MEMORY", "default_value": "1024",
     "rules": "required|integer|min:512|max:65536"}
  ],
  "volumes": {"server_data": "/data"}
}
```

### System

```bash
dck system prune          # remove stopped containers, overlays, logs
dck system prune -a       # also remove all images
dck doctor                # system readiness check
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
| `-w, --workdir` | Working directory |
| `-h, --hostname` | Container hostname |
| `--entrypoint` | Override entrypoint |
| `--restart` | Restart policy (`no`, `always`, `on-failure`) |
| `--external-ip` | External IP for port URL display |

## Architecture

```
dck pull nginx          dck run -p 8080:80 nginx
      │                        │
      ▼                        ▼
  ┌──────────┐           ┌──────────┐
  │runtime.py│           │ cli.py   │
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
           └── rootfs/        ├── namespaces (mnt/pid/net/uts/ipc/cgroup)
                               ├── veth pair + dck0 bridge + iptables
                               └── ~/.dck/containers/{id}.json
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
├── eggs/            # user-defined Pterodactyl eggs
└── network_ips.json # allocated IP pool
```

## License

MIT
