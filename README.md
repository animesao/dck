<p align="center">
<  <img src="https://img.shields.io/badge/version-v1.19.0--stalbal.95dfa13-blue?style=flat-square">
  <img src="https://img.shields.io/badge/go-1.18+-00ADD8?style=flat-square&logo=go">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  <img src="https://img.shields.io/badge/no%20daemon-%E2%9C%93-brightgreen?style=flat-square">
</p>

<h1 align="center">dck — Lightweight Container Runtime</h1>

<p align="center">
  <b>No daemon. No Docker. Just containers.</b><br>
  ~5 MB static binary, zero daemon, OCI images, bridge networking.
</p>

```bash
dck run --rm alpine echo "hello from dck!"
dck run -d -n web -p 8080:80 nginx:alpine
curl http://localhost:8080
```

---

## Quick Start

```bash
# Install via apt (Debian/Ubuntu)
curl -sSL https://raw.githubusercontent.com/animesao/dck/main/scripts/install-apt.sh | sudo bash

# Or build from source (Linux)
curl -sSL https://raw.githubusercontent.com/animesao/dck/main/install.sh | sudo bash

# dck-client
curl -sSL https://raw.githubusercontent.com/animesao/dck-client/main/install.sh | sudo bash

# Pull & run
dck pull nginx:alpine
dck run -d -n web -p 8080:80 nginx:alpine

# Check
dck ps
curl http://localhost:8080

# Logs & exec
dck logs web
dck exec web cat /etc/hostname

# Interactive
dck run -it alpine sh

# Stop & remove
dck stop web && dck rm web
```

**Requirements:** Linux with `unshare`, `nsenter`, `ip`, `iptables`, `mount`, `pgrep` +
PID/Mount/Net/UTS/IPC namespaces + overlayfs.

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Image** | Read-only rootfs (`python:3.11-slim`, `nginx:alpine`). Pulled once via `dck pull`. |
| **Container** | Image + writable overlay layer. Changes live in the overlay, not the image. |
| **Overlay** | Diff layer on top of the image. Persists across restarts — packages stay installed. |
| **Volume** | Host bind mount into the container. `-v /opt/mybot:/bot` mounts `/opt/mybot` as `/bot`. |
| **Network** | Every container gets IP `10.0.2.X` on bridge `dck0`. Host at `10.0.2.1`. |

```
Host:        dck0  10.0.2.1/24
Container A: eth0  10.0.2.2
Container B: eth0  10.0.2.3

A → host:      ping 10.0.2.1      (host is gateway)
host → A:      ping 10.0.2.2      (host has route)
A → B:         ping 10.0.2.3      (via bridge)
A → B's port:  curl 10.0.2.1:8080 (DNAT: host_port → B:container_port)
```

---

## Usage

### Image Commands

```bash
dck pull alpine                    # Pull image
dck pull nginx:alpine              # With tag
dck images                         # List local images
dck rmi nginx:alpine               # Remove image
```

### Container Lifecycle

```bash
dck run --rm alpine echo hi                 # One-shot
dck run -d -n web -p 80:80 nginx            # Detached
dck run -it alpine sh                       # Interactive
dck ps -a                                   # List all containers
dck stop web                                # Stop
dck start web                               # Start stopped
dck restart web                             # Restart
dck rm -f web                               # Force remove
dck rename web web-new                      # Rename container
dck system prune                            # Remove unused containers and images
dck info                                    # System information
dck commit web my-image:v1                  # Create image from container
```

### Logs & Attach

```bash
dck logs web                                # Last output
dck logs -f web                             # Follow
dck attach web                              # Full history + live stdin/stdout
dck exec web cat /etc/hostname              # Run command inside
dck exec -it web /bin/sh                    # Interactive shell
dck console web                             # Auto-detect shell
dck top web                                 # Processes inside container
dck cp web:/etc/hostname .                  # Copy file from container
dck cp app.py web:/app/                     # Copy file to container
```

