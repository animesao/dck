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
- Kernel: namespaces, overlayfs

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
git clone https://gitlab.com/animesao/dck.git && cd dck
go build -o dck .
sudo install dck /usr/local/bin/
```

## Usage

### Image Management
```bash
dck pull alpine              # Pull latest Alpine
dck pull nginx:alpine        # Pull with tag
dck pull postgres:16         # Pull specific version
dck pull python:3.11-slim    # Pull Python slim image
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

# With restart policy
dck run -d --restart always --name app -p 3000:3000 node:20 npm start

# Custom hostname
dck run -h myserver --rm alpine hostname
```

### Container Management
```bash
dck ps                 # Running containers
dck ps -a              # All containers
dck stop web           # Stop (SIGTERM + 10s + SIGKILL)
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
# Port mapping: -p HOST_PORT:CONTAINER_PORT
#   HOST_PORT       — порт на твоём сервере (через который заходишь)
#   CONTAINER_PORT  — порт, который слушает приложение ВНУТРИ контейнера

dck run -d -p 8080:80 nginx:alpine       # nginx слушает 80 внутри → открыто на 8080
dck run -d -p 443:80 nginx:alpine        # nginx слушает 80 внутри → открыто на 443
dck run -d -p 25565:25565 minecraft      # майнкрафт слушает 25565 внутри → 25565
dck run -d -p 5432:5432 postgres:16      # postgres слушает 5432 внутри → 5432

# iptables rules are automatically created/removed
# Bridge network: 10.0.2.0/24
# Each container gets a unique IP on dck0 bridge
```

> **Важно:** Второе число — это порт ВНУТРИ контейнера. Если приложение слушает 80,
> а ты делаешь `-p 443:443` — трафик уйдёт на 443 внутри контейнера, где ничего нет.
> Проверить можно через `dck logs <id>` (показывает реальные запросы внутри).
>
> Если не работает — проверь UFW: `ufw status` (порт должен быть ALLOW).

## Run Options Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-d` | Detach (run in background) | `false` |
| `-n, --name` | Container name | auto-generated |
| `-p` | Port mapping `host:container` (`-p 8080:80` = хост:8080 → контейнер:80) | - |
| `-v` | Volume mount `src:dst` | - |
| `-e` | Environment variable `KEY=val` | - |
| `-i` | Interactive (keep STDIN open) | `false` |
| `-t` | Allocate pseudo-TTY | `false` |
| `--rm` | Auto-remove on exit | `false` |
| `--restart` | Restart policy | `no` |
| `-h` | Container hostname | container ID |

### Restart Policies
| Policy | Behavior |
|--------|----------|
| `no` | Do not restart (default) |
| `always` | Always restart, even after manual stop |
| `on-failure` | Restart only if exit code != 0 |

## Examples

### Web Server (Nginx)
```bash
dck pull nginx:alpine
dck run -d --name web -p 80:80 nginx:alpine
curl localhost
dck logs -f web
dck stop web && dck rm web
```

### PostgreSQL with Persistent Data
```bash
dck run -d --restart always \
  --name pg \
  -p 5432:5432 \
  -v pg_data:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=strongpass \
  -e POSTGRES_DB=myapp \
  postgres:16

psql -h localhost -U postgres -d myapp
```

### MariaDB
```bash
dck run -d --restart always \
  --name mariadb \
  -p 3306:3306 \
  -v mariadb_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=secret \
  -e MYSQL_DATABASE=wordpress \
  mariadb:10

# Connect
mysql -h localhost -u root -psecret wordpress
```

### MySQL 8
```bash
dck run -d --restart always \
  --name mysql \
  -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=myapp \
  -e MYSQL_USER=appuser \
  -e MYSQL_PASSWORD=apppass \
  mysql:8

# Connect
mysql -h localhost -u appuser -papppass myapp

# Or with a custom config
dck run -d --restart always \
  --name mysql \
  -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  -v /path/to/my.cnf:/etc/mysql/conf.d/custom.cnf \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  mysql:8
```

### Redis Cache
```bash
dck run -d --restart always \
  --name redis \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:7 --appendonly yes

# Test connection
redis-cli -h localhost ping
```

