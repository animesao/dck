# dck — Simple Container Runtime

A lightweight container runtime written in Go. Pulls OCI images from Docker Hub
and runs them using Linux namespaces, overlayfs, and bridge networking.
**No Docker daemon required.**

## Quick Start

```bash
# Install (Linux - root)
curl -sSL https://gitlab.com/animesao/dck/-/raw/main/install.sh | sudo bash

# Run your first container
dck run --rm alpine echo "hello from dck!"

# Pull and run a web server
dck pull nginx:alpine
dck run -d --name web -p 8080:80 nginx:alpine
curl http://localhost:8080
```

## Requirements

### Linux
- `unshare` + `nsenter` (util-linux)
- `ip` (iproute2)
- `iptables`
- `pgrep` (procps)
- `mount` / `umount`
- Kernel: namespaces, overlayfs, cgroups v2

The installer will detect your distro and install all dependencies automatically.

### Windows
- CLI commands only (pull, ps, images, rmi)
- Container runtime requires Linux (WSL2 recommended)

## Installation

### Linux (auto-installer)
```bash
curl -sSL https://gitlab.com/animesao/dck/-/raw/main/install.sh | sudo bash
```

The installer will:
1. Detect your OS/distro
2. Install Go if missing
3. Install all required packages (util-linux, iproute2, iptables, procps, curl)
4. Install and enable **UFW** (opens port 22/tcp for SSH)
5. Enable **IP forwarding** (net.ipv4.ip_forward=1)
6. Build `dck` and install to `/usr/local/bin`
7. Verify the installation

### Windows
```powershell
powershell -c "iwr -useb https://gitlab.com/animesao/dck/-/raw/main/install.ps1 | iex"
```

### Build from source
```bash
git clone <repo> && cd dck
go build -o dck .
sudo install dck /usr/local/bin/
```

## Usage

### Image Management
```bash
dck pull alpine              # Pull latest Alpine
dck pull nginx:alpine        # Pull with tag
dck pull postgres:16         # Pull specific version
dck images                   # List local images
dck rmi nginx:alpine         # Remove image
```

### Running Containers
```bash
# One-shot command
dck run --rm alpine echo hello

# Interactive shell
dck run -it alpine sh
dck run -it ubuntu bash

# Detached web server
dck run -d --name web -p 8080:80 nginx:alpine

# With environment variables
dck run -d --name pg -p 5432:5432 \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_DB=myapp \
  postgres:16

# With volume mounts
dck run -d --name data -v /host/data:/container/data alpine sleep infinity

# With resource names and restart
dck run -d --restart always --name app -p 3000:3000 node:20 npm start

# Custom hostname
dck run -h myserver --rm alpine hostname
```

### Container Management
```bash
dck ps                 # Running containers
dck ps -a              # All containers
dck stop web           # Stop (SIGTERM + 10s + SIGKILL)
dck start web          # Start stopped container
dck restart web        # Restart container
dck rm web             # Remove stopped
dck rm -f web          # Force remove running
```

### Logs & Debug
```bash
dck logs web            # Last output
dck logs -f web         # Follow (tail -f)
dck exec web cat /etc/hostname
dck exec -it web /bin/sh    # Interactive command
dck console web             # Auto-detect and open shell
dck attach web              # Attach to main process
```

### Network & Ports
```bash
# Port mapping (host:container)
dck run -d -p 8080:80 nginx:alpine
dck run -d -p 25565:25565 itzg/minecraft-server
dck run -d -p 5432:5432 postgres:16
dck run -d -p 3000:3000 node:20

# iptables rules are automatically created/removed
# Bridge network: 10.0.2.0/24
# Each container gets a unique IP on dck0 bridge
```

## Run Options Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-d` | Detach (run in background) | `false` |
| `-n, --name` | Container name | auto-generated |
| `-p` | Port mapping `host:container[/proto]` | - |
| `-v` | Volume mount `src:dst` | - |
| `-e` | Environment variable `KEY=val` | - |
| `-i` | Interactive (keep STDIN open) | `false` |
| `-t` | Allocate pseudo-TTY | `false` |
| `--rm` | Auto-remove on exit | `false` |
| `--restart` | Restart policy | `no` |
| `-h` | Container hostname | container ID |
| `--entrypoint` | Override entrypoint | from image |
| `--tag` | Image tag | `latest` |

