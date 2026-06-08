# dck — Lightweight OCI Container Runtime

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
dck run -d -n web -p 8080:80 nginx:alpine
curl http://localhost:8080
```

## Requirements

### Linux
- `unshare` + `nsenter` (util-linux)
- `ip` (iproute2)
- `iptables`
- `iptables-save`
- `pgrep` (procps)
- `mount` / `umount`
- Kernel: namespaces (PID, mount, net, UTS, IPC), overlayfs

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

### Build from source
```bash
# HTTPS (default)
git clone https://gitlab.com/animesao/dck.git && cd dck
go build -o dck .
sudo install dck /usr/local/bin/

# HTTP fallback (if your VPS blocks HTTPS to gitlab.com)
git clone http://gitlab.com/animesao/dck.git /tmp/dck
cd /tmp/dck && go build -o dck . && sudo install dck /usr/local/bin/

# SSH (if you have a key on GitLab)
git clone git@gitlab.com:animesao/dck.git
cd dck && go build -o dck . && sudo install dck /usr/local/bin/
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
dck run -d -n web -p 8080:80 nginx:alpine

# With environment variables
dck run -d -n pg -p 5432:5432 \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_DB=myapp \
  postgres:16

# With volume mounts
dck run -d -n data -v /host/data:/container/data alpine sleep infinity

# With restart policy (auto-start on boot via bootstrap)
dck run -d --restart always -n app -p 3000:3000 node:20 npm start

# Custom hostname
dck run -h myserver --rm alpine hostname
```

### Container Management
```bash
dck ps                 # Running containers
dck ps -a              # All containers (shows real status — checks PID liveness)
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

# Attach — shows full log history then live stdin/stdout stream
# Console-serve creates a Unix socket; attach connects as a client
# Container keeps running when you Ctrl+C out of attach
dck attach web              # Attach to main process
```

### Network & Ports
```bash
# Port mapping: -p HOST_PORT:CONTAINER_PORT
#   HOST_PORT      — the port on your server (where you connect to)
#   CONTAINER_PORT — the port the application listens on INSIDE the container

dck run -d -p 8080:80 nginx:alpine       # nginx listens on 80 inside → exposed on 8080
dck run -d -p 443:80 nginx:alpine        # nginx listens on 80 inside → exposed on 443
dck run -d -p 25565:25565 minecraft      # minecraft listens on 25565 inside → 25565
dck run -d -p 5432:5432 postgres:16      # postgres listens on 5432 inside → 5432

# iptables rules are automatically created/removed
# Bridge network: 10.0.2.0/24
# Each container gets a unique IP on dck0 bridge
```

> **Important:** The second number is the port INSIDE the container. If your app listens on 80
> and you use `-p 443:443`, traffic goes to port 443 inside the container where nothing is listening.
> Check with `dck logs <id>` (shows real requests inside the container).
>
> If it doesn't work — check UFW: `ufw status` (port must be ALLOW).

## Run Options Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-d` | Detach (run in background) | `false` |
| `-n, --name` | Container name | auto-generated |
| `-p` | Port mapping `host:container` (`-p 8080:80` = host:8080 → container:80) | - |
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
| `always` | Always restart on boot (via `dck bootstrap`), even after manual stop |
| `on-failure` | Restart only if exit code != 0 |

## Examples

### Web Server (Nginx)
```bash
dck pull nginx:alpine
dck run -d -n web -p 80:80 nginx:alpine
curl localhost
dck logs -f web
dck stop web && dck rm web
```

### PostgreSQL with Persistent Data
```bash
dck run -d --restart always \
  -n pg \
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
  -n mariadb \
  -p 3306:3306 \
  -v mariadb_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=secret \
  -e MYSQL_DATABASE=wordpress \
  mariadb:10

mysql -h localhost -u root -psecret wordpress
```