### Node.js App
```bash
# Create a simple HTTP server
mkdir myapp && cd myapp
cat > index.js << 'EOF'
const http = require('http');
const server = http.createServer((req, res) => {
  res.end('Hello from dck!\n');
});
server.listen(3000);
EOF

# Build and run
dck run -d --restart always \
  --name myapp \
  -p 3000:3000 \
  -v $(pwd):/app \
  node:20 node /app/index.js

curl http://localhost:3000
```

### Python Flask App
```bash
# Create Flask app
cat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)
@app.route('/')
def hello():
    return 'Hello from dck!'
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOF

# Install dependencies and run
cat > requirements.txt << 'EOF'
flask==3.0.0
EOF

dck run -d --restart always \
  --name flask \
  -p 5000:5000 \
  -v $(pwd):/app \
  python:3.11-slim sh -c "\
    pip install -r /app/requirements.txt && \
    python /app/app.py"

curl http://localhost:5000
```

### Minecraft Server (Vanilla)
```bash
# Pull and run a vanilla Minecraft server
dck pull itzg/minecraft-server
dck run -d --restart always \
  --name mc \
  -p 25565:25565 \
  -v mc_data:/data \
  -e EULA=TRUE \
  -e MEMORY=2G \
  -e DIFFICULTY=hard \
  -e MAX_PLAYERS=20 \
  itzg/minecraft-server

dck console mc   # Open server console
dck logs -f mc   # Follow server logs
```

### Minecraft Server (Paper with Plugins)
```bash
dck run -d --restart always \
  --name mc-paper \
  -p 25565:25565 \
  -v mc_paper_data:/data \
  -e EULA=TRUE \
  -e TYPE=PAPER \
  -e VERSION=1.20.4 \
  -e MEMORY=4G \
  -e PLUGINS=https://ci.dmulloy2.net/job/ProtocolLib/lastSuccessfulBuild/artifact/target/ProtocolLib.jar \
  itzg/minecraft-server

# Plugins are auto-downloaded to /data/plugins/
```

### Minecraft Server (Modded — Forge)
```bash
dck run -d --restart always \
  --name mc-forge \
  -p 25565:25565 \
  -v mc_forge_data:/data \
  -e EULA=TRUE \
  -e TYPE=FORGE \
  -e VERSION=1.20.1 \
  -e MEMORY=6G \
  itzg/minecraft-server

# Add mods manually:
# dck exec mc-forge wget -O /data/mods/my-mod.jar https://example.com/mod.jar
```

### Minecraft Server (Modded — Fabric)
```bash
dck run -d --restart always \
  --name mc-fabric \
  -p 25565:25565 \
  -v mc_fabric_data:/data \
  -e EULA=TRUE \
  -e TYPE=FABRIC \
  -e VERSION=1.20.4 \
  -e MEMORY=4G \
  -e FABRIC_LOADER_VERSION=0.15.11 \
  -e FABRIC_INSTALLER_VERSION=1.0.0 \
  itzg/minecraft-server
```

### Minecraft — Backup World
```bash
# Manual backup
dck exec mc sh -c "tar czf /data/backups/world-\$(date +%Y%m%d-%H%M).tar.gz /data/world"

# Auto-backup via cron (on host)
echo "0 */6 * * * root dck exec mc tar czf /data/backups/world-\$(date +%%Y%%m%%d-%%H%%M).tar.gz /data/world" | sudo tee /etc/cron.d/mc-backup
```

### Multi-Container Setup (App + DB)
```bash
# Run PostgreSQL
dck run -d --restart always \
  --name db \
  -p 5432:5432 \
  -e POSTGRES_DB=myapp \
  -e POSTGRES_PASSWORD=secret \
  postgres:16

# Run your app (connects via host IP)
dck run -d --restart always \
  --name app \
  -p 8080:80 \
  -e DATABASE_URL=postgres://postgres:secret@HOST_IP:5432/myapp \
  nginx:alpine
```

### Cron Jobs (Scheduled Tasks)
```bash
# Run a backup every day via systemd/cron + dck
dck run --rm \
  -v pg_data:/var/lib/postgresql/data \
  postgres:16 tar czf /backup/pg-$(date +%Y%m%d).tar.gz /var/lib/postgresql/data
```

### Data-only Container
```bash
# Create a data volume container
dck run -d --name data \
  -v /backup:/data \
  alpine sleep infinity

# Copy data into it
dck exec data sh -c "echo 'my data' > /data/file.txt"

# Another container reads it
dck run --rm -v /backup:/data alpine cat /data/file.txt
```