`dck attach` is **Ctrl+C safe** — container keeps running.

> **exec vs attach:** `attach` connects to the main process stdin/stdout. `exec` runs a new command inside the container. `console` is a shortcut for `exec -it` with auto-detected shell.

### Options

| Flag | Description |
|------|-------------|
| `-d` | Detach (background) |
| `-n` | Container name |
| `-p` | Port mapping `host:container` |
| `-v` | Volume mount `src:dst` |
| `-e` | Environment variable (repeatable) |
| `-i` | Interactive (keep stdin) |
| `-t` | Allocate TTY |
| `--rm` | Auto-remove on exit |
| `--restart` | Restart policy: `no`, `always`, `on-failure`, `unless-stopped` |
| `-h` | Hostname |
| `--startup` | Startup script (inline or `@file`) — overrides CMD |
| `--healthcheck-cmd` | Health check command |
| `--healthcheck-interval` | Health check interval (seconds) |
| `--healthcheck-retries` | Health check retries |
| `--healthcheck-timeout` | Health check timeout (seconds) |

---

## Examples

### Web Server

```bash
dck run -d --restart always -n web -p 80:80 nginx:alpine
curl localhost
```

### Python Flask App

```bash
mkdir -p /opt/flask-app && cd /opt/flask-app
cat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)
@app.route('/')
def hello():
    return 'Hello from dck!'
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOF
echo "flask==3.0.0" > requirements.txt

dck run -d --restart always \
  -n flask -p 5000:5000 \
  -v /opt/flask-app:/app \
  python:3.11-slim sh -c "\
    pip install -r /app/requirements.txt && \
    python /app/app.py"
curl http://localhost:5000
```

### PostgreSQL

```bash
dck run -d --restart always \
  -n pg -p 5432:5432 \
  -v pg_data:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_DB=myapp \
  postgres:16
psql -h localhost -U postgres -d myapp
```

### MySQL

```bash
dck run -d --restart always \
  -n mysql -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=myapp \
  mysql:8
mysql -h localhost -u root -prootpass myapp
```

### Redis

```bash
dck run -d --restart always \
  -n redis -p 6379:6379 \
  -v redis_data:/data \
  redis:7 --appendonly yes
redis-cli -h localhost ping
```

### Minecraft Server (itzg/minecraft-server)

```bash
dck run -d --restart always \
  -n mc -p 25565:25565 \
  -v mc_data:/data \
  -e EULA=TRUE -e TYPE=PAPER -e VERSION=1.20.4 \
  itzg/minecraft-server
```

### Minecraft Server (чистый Java + `--startup`)

Сначала создай скрипт `mc-startup.sh`:

```bash
#!/bin/sh
set -e
SERVER_DIR="/data"
SERVER_JAR="server.jar"
MAX_MEM="${DCK_MEMORY:-2G}"
echo "eula=true" > "$SERVER_DIR/eula.txt"
if [ ! -f "$SERVER_DIR/$SERVER_JAR" ]; then
  curl -fsSL -o "$SERVER_DIR/$SERVER_JAR" \
    "https://fill-data.papermc.io/v1/objects/e708e8c132dc143ffd73528cccb9532e2eb17628b1a0eee74469bf466c7003f8/paper-1.21.11-116.jar"
fi
exec java -Xms512M -Xmx$MAX_MEM -jar "$SERVER_DIR/$SERVER_JAR" nogui
```

Запуск:

```bash
dck run -d --restart always \
  -n mc-paper -p 25565:25565 \
  -v mc_data:/data --memory 4G --cpus 4 \
  --startup @mc-startup.sh \
  eclipse-temurin:21-jdk
```

Для Paper 1.16.5 (Java 16):