### MySQL 8
```bash
dck run -d --restart always \
  -n mysql \
  -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=myapp \
  -e MYSQL_USER=appuser \
  -e MYSQL_PASSWORD=apppass \
  mysql:8

mysql -h localhost -u appuser -papppass myapp
```

### Redis Cache
```bash
dck run -d --restart always \
  -n redis \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:7 --appendonly yes

redis-cli -h localhost ping
```

### Node.js App
```bash
mkdir myapp && cd myapp
cat > index.js << 'EOF'
const http = require('http');
const server = http.createServer((req, res) => {
  res.end('Hello from dck!\n');
});
server.listen(3000);
EOF

dck run -d --restart always \
  -n myapp \
  -p 3000:3000 \
  -v $(pwd):/app \
  node:20 node /app/index.js

curl http://localhost:3000
```

### Python Flask App
```bash
cat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)
@app.route('/')
def hello():
    return 'Hello from dck!'
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOF

cat > requirements.txt << 'EOF'
flask==3.0.0
EOF

dck run -d --restart always \
  -n flask \
  -p 5000:5000 \
  -v $(pwd):/app \
  python:3.11-slim sh -c "\
    pip install -r /app/requirements.txt && \
    python /app/app.py"

curl http://localhost:5000
```

### Multiple Minecraft Servers (different ports)

```bash
# Server 1 — Paper 1.20.4 on port 25565
dck run -d --restart always \
  -n mc-paper \
  -p 25565:25565 \
  -v mc_paper_data:/data \
  -e EULA=TRUE \
  -e TYPE=PAPER \
  -e VERSION=1.20.4 \
  -e MEMORY=4G \
  itzg/minecraft-server

# Server 2 — Vanilla on port 25566
dck run -d --restart always \
  -n mc-vanilla \
  -p 25566:25565 \
  -v mc_vanilla_data:/data \
  -e EULA=TRUE \
  -e MEMORY=2G \
  -e DIFFICULTY=hard \
  itzg/minecraft-server

dck ps                    # Both running
dck attach mc-paper       # Console for server 1 (Ctrl+C to detach)
dck attach mc-vanilla     # Console for server 2
```

### Minecraft Server (Paper with Plugins)
```bash
dck run -d --restart always \
  -n mc-paper \
  -p 25565:25565 \
  -v mc_paper_data:/data \
  -e EULA=TRUE \
  -e TYPE=PAPER \
  -e VERSION=1.20.4 \
  -e MEMORY=4G \
  -e PLUGINS=https://ci.dmulloy2.net/job/ProtocolLib/lastSuccessfulBuild/artifact/target/ProtocolLib.jar \
  itzg/minecraft-server
```

### Nginx Reverse Proxy
```bash
dck run -d --restart always \
  -n nginx \
  -p 80:80 -p 443:443 \
  -v nginx_conf:/etc/nginx/conf.d \
  -v nginx_html:/usr/share/nginx/html \
  nginx:alpine
```

### NocoDB (Database GUI)
```bash
dck run -d --restart always \
  -n nocodb \
  -p 8080:8080 \
  -v nocodb_data:/usr/app/data \
  nocodb/nocodb:latest
```

### Discord Bot (Python)
```bash
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

dck run -d --restart always \
  -n discord-bot \
  -v $(pwd):/bot \
  python:3.11-slim sh -c "\
    pip install -r /bot/requirements.txt && python /bot/bot.py"
```

### Discord Bot (Node.js)
```bash
mkdir discord-js-bot && cd discord-js-bot
cat > index.js << 'EOF'
const { Client, GatewayIntentBits } = require('discord.js');
const client = new Client({ intents: [GatewayIntentBits.Guilds] });
client.on('ready', () => console.log(`Logged in as ${client.user.tag}`));
client.on('interactionCreate', async (interaction) => {
  if (!interaction.isChatInputCommand()) return;
  if (interaction.commandName === 'ping')
    await interaction.reply('Pong!');
});
client.login(process.env.TOKEN);
EOF

cat > package.json << 'EOF'
{"name":"discord-bot","dependencies":{"discord.js":"^14.14.1"}}
EOF

dck run -d --restart always \
  -n discord-bot-js \
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
async def start(update, context):
    await update.message.reply_text("Hello from dck!")
async def ping(update, context):
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
  -n tg-bot \
  -v $(pwd):/bot \
  python:3.11-slim sh -c "\
    pip install -r /bot/requirements.txt && python /bot/bot.py"
```