### Rust / Go Builder
```bash
# Rust
dck run --rm \
  -v $(pwd):/app \
  rust:latest sh -c "cd /app && cargo build --release"

# Go
dck run --rm \
  -v $(pwd):/app \
  golang:latest sh -c "cd /app && go build -o app ."
```

### Nginx Reverse Proxy
```bash
dck run -d --restart always \
  --name nginx \
  -p 80:80 -p 443:443 \
  -v nginx_conf:/etc/nginx/conf.d \
  -v nginx_html:/usr/share/nginx/html \
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

### Discord Bot (Python — discord.py)
```bash
# Create bot
mkdir discord-bot && cd discord-bot
cat > bot.py << 'EOF'
import discord
from discord.ext import commands

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

bot.run("YOUR_BOT_TOKEN")
EOF

cat > requirements.txt << 'EOF'
discord.py==2.3.2
EOF

# Build and run
dck run -d --restart always \
  --name discord-bot-py \
  -v $(pwd):/bot \
  python:3.11-slim sh -c "\
    pip install -r /bot/requirements.txt && \
    python /bot/bot.py"
```

### Discord Bot (Node.js — discord.js)
```bash
# Create bot
mkdir discord-js-bot && cd discord-js-bot
cat > index.js << 'EOF'
const { Client, GatewayIntentBits } = require('discord.js');
const client = new Client({ intents: [GatewayIntentBits.Guilds] });

client.on('ready', () => {
  console.log(`Logged in as ${client.user.tag}`);
});

client.on('interactionCreate', async (interaction) => {
  if (!interaction.isChatInputCommand()) return;
  if (interaction.commandName === 'ping') {
    await interaction.reply('Pong!');
  }
});

client.login(process.env.TOKEN);
EOF

cat > package.json << 'EOF'
{
  "name": "discord-bot",
  "dependencies": { "discord.js": "^14.14.1" }
}
EOF

# Run
dck run -d --restart always \
  --name discord-bot-js \
  -v $(pwd):/bot \
  -e TOKEN=YOUR_BOT_TOKEN \
  node:20 sh -c "cd /bot && npm install && node index.js"
```

### Telegram Bot (Python)
```bash
mkdir telegram-bot && cd telegram-bot
cat > bot.py << 'EOF'
from telegram import Update
from telegram.ext import Application, CommandHandler

async def start(update: Update, context):
    await update.message.reply_text("Hello from dck!")

async def ping(update: Update, context):
    await update.message.reply_text("Pong!")

app = Application.builder().token("YOUR_BOT_TOKEN").build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))
app.run_polling()
EOF

cat > requirements.txt << 'EOF'
python-telegram-bot==20.7
EOF

dck run -d --restart always \
  --name tg-bot \
  -v $(pwd):/bot \
  python:3.11-slim sh -c "\
    pip install -r /bot/requirements.txt && \
    python /bot/bot.py"
```

### Nginx + PHP (LAMP-Style)
```bash
# Database
dck run -d --restart always --name db \
  -v db_data:/var/lib/mysql \
  -e MARIADB_ROOT_PASSWORD=root \
  mariadb:10

# PHP app with nginx frontend
dck run -d --restart always --name app \
  -p 8080:80 \
  -v html:/var/www/html \
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

# Verify system tools
unshare --version
nsenter --version
ip link help
mount -V
```

### Orphaned containers (detach-убил снаружи)
Если убить процесс nginx/приложения снаружи (через `kill`), контейнер остаётся
в статусе `running` в `dck ps`, а iptables правила и IP не очищаются.

```bash
# Принудительно удалить мёртвый контейнер
dck rm -f <id>

# Почистить висящие iptables правила
iptables -t nat -L PREROUTING -n --line-numbers
iptables -t nat -D PREROUTING <номер>

# Проверить, нет ли дублирующихся правил
iptables -t nat -L PREROUTING -n
```

> **Причина:** `dck run -d` завершает процесс сразу после запуска контейнера,
> монитор умирает вместе с ним. Контейнер живёт сам по себе, и если его убить
> снаружи — dck не узнает об этом. Всегда используй `dck stop` / `dck rm -f`.

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
| `rm` | Remove a container |
| `exec` | Execute a command in a container |
| `console` | Open an interactive shell |
| `attach` | Attach to the main process |
| `logs` | Show or follow container logs |
| `images` | List local images |
| `rmi` | Remove a local image |
| `version` | Show dck version |
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