```bash
#!/bin/sh
set -e
SERVER_DIR="/data"
SERVER_JAR="server.jar"
MAX_MEM="${DCK_MEMORY:-2G}"
echo "eula=true" > "$SERVER_DIR/eula.txt"
if [ ! -f "$SERVER_DIR/$SERVER_JAR" ]; then
  curl -fsSL -o "$SERVER_DIR/$SERVER_JAR" \
    "https://fill-data.papermc.io/v1/objects/e67da4851d08cde378ab2b89be58849238c303351ed2482181a99c2c2b489276/paper-1.16.5-794.jar"
fi
exec java -Xms512M -Xmx$MAX_MEM -jar "$SERVER_DIR/$SERVER_JAR" nogui
```

```bash
dck run -d --restart always \
  -n mc-1165 -p 25565:25565 \
  -v mc1165_data:/data --memory 4G --cpus 4 \
  --startup @mc-startup.sh \
  eclipse-temurin:16-jdk
```

### Node.js App

```bash
mkdir -p /opt/node-app && cd /opt/node-app
cat > index.js << 'EOF'
const http = require('http');
http.createServer((req, res) => res.end('Hello from dck!\n')).listen(3000);
EOF

dck run -d --restart always \
  -n node-app -p 3000:3000 \
  -v /opt/node-app:/app \
  node:20 node /app/index.js
curl http://localhost:3000
```

### Bot + Database (Two Containers)

Start the database first, then the bot connects via `10.0.2.1`:

```bash
# 1. MySQL
dck run -d --restart always \
  -n bot-mysql -p 3306:3306 \
  -v bot_mysql_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=botdb \
  -e MYSQL_USER=bot -e MYSQL_PASSWORD=botpass \
  mysql:8

# 2. Discord bot
mkdir -p /opt/discord-bot && cd /opt/discord-bot
cat > bot.py << 'EOF'
import discord
from discord.ext import commands
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
bot.run(os.environ["BOT_TOKEN"])
EOF
echo "discord.py==2.3.2" > requirements.txt

dck run -d --restart always \
  -n discord-bot \
  -v /opt/discord-bot:/bot \
  -e BOT_TOKEN=your_token_here \
  python:3.11-slim sh -c "\
    pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null \
      || pip install -r /bot/requirements.txt; \
    exec python /bot/bot.py"
```

Packages install into the overlay — they persist across restarts. The `--dry-run` check skips pip if requirements haven't changed (pip 21.1+).

---

## dck-wings — Container Management Agent