### Multi-Container Setup (App + DB)
```bash
# Run PostgreSQL
dck run -d --restart always \
  -n db \
  -p 5432:5432 \
  -e POSTGRES_DB=myapp \
  -e POSTGRES_PASSWORD=secret \
  postgres:16

# Run your app (connects via host IP)
dck run -d --restart always \
  -n app \
  -p 8080:80 \
  -e DATABASE_URL=postgres://postgres:secret@HOST_IP:5432/myapp \
  nginx:alpine
```

### Nginx + PHP (LAMP-Style)
```bash
# Database
dck run -d --restart always -n db \
  -v db_data:/var/lib/mysql \
  -e MARIADB_ROOT_PASSWORD=root \
  mariadb:10

# PHP app with nginx frontend
dck run -d --restart always -n app \
  -p 8080:80 \
  -v html:/var/www/html \
  php:8-apache
```

### Cron Jobs via systemd
```bash
# Nightly database backup
cat > /etc/systemd/system/dck-backup.service << 'EOF'
[Unit]
Description=dck nightly backup

[Service]
Type=oneshot
ExecStart=/usr/local/bin/dck run --rm -v pg_data:/data postgres:16 tar czf /backup/pg-$(date +%Y%m%d).tar.gz /data
EOF

cat > /etc/systemd/system/dck-backup.timer << 'EOF'
[Unit]
Description=Nightly backup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl enable --now dck-backup.timer
```

## Config File (`dck.toml`)

Define all your containers in a single `dck.toml` file. Create it in your project
directory or in `~/.dck/dck.toml`.

```toml
[container.web]
image = "nginx:alpine"
ports = ["443:80", "80:80"]
volumes = ["./html:/usr/share/nginx/html"]
restart = "always"

[container.app]
image = "python:3.11-slim"
command = "python3 app.py"
ports = ["5000:5000"]
volumes = ["./app:/app"]
env = { FLASK_ENV = "production", SECRET_KEY = "change-me" }
restart = "always"

[container.db]
image = "postgres:16"
ports = ["5432:5432"]
volumes = ["pg_data:/var/lib/postgresql/data"]
env = { POSTGRES_PASSWORD = "secret", POSTGRES_DB = "myapp" }
restart = "always"
```

Then start everything at once:

```bash
dck up              # Create/start all containers from dck.toml
dck up web          # Start only the web container
dck up -f /path/to/dck.toml   # Custom config path
```

Stop and remove:

```bash
dck down            # Stop/remove all containers from dck.toml
dck down web        # Stop/remove only web
dck down -a         # Remove ALL containers (ignore config)
```

When you run `dck up`:
1. Searches for `dck.toml` (current dir → `~/.dck/`)
2. Pulls missing images
3. Creates containers with `--restart always` by default
4. Starts all containers — exactly like `dck run -d ...`

### Config Fields

| Field | Description | Example |
|-------|-------------|---------|
| `image` | Container image (required) | `"nginx:alpine"` |
| `command` | Startup command | `"python3 app.py"` |
| `ports` | Port mappings | `["443:80", "3000:3000"]` |
| `volumes` | Volume mounts | `["./data:/data"]` |
| `env` | Environment variables | `{ KEY = "val" }` |
| `restart` | Restart policy | `"always"` (default), `"no"`, `"on-failure"` |
| `hostname` | Container hostname | `"myserver"` |

### Examples with dck.toml

#### Web Server + Database

