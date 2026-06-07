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

### Minecraft Server (Vanilla)
```bash
dck pull itzg/minecraft-server
dck run -d --restart always \
  -n mc \
  -p 25565:25565 \
  -v mc_data:/data \
  -e EULA=TRUE \
  -e MEMORY=2G \
  -e DIFFICULTY=hard \
  -e MAX_PLAYERS=20 \
  itzg/minecraft-server

dck console mc
dck logs -f mc
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

## Auto-Start on Boot (`dck bootstrap`)

`dck` не имеет демона. Вместо этого используется systemd oneshot сервис,
который при загрузке запускает все контейнеры с `--restart always`.

```bash
# Установить systemd сервис
dck bootstrap --install

# Запустить все контейнеры сейчас (без перезагрузки)
dck bootstrap
```

После перезагрузки systemd автоматически вызывает `dck bootstrap`,
который поднимает все контейнеры с политикой `--restart always`.

### Как это работает

```
Загрузка системы
      │
      ▼
systemd запускает dck-bootstrap.service (Type=oneshot, KillMode=process)
      │
      ▼
dck bootstrap читает /root/.dck/containers/*.json
      │
      ▼
Для каждого контейнера с "restart":"always":
  1. Пересоздаёт overlayfs (upper/work/merged)
  2. Запускает unshare --fork --pid --mount --net --uts --ipc
  3. Настраивает veth пару (dck0 ↔ container)
  4. Добавляет iptables DNAT (PREROUTING + OUTPUT) и FORWARD ACCEPT
  5. Очищает старые DNAT правила для этого порта (чтобы не было дубликатов)
      │
      ▼
bootstrap завершается, контейнеры продолжают работать
(systemd НЕ убивает их благодаря KillMode=process)
```

### Почему `KillMode=process`?

Systemd с `Type=oneshot` по умолчанию использует `KillMode=process-group`.
Когда `dck bootstrap` завершается, systemd посылает SIGTERM всей **process group**,
включая дочерний процесс `unshare`. `unshare` форвардит SIGTERM в контейнер
(через `--kill-child`) — и nginx/приложение умирает.

`KillMode=process` говорит systemd посылать SIGTERM только главному процессу
(bootstrap), который и так собирался завершиться. Дочерние процессы
(unshare, nginx) остаются жить.

### Принудительный перезапуск при падении

Если нужен гарантированный restart после crash (даже если монитор dck не успел
среагировать), создай отдельный systemd сервис на конкретный контейнер:

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
Внешний запрос → 193.23.220.15:443
      │
      ▼
PREROUTING DNAT: 443 → 10.0.2.5:80  (перенаправление)
      │
      ▼
FORWARD ACCEPT: разрешён трафик к 10.0.2.5:80
      │
      ▼
dck0 bridge → veth → eth0 (10.0.2.5) → nginx (порт 80)
```

Три iptables правила на каждый порт:

| Цепочка | Назначение |
|----------|------------|
| `PREROUTING DNAT` | Перенаправляет входящие пакеты с порта хоста на IP контейнера |
| `OUTPUT DNAT` | Перенаправляет пакеты, идущие с самого хоста (localhost → container) |
| `FORWARD ACCEPT` | Разрешает форвардинг трафика к контейнеру |

При каждом запуске `dck` удаляет старые DNAT правила для этого порта
(через `iptables-save` + разбор), чтобы избежать дубликатов.

### UFW (Uncomplicated Firewall)

`dck` автоматически:
- Включает `ip_forward` (sysctl)
- Добавляет `ufw route allow in/out on dck0`
- После перезагрузки: `dck bootstrap` вызывает `EnsureNetBase()`,
  который восстанавливает все сетевые настройки

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

Systemd запускает root-сервисы с `HOME=/`, а не `/root`.
`dck` определяет это по `os.Getuid() == 0` и использует `/root/.dck/`
напрямую, чтобы не зависеть от переменной `$HOME`.

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
```
dck bootstrap (завершается после запуска)
  └─ unshare --fork --pid --mount --net --uts --ipc dck init <id>
      └─ dck init (chroot → mounts → exec nginx)
          └─ nginx (PID 1 внутри контейнера)
```

`dck init` входит в namespace контейнера, монтирует overlayfs,
настраивает `/proc`, `lo`, и заменяет себя (`syscall.Exec`)
на команду пользователя (nginx, sh, python, …).

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

Если контейнер был убит снаружи (kill -9, crash), его статус в `dck ps`
оставался "running" навсегда. Теперь `dck` проверяет живость PID:

- `dck ps` — проверяет `/proc/<pid>` для каждого "running" контейнера
- `dck exec` — не пытается nsenter в мёртвый PID
- `dck logs` — работает даже для мёртвых контейнеров (читает файл)
- `dck bootstrap` — всегда пересоздаёт контейнер с `--restart always`

### Duplicate DNAT Prevention

При каждом запуске контейнера `dck` удаляет существующие DNAT правила
для того же порта (через `iptables-save -t nat` + разбор вывода),
чтобы старые правила не накапливались и не shadow-или актуальные.

```bash
# Ручная очистка (если что-то пошло не так)
iptables -t nat -F PREROUTING
iptables -t nat -F OUTPUT
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

### Container dies immediately after bootstrap
Симптом: `dck ps` показывает "running", но `curl http://localhost:443` —
"No route to host". `dck logs <id>` показывает SIGTERM.

Причина: systemd убивает unshare/nginx вместе с bootstrap
(см. раздел про `KillMode=process`).

Решение: переустановить systemd unit:
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
# 1. Проверить что bootstrap отработал
systemctl status dck-bootstrap

# 2. Проверить iptables
iptables -t nat -L PREROUTING -n

# 3. Проверить что контейнер жив
dck ps
ping -c 2 $(dck inspect <id> ip)  # или cat /root/.dck/containers/*.json | grep ip

# 4. Если контейнер мёртв — запустить вручную
dck rm -f <id>
dck run -d --restart always -n web -p 443:80 nginx:alpine

# 5. Если есть дубликаты DNAT — очистить
iptables -t nat -F PREROUTING
iptables -t nat -F OUTPUT
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
| `ps` | List containers (с проверкой живости PID) |
| `stop` | Stop a running container |
| `rm` | Remove a container |
| `exec` | Execute a command in a container |
| `console` | Open an interactive shell |
| `attach` | Attach to the main process |
| `logs` | Show or follow container logs |
| `images` | List local images |
| `rmi` | Remove a local image |
| `bootstrap` | Start all containers with `--restart always` (автостарт при boot) |
| `inspect` | Show container details |
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

## Changelog

### v1.2.1 (current)
- **KillMode=process** в systemd unit — контейнеры больше не умирают после bootstrap
- **DNAT deduplication** — старые DNAT правила удаляются перед добавлением новых
- **PID liveness check** — `dck ps` показывает реальный статус, а не stale "running"
- **Улучшен bootstrap** — всегда пересоздаёт контейнеры без race condition
- **/root/.dck для root** — не зависит от systemd `HOME=/`

### v1.2.0
- OUTPUT DNAT rule (localhost → container)
- UFW route allow in/out on dck0
- ip_forward auto-configure
- Removed RemainAfterExit (systemd skip bug)
- --install не запускает systemctl start (race fix)

### v1.1.0
- Первая стабильная версия
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