[dck-wings](https://github.com/animesao/dck-wings) is a REST API daemon for managing containers remotely. It runs as a systemd service and allows frontends (like dck-panel) to control containers over HTTP.

```bash
# Install
bash <(curl -sfL https://raw.githubusercontent.com/animesao/dck-wings/main/install.sh)

# Start
systemctl enable --now dck-wings

# API (auth via Bearer token from /etc/dck-wings/config.toml)
curl -H "Authorization: Bearer <api_key>" http://localhost:8080/api/containers
```

---

## Auto-Start on Boot

```bash
dck bootstrap --install
```

Installs a systemd oneshot service. After reboot, all containers with `--restart always` start automatically.

```
System boot → systemd → dck-bootstrap.service → dck bootstrap
  └─ For each container with restart=always:
      1. Setup overlayfs
      2. Run unshare with namespaces
      3. Setup veth + iptables
```

---

## dck.toml (Multi-Container Config)

Define containers in a TOML file, start everything with one command.

```toml
[container.web]
image = "nginx:alpine"
ports = ["80:80", "443:80"]
volumes = ["./html:/usr/share/nginx/html"]
restart = "always"

[container.db]
image = "postgres:16"
ports = ["5432:5432"]
env = { POSTGRES_PASSWORD = "secret", POSTGRES_DB = "myapp" }
volumes = ["pg_data:/var/lib/postgresql/data"]
restart = "always"
```

```bash
dck up              # Create/start all containers
dck up web          # Start only web
dck down            # Stop/remove all
dck down -a         # Remove ALL containers (ignore config)
```

### Config Fields

| Field | Description | Example |
|-------|-------------|---------|
| `image` | Container image (required) | `"nginx:alpine"` |
| `command` | Startup command | `"python3 app.py"` |
| `ports` | Port mappings | `["443:80", "3000:3000"]` |
| `volumes` | Volume mounts | `["./data:/data"]` |
| `env` | Environment variables | `{ KEY = "val" }` |
| `restart` | Restart policy | `"always"` (default) |
| `hostname` | Container hostname | `"myserver"` |
| `healthcheck` | Health check config | `{ cmd = "...", interval = 30, retries = 3, timeout = 5 }` |

Healthcheck runs the command inside the container at the given interval. After `retries` consecutive failures, the container is killed and restarted.

---

## Startup Scripts

Use `--startup` to run a custom script instead of the image's default command:

```bash
# Inline script
dck run -d --startup "#!/bin/sh\necho 'Hello from startup'" alpine sleep infinity

# Load from file
dck run -d --startup @./myscript.sh ubuntu
```

The script is written to `/startup.sh` inside the container and executed via `/bin/sh`. When a startup script is present, it **overrides** the normal `CMD`/`entrypoint`.

The following environment variables are injected automatically for startup scripts:

| Variable | Description |
|----------|-------------|
| `DCK_CONTAINER_ID` | Container ID |
| `DCK_CONTAINER_NAME` | Container name |
| `DCK_IMAGE_NAME` | Image name |
| `DCK_IMAGE_TAG` | Image tag |
| `DCK_HOSTNAME` | Container hostname |
| `DCK_MEMORY` | Memory limit (bytes) |
| `DCK_CPU` | CPU limit (cores) |
| `DCK_IP` | Container IP address |
| `DCK_RESTART` | Restart policy |

## Architecture

```
Storage: /root/.dck/

images/        OCI rootfs per tag
containers/    State JSON files
overlay/       upper/work/merged per container
logs/          Container stdout/stderr
consoles/      Unix sockets for attach
networks/      IP allocation pool

dck run -d
  ├─ unshare --fork --pid --mount --net --uts --ipc dck init <id>
  │   └─ dck init → chroot overlay → setup /proc/lo/eth0 → exec CMD
  └─ dck console-serve <id>
      ├─ reads stdout pipe
      ├─ writes to log file
      ├─ listens on Unix socket
      └─ broadcasts to all attach clients
```

---

## Comparison

| Feature | dck | Docker |
|---------|-----|--------|
| Daemon | No daemon | dockerd required |
| Binary size | ~5 MB | ~100+ MB |
| Namespaces | PID, Mount, Net, UTS, IPC | All |
| Bridge network | dck0 (10.0.2.0/24) | docker0 |
| Port mapping | iptables DNAT | iptables DNAT |
| Auto-start | systemd oneshot | systemd dockerd |
| Image format | OCI/Docker V2 | OCI/Docker V2 |

---

## Changelog

**v1.13.0** — Added `--startup` flag for custom startup scripts (inline or `@file`), `--healthcheck-*` flags, DCK_* environment variables injected into containers, resource limit enforcement via cgroups v2.

**v1.11.0** — Debian packaging, APT repository, snap packaging, release workflow.

**v1.10.0** — `dck stats` command with live CPU/RAM/IO/PIDs from cgroup v2.

**v1.4.7** — `dck attach` rewritten (Unix socket, history + live, Ctrl+C safe), console-serve daemon, network readiness, overlay stale mount detection, multi-container fixes.

**v1.3.0** — `dck.toml` config, `dck up`/`dck down`.

**v1.2.1** — KillMode=process, DNAT dedup, PID liveness check, UFW auto-ports.

**v1.1.0** — First stable release.

---

## Updating

```bash
dck update
```

Downloads the latest binary and replaces `/usr/local/bin/dck`.

---

## Uninstall

```bash
dck bootstrap --remove
rm /usr/local/bin/dck
rm -rf ~/.dck
```

## License

[MIT](LICENSE)