Put this in your project as `dck.toml`, then run `dck up`:

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
dck up         # starts both web + db
curl localhost # → nginx
```

#### Python Flask App + PostgreSQL

```toml
[container.app]
image = "python:3.11-slim"
command = "python3 app.py"
ports = ["5000:5000"]
volumes = ["./app:/app"]
env = { FLASK_ENV = "production", DATABASE_URL = "postgres://postgres:secret@HOST_IP:5432/myapp" }
restart = "always"

[container.db]
image = "postgres:16"
ports = ["5432:5432"]
env = { POSTGRES_PASSWORD = "secret", POSTGRES_DB = "myapp" }
volumes = ["pg_data:/var/lib/postgresql/data"]
restart = "always"
```

```bash
dck up app db         # start app + database
curl localhost:5000   # → Hello from dck!
```

#### Minecraft Server (Paper with Plugins)

```toml
[container.mc]
image = "itzg/minecraft-server"
ports = ["25565:25565"]
volumes = ["mc_data:/data"]
env = { EULA = "TRUE", TYPE = "PAPER", VERSION = "1.20.4", MEMORY = "4G", DIFFICULTY = "hard" }
restart = "always"
```

```bash
dck up mc
# connect in Minecraft: server_ip:25565
dck console mc        # server console
dck logs -f mc        # follow logs
```

#### Discord Bot (Python)

```toml
[container.discord-bot]
image = "python:3.11-slim"
command = "python bot.py"
volumes = ["./discord-bot:/bot"]
workdir = "/bot"  # will be /bot in container
env = { DISCORD_TOKEN = "YOUR_BOT_TOKEN" }
restart = "always"
```

```bash
mkdir discord-bot && cd discord-bot
# create bot.py with your code
cat > bot.py << 'EOF'
import discord, os
from discord.ext import commands
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")
bot.run(os.environ["DISCORD_TOKEN"])
EOF

# create requirements.txt
echo "discord.py==2.3.2" > requirements.txt
```

Configure `dck.toml` above and run:

```bash
pip download -r discord-bot/requirements.txt -d discord-bot/pkgs  # pre-download deps
dck up discord-bot
```

#### Telegram Bot

```toml
[container.tg-bot]
image = "python:3.11-slim"
command = "python bot.py"
volumes = ["./telegram-bot:/bot"]
env = { TELEGRAM_TOKEN = "YOUR_BOT_TOKEN" }
restart = "always"
```

```bash
mkdir telegram-bot && cd telegram-bot
cat > bot.py << 'EOF'
from telegram import Update
from telegram.ext import Application, CommandHandler
import os
async def start(update, context):
    await update.message.reply_text("Hello from dck!")