### Restart Policies
| Policy | Behavior |
|--------|----------|
| `no` | Do not restart (default) |
| `always` | Always restart, even after manual stop |
| `on-failure` | Restart only if exit code != 0 |

## Use Cases

### Minecraft Server
```bash
# Pull the image
dck pull itzg/minecraft-server

# Run the server
dck run -d --restart always \
  --name mc \
  -p 25565:25565 \
  -v mc_data:/data \
  -e EULA=TRUE \
  -e MEMORY=2G \
  -e DIFFICULTY=hard \
  -e MAX_PLAYERS=20 \
  itzg/minecraft-server

# Open server console
dck console mc

# Check logs
dck logs -f mc
```

### PostgreSQL Database
```bash
# Run PostgreSQL
dck run -d --restart always \
  --name pg \
  -p 5432:5432 \
  -v pg_data:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=strongpass \
  -e POSTGRES_DB=myapp \
  -e POSTGRES_USER=appuser \
  postgres:16

# Connect from host
psql -h localhost -U appuser -d myapp

# Backup database
dck exec pg pg_dump -U appuser myapp > backup.sql
```

### MariaDB / MySQL
```bash
dck run -d --restart always \
  --name mariadb \
  -p 3306:3306 \
  -v mariadb_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=secret \
  -e MYSQL_DATABASE=wordpress \
  mariadb:10
```

### Redis Cache
```bash
dck run -d --restart always \
  --name redis \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:7 --appendonly yes
```

### Node.js Bot / Web App
```bash
# Build your app
cat > app.js << 'EOF'
const http = require('http');
http.createServer((req, res) => {
  res.end('Hello from dck!');
}).listen(3000);
EOF

# Run with mounted code
dck run -d --restart always \
  --name myapp \
  -p 3000:3000 \
  -v $(pwd):/app \
  -w /app \
  node:20 node app.js

# Or with env config
dck run -d --restart always \
  --name bot \
  -e BOT_TOKEN=xxx \
  -e DATABASE_URL=postgres://... \
  node:20 npm start
```

### Python Web App
```bash
dck run -d --restart always \
  --name flask \
  -p 5000:5000 \
  -v $(pwd):/app \
  -w /app \
  python:3.11 python app.py
```

### Nginx Reverse Proxy
```bash
dck run -d --restart always \
  --name nginx \
  -p 80:80 -p 443:443 \
  -v nginx_conf:/etc/nginx/conf.d \
  -v nginx_html:/usr/share/nginx/html \
  -v nginx_certs:/etc/nginx/ssl \
  nginx:alpine
```

### NocoDB (Database GUI)
```bash
dck run -d --restart always \
  --name nocodb \
  -p 8080:8080 \
  -v nocodb_data:/usr/app/data \
  nocodb/nocodb:latest
```

### Rust / Go Builder
```bash
# Rust builder
dck run --rm -v $(pwd):/app -w /app rust:latest cargo build --release

# Go builder
dck run --rm -v $(pwd):/app -w /app golang:latest go build -o app .
```

### Full LAMP Stack
```bash
# Network for inter-container communication
dck run -d --restart always --name db \
  -e MARIADB_ROOT_PASSWORD=root \
  mariadb:10

dck run -d --restart always --name app \
  -p 8080:80 \
  -v html:/var/www/html \
  -e DB_HOST=db \
  --link db \
  php:8-apache
```

## Storage

All data stored in `~/.dck/`:

```
~/.dck/
├── images/          # Pulled OCI images (rootfs per tag)
│   └── library_nginx/
│       └── alpine/
│           ├── config.json
│           ├── manifest.json
│           ├── layers/      # Cached tar.gz layers
│           └── rootfs/      # Extracted root filesystem
├── containers/      # Container state files (*.json)
├── overlay/         # overlayfs upper/work/merged per container
│   └── <id>/
│       ├── upper/
│       ├── work/
│       └── merged/
├── logs/            # Container stdout/stderr logs
└── networks/        # IP allocation pool
```

## Architecture