app = Application.builder().token(os.environ["TELEGRAM_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
EOF
echo "python-telegram-bot==20.7" > requirements.txt
```

```bash
dck up tg-bot
```

#### Node.js App + Redis

```toml
[container.app]
image = "node:20"
command = "node index.js"
ports = ["3000:3000"]
volumes = ["./app:/app"]
env = { REDIS_URL = "redis://HOST_IP:6379" }
restart = "always"

[container.redis]
image = "redis:7"
command = "redis-server --appendonly yes"
ports = ["6379:6379"]
volumes = ["redis_data:/data"]
restart = "always"
```

```bash
dck up
curl localhost:3000
```

#### WordPress (Nginx + PHP + MariaDB)

```toml
[container.db]
image = "mariadb:10"
volumes = ["wp_db:/var/lib/mysql"]
env = { MARIADB_ROOT_PASSWORD = "rootpass", MARIADB_DATABASE = "wordpress", MARIADB_USER = "wp", MARIADB_PASSWORD = "wppass" }
restart = "always"

[container.php]
image = "php:8-fpm"
volumes = ["./wordpress:/var/www/html"]
restart = "always"

[container.web]
image = "nginx:alpine"
ports = ["80:80"]
volumes = ["./wordpress:/var/www/html", "./nginx.conf:/etc/nginx/conf.d/default.conf"]
restart = "always"
```

#### Reverse Proxy (Nginx + multiple apps)

```toml
[container.proxy]
image = "nginx:alpine"
ports = ["80:80", "443:443"]
volumes = ["./nginx.conf:/etc/nginx/conf.d/default.conf", "./ssl:/etc/nginx/ssl"]
restart = "always"

[container.app1]
image = "node:20"
command = "node server.js"
volumes = ["./app1:/app"]
restart = "always"

[container.app2]
image = "python:3.11-slim"
command = "python app.py"
volumes = ["./app2:/app"]
restart = "always"
```

All containers start with one command:

```bash
dck up
```

And stop with another:

```bash
dck down
```

## Auto-Start on Boot (`dck bootstrap`)

`dck` has no daemon. Instead, it uses a systemd oneshot service
that starts all containers with `--restart always` on boot.

```bash
# Install the systemd service
dck bootstrap --install

# Start all containers now (without reboot)
dck bootstrap
```

After reboot, systemd automatically calls `dck bootstrap`,
which brings up all containers with the `--restart always` policy.

### How it works

```
System boot
      │
      ▼
systemd starts dck-bootstrap.service (Type=oneshot, KillMode=process)
      │
      ▼
dck bootstrap reads /root/.dck/containers/*.json
      │
      ▼
For each container with "restart":"always":
  1. Recreates overlayfs (upper/work/merged)
  2. Runs unshare --fork --pid --mount --net --uts --ipc
  3. Sets up veth pair (dck0 ↔ container)
  4. Adds iptables DNAT (PREROUTING + OUTPUT) and FORWARD ACCEPT
  5. Cleans old DNAT rules for this port (to avoid duplicates)
      │
      ▼
bootstrap finishes, containers keep running
(systemd does NOT kill them thanks to KillMode=process)
```

### Why `KillMode=process`?

Systemd with `Type=oneshot` defaults to `KillMode=process-group`.
When `dck bootstrap` finishes, systemd sends SIGTERM to the entire **process group**,
including the `unshare` child process. `unshare` forwards SIGTERM into the container
(via `--kill-child`) — and nginx/app dies.

`KillMode=process` tells systemd to send SIGTERM only to the main process
(bootstrap), which was going to exit anyway. Child processes
(unshare, nginx) keep running.

### Crash recovery with per-container systemd unit

If you need guaranteed restart after a crash (even if dck monitor hasn't reacted yet),
create a separate systemd service for a specific container:

```bash
cat > /etc/systemd/system/dck-web.service << 'EOF'
[Unit]
Description=dck web container
After=network.target
BindsTo=dck-bootstrap.service

[Service]
Type=exec
ExecStart=/usr/local/bin/dck run --rm -p 443:80 nginx:alpine
Restart=always
RestartSec=5
KillMode=process

[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now dck-web
```

## How Port Forwarding Works

```
External request → 193.23.220.15:443
      │
      ▼
PREROUTING DNAT: 443 → 10.0.2.5:80  (redirect)
      │
      ▼
FORWARD ACCEPT: traffic to 10.0.2.5:80 allowed
      │
      ▼
dck0 bridge → veth → eth0 (10.0.2.5) → nginx (port 80)
```

Three iptables rules per port:

| Chain | Purpose |
|-------|---------|
| `PREROUTING DNAT` | Redirects incoming packets from host port to container IP |
| `OUTPUT DNAT` | Redirects packets originating from the host itself (localhost → container) |
| `FORWARD ACCEPT` | Allows traffic forwarding to the container |

On each start, `dck` removes old DNAT rules for this port
(via `iptables-save` + parsing) to avoid duplicates.

### UFW (Uncomplicated Firewall)

`dck` automatically:
- Enables `ip_forward` (sysctl)
- Adds `ufw route allow in/out on dck0`
- After reboot: `dck bootstrap` calls `EnsureNetBase()`,
  which restores all network settings

## Storage

All data stored in `~/.dck/` (or `/root/.dck/` for root):

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

### Why `/root/.dck/` for root?

Systemd starts root services with `HOME=/`, not `/root`.
`dck` detects this via `os.Getuid() == 0` and uses `/root/.dck/`
directly, without relying on the `$HOME` variable.

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
       ▼                   │  iptables:       │
  ~/.dck/images/           │  • PREROUTING    │
                           │  • OUTPUT        │
                           │  • FORWARD       │
                           └────────┬─────────┘
                                      │
                                 ~/.dck/containers/
```

### Process Tree

#### Detached mode (dck run -d)
```
dck run -d
  ├─ unshare --fork --pid --mount --net --uts --ipc dck init <id>
  │   └─ dck init (chroot → mounts → wait eth0 → exec java -jar paper.jar)
  │       └─ java (PID 1 inside the container)
  └─ dck console-serve <id>
      ├─ reads stdout pipe from unshare
      ├─ writes to log file
      ├─ creates Unix socket /root/.dck/consoles/<id>.sock
      └─ broadcasts stdin/stdout to all connected clients

dck attach <id> — connects to Unix socket
   └─ receives full log history → streams live output
```

`dck init` enters the container namespace, mounts overlayfs,
sets up `/proc`, `lo`, waits up to 20s for `eth0`, and
replaces itself (`syscall.Exec`) with the user's command
(nginx, sh, java, python, …).

`console-serve` is spawned by `dck run -d` with pipe file descriptors
(FD 3 = stdinW, FD 4 = stdoutR). It bridges the container's
stdin/stdout to a Unix socket, allowing multiple concurrent
`dck attach` clients. Unlike Docker, `dck attach` is **decoupled**
from the container's lifecycle — the container keeps running even
when no one is attached.

### Network Architecture
```
Host (10.0.2.1)                       Container (10.0.2.x)
┌─────────────────────────────────────────────────────────┐
│ ┌─────┐    ┌──────────┐         ┌────────────────────┐ │
│ │dck0 │────│ veth-xxx │─────────│ eth0 (10.0.2.5)    │ │
│ │bridge│   └──────────┘         │ lo                 │ │
│ └─────┘                         └────────────────────┘ │
│                                                          │
│ iptables:                                                │
│   nat PREROUTING DNAT 443 → 10.0.2.5:80                  │
│   nat OUTPUT      DNAT 443 → 10.0.2.5:80                 │
│   FORWARD ACCEPT tcp --dport 80 -d 10.0.2.5              │
│   nat POSTROUTING MASQUERADE 10.0.2.0/24 !dck0           │
│                                                          │
│ UFW:                                                      │
│   ufw route allow in/out on dck0                         │
└──────────────────────────────────────────────────────────┘
```

## State Management & Stale Detection

If a container was killed externally (kill -9, crash), its status in `dck ps`
stayed "running" forever. Now `dck` checks PID liveness:

- `dck ps` — checks `/proc/<pid>` for each "running" container
- `dck exec` — won't nsenter into a dead PID
- `dck logs` — works even for dead containers (reads the log file)
- `dck bootstrap` — always recreates containers with `--restart always`

### Duplicate DNAT Prevention

On each container start, `dck` removes existing DNAT rules
for the same port (via `iptables-save -t nat` + parsing the output),
so old rules don't accumulate and shadow the current ones.

```bash
# Manual cleanup (if something went wrong)
iptables -t nat -F PREROUTING
iptables -t nat -F OUTPUT
```

## Environment Variables
```bash
DCK_EXTERNAL_IP=1.2.3.4            # External IP for port URL display
DCK_DATA_DIR=/path/to/dck          # Override ~/.dck location
DCK_UPDATE_MIRROR=http://mirror...  # Custom update source (if HTTPS to gitlab is blocked)
```

## Troubleshooting

### Permission denied
```bash
# dck requires root for namespace creation
sudo dck run --rm alpine echo hello

# Or add capabilities (not recommended)
sudo setcap cap_sys_admin+ep /usr/local/bin/dck
```

### Container dies immediately after bootstrap
Symptom: `dck ps` shows "running", but `curl http://localhost:443` —
"No route to host". `dck logs <id>` shows SIGTERM.

Cause: systemd kills unshare/nginx along with bootstrap
(see `KillMode=process` section above).

Fix: reinstall the systemd unit:
```bash
dck bootstrap --install
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
iptables -t nat -L -n
iptables -L FORWARD -n

# Check UFW
ufw status verbose

# Debug: try connecting to container directly
dck exec <id> wget -qO- http://127.0.0.1:80
```

### No route to host after reboot
```bash
# 1. Check that bootstrap ran
systemctl status dck-bootstrap

# 2. Check iptables
iptables -t nat -L PREROUTING -n

# 3. Check that the container is alive
dck ps
ping -c 2 $(dck inspect <id> ip)  # or cat /root/.dck/containers/*.json | grep ip

# 4. If container is dead — restart manually
dck rm -f <id>
dck run -d --restart always -n web -p 443:80 nginx:alpine

# 5. If there are duplicate DNAT rules — flush them
iptables -t nat -F PREROUTING
iptables -t nat -F OUTPUT
```

### HTTPS to GitLab fails (SSL wrong version number)
Some VPS providers put a transparent HTTP proxy on port 443,
or there is a local DNAT rule redirecting HTTPS to plain HTTP:

```bash
# Check iptables for local redirects
iptables -t nat -L -n | grep ':443 '

# If you see something like:
#   DNAT tcp -- 0.0.0.0/0 0.0.0.0/0 tcp dpt:443 to:10.0.2.4:80
# Remove the rules:
iptables -t nat -D PREROUTING -p tcp --dport 443 -j DNAT --to-destination 10.0.2.4:80
iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination 10.0.2.4:80
```

If it's not a local DNAT but a provider-level block:
```bash
# Build from source via HTTP
git clone http://gitlab.com/animesao/dck.git /tmp/dck
cd /tmp/dck && go build -o dck . && install dck /usr/local/bin/

# Or via SSH (if you have a key on GitLab)
git clone git@gitlab.com:animesao/dck.git /tmp/dck
cd /tmp/dck && go build -o dck . && install dck /usr/local/bin/

# dck update tries: Go HTTP → curl → wget → git ls-remote (SSH)
# You can also set a mirror via DCK_UPDATE_MIRROR:
DCK_UPDATE_MIRROR=http://your-mirror dck update --check
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

## All Commands

| Command | Description |
|---------|-------------|
| `pull` | Pull image from Docker Hub |
| `run` | Create and start a container |
| `ps` | List containers (with PID liveness check) |
| `stop` | Stop a running container |
| `rm` | Remove a container |
| `exec` | Execute a command in a container |
| `console` | Open an interactive shell |
| `attach` | Attach to main process (full log history + live stdin/stdout via Unix socket) |
| `logs` | Show or follow container logs |
| `images` | List local images |
| `rmi` | Remove a local image |
| `up` | Create/start containers from `dck.toml` |
| `down` | Stop/remove containers from `dck.toml` |
| `bootstrap` | Start all containers with `--restart always` (auto-start on boot) |
| `inspect` | Show container details |
| `version` | Show dck version |
| `update` | Check for updates and self-update |

## Updates

```bash
# Check if a newer version is available
dck update --check

# Download and install the latest version
dck update

# Use a custom mirror (if GitLab is blocked)
DCK_UPDATE_MIRROR=http://your-mirror dck update
```

The update command tries multiple methods in order:
1. **Go HTTP client** (HTTPS)
2. **curl** (HTTPS)
3. **wget** (HTTPS)
4. **git ls-remote over SSH** (version check only)
5. `DCK_UPDATE_MIRROR` env var — full mirror with the same URL structure

If `dck update` doesn't work — build manually:
```bash
# HTTP (if HTTPS is blocked)
git clone http://gitlab.com/animesao/dck.git /tmp/dck
cd /tmp/dck && go build -o dck . && install dck /usr/local/bin/

# SSH (if you have a key on GitLab)
git clone git@gitlab.com:animesao/dck.git /tmp/dck
cd /tmp/dck && go build -o dck . && install dck /usr/local/bin/
```

## Changelog

### v1.4.0 (current)
- **`dck attach` rewritten** — uses Unix socket (Pterodactyl-style) via `console-serve` process
- **`console-serve`** — new daemon process spawned per container that bridges stdin/stdout to a Unix socket
- **Full log history on attach** — new clients automatically receive all existing log content before live streaming
- **Disconnect-safe** — container keeps running when you Ctrl+C out of `dck attach` (decoupled from container lifecycle)
- **Console-serve writes logs** — stdout/stderr go through console-serve, ensuring no data loss when `dck run -d` exits
- **Network readiness** — `dck init` waits up to 20s for `eth0` before starting CMD, fixing Minecraft/Paper container startup
- **Multi-container** — multiple containers on different ports work correctly
- **`dck start` / `dck restart`** — start/restart stopped containers preserving overlay layer
- **`dck stop`** — kills unshare parent with `--kill-child` for clean container teardown
- **`dck exec` / `dck console`** — uses `nsenter` to enter container namespaces
- **session.lock race fix** — recursive cleanup under volume mount sources
- **Socket cleanup** — console socket and `session.lock` removed on container stop/cleanup

### v1.3.0
- **`dck.toml` config file** — define all containers in one TOML file
- **`dck up`** — create/start containers from config (auto-pulls images, creates with --restart always)
- **`dck down`** — stop/remove containers from config
- **`dck down -a`** — remove ALL containers (ignore config)

### v1.2.1
- **KillMode=process** in systemd unit — containers no longer die after bootstrap
- **DNAT deduplication** — old DNAT rules are removed before adding new ones
- **PID liveness check** — `dck ps` shows real status instead of stale "running"
- **Improved bootstrap** — always recreates containers without race conditions
- **/root/.dck for root** — doesn't depend on systemd's `HOME=/`
- **Multi-transport update** — Go HTTP → curl → wget → git SSH
- **`DCK_UPDATE_MIRROR`** — env var for update mirror
- **Auto UFW ports** — `dck run -p` automatically opens ports in UFW, `dck rm` closes them
- **Fixed OUTPUT DNAT** — now restricted to local traffic only, won't hijack outbound HTTPS connections (e.g., to GitLab)

### v1.2.0
- OUTPUT DNAT rule (localhost → container)
- UFW route allow in/out on dck0
- ip_forward auto-configure
- Removed RemainAfterExit (systemd skip bug)
- --install no longer calls systemctl start (race fix)

### v1.1.0
- First stable release
- Pull/run/ps/stop/rm/logs/exec
- Bridge networking (dck0), iptables DNAT
- overlayfs, OCI image format
- restart policy, volume mounts, env vars
- bootstrap systemd service

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
| Port mapping | Yes (iptables DNAT PREROUTING + OUTPUT) | Yes |
| Restart policy | always, on-failure | always, on-failure, unless-stopped |
| Auto-start on boot | systemd oneshot (bootstrap) | systemd dockerd |
| Crash recovery | systemd per-container unit (manual) | Automatic via dockerd |
| Volume mounts | Yes (bind mount) | Yes (volumes, bind) |
| Environment | Yes | Yes |
| Rootless | No | Experimental |
| Stale PID detection | Yes (load-time check) | N/A (daemon tracks state) |
| DNAT deduplication | Yes (auto-clean on start) | N/A (single state) |

## Uninstall

### Linux
```bash
dck bootstrap --remove
sudo rm /usr/local/bin/dck
rm -rf ~/.dck
```

## License

MIT