```
dck pull nginx              dck run -p 8080:80 nginx
      │                           │
      ▼                           ▼
  ┌──────────┐             ┌──────────────────┐
  │   OCI    │             │    unshare       │
  │ Registry │             │  ┌────────────┐  │
  │  API v2  │             │  │ Namespaces │  │
  │          │             │  │ PID MOUNT   │  │
  │ Manifest │             │  │ NET UTS IPC │  │
  │ Layers   │             │  └────────────┘  │
  │ Config   │             │  overlayfs       │
  └────┬─────┘             │  bridge dck0     │
       │                   │  veth pair       │
       ▼                   │  iptables DNAT   │
  ~/.dck/images/           └────────┬─────────┘
                                    │
                               ~/.dck/containers/
```

### Network Architecture
```
Host                             Container
┌──────────────────────────────────────────────────┐
│ ┌─────┐    ┌──────────┐    ┌──────────────────┐ │
│ │dck0 │────│ veth-xxx │────│ eth0 (10.0.2.x)  │ │
│ │bridge│   └──────────┘    │ lo               │ │
│ │10.0.2.1│                 └──────────────────┘ │
│ └─────┘                                          │
│ iptables:                                        │
│   -t nat -A POSTROUTING -s 10.0.2.0/24 -j MASQ  │
│   -t nat -A PREROUTING -p tcp --dport 8080       │
│            -j DNAT --to 10.0.2.2:80              │
└──────────────────────────────────────────────────┘
```

## Environment Variables
```bash
DCK_EXTERNAL_IP=1.2.3.4    # External IP for port URL display
DCK_DATA_DIR=/path/to/dck  # Override ~/.dck location
```

## Troubleshooting

### Permission denied
```bash
# dck requires root for namespace creation
sudo dck run --rm alpine echo hello

# Or add capabilities (not recommended)
sudo setcap cap_sys_admin+ep /usr/local/bin/dck
```

### "unshare" not found
```bash
# Debian/Ubuntu
sudo apt-get install -y util-linux

# RHEL/Fedora
sudo dnf install -y util-linux
```

### Network issues
```bash
# Check bridge
ip link show dck0
ip addr show dck0

# Check iptables rules
sudo iptables -t nat -L -n
sudo iptables -L FORWARD -n

# Enable IP forwarding
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward
```

### Container won't start
```bash
# Check logs
dck logs <container-id>

# Check if image exists
dck images

# Verify system
dck doctor 2>/dev/null || echo "doctor not available, check manually:"
unshare --version
nsenter --version
ip link help
mount -V
```

## Uninstall

### Linux
```bash
sudo ./uninstall.sh
```

### Windows
```powershell
.\uninstall.ps1
```

Or manually:
```bash
sudo rm /usr/local/bin/dck
rm -rf ~/.dck
```

## All Commands

| Command | Description |
|---------|-------------|
| `pull` | Pull image from Docker Hub |
| `run` | Create and start a container |
| `ps` | List containers |
| `stop` | Stop a running container |
| `start` | Restart a stopped container |
| `restart` | Restart a container |
| `rm` | Remove a container |
| `exec` | Execute a command in a container |
| `console` | Open an interactive shell |
| `attach` | Attach to the main process |
| `logs` | Show or follow container logs |
| `images` | List local images |
| `rmi` | Remove a local image |
| `update` | Check for updates and self-update |

## Updates

```bash
# Check if a newer version is available
dck update --check

# Download and install the latest version
dck update
```

The update command fetches the latest version from the GitLab repository and
runs the installer to upgrade if a newer version is found.

## Comparison

| Feature | dck | Docker |
|---------|-----|--------|
| Daemon | No daemon | dockerd required |
| Binary size | ~5 MB | ~100+ MB |
| Dependencies | None (Go static) | Containerd, runc, etc. |
| Image format | OCI/Docker V2 | OCI/Docker V2 |
| Namespaces | PID, Mount, Net, UTS, IPC | All |
| OverlayFS | Yes | Yes |
| Bridge network | Yes (dck0) | Yes (docker0) |
| Port mapping | Yes (iptables) | Yes |
| Restart policy | always, on-failure | always, on-failure, unless-stopped |
| Volume mounts | Yes | Yes |
| Environment | Yes | Yes |
| Rootless | No | Experimental |

## License

MIT
