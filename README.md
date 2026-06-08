# dck — Lightweight Container Runtime

No daemon. No Docker. Just containers.

```bash
dck run --rm alpine echo "hello from dck!"
dck run -d -n web -p 8080:80 nginx:alpine
curl http://localhost:8080
```

---

## Quick Start

```bash
# Install (Linux)
curl -sSL https://gitlab.com/animesao/dck/-/raw/main/install.sh | sudo bash

# Pull and run
dck pull nginx:alpine
dck run -d -n web -p 8080:80 nginx:alpine

# Check
dck ps                     # see running containers
curl http://localhost:8080  # see nginx

# Logs and exec
dck logs web               # see what the process wrote
dck exec web cat /etc/hostname  # run a command inside

# Interactive shell
dck run -it alpine sh      # ephemeral, --rm by default

# Stop and remove
dck stop web
dck rm web
```

## Requirements

- Linux with `unshare`, `nsenter`, `ip`, `iptables`, `mount`, `pgrep`
- Kernel: PID/Mount/Net/UTS/IPC namespaces + overlayfs

---

## Key Concepts

**Image** — read-only rootfs (like `python:3.11-slim`, `nginx:alpine`).
`dck pull` downloads it once.

**Container** — image + writable overlay layer. Every `pip install`,
config change, or file create lives in the overlay, not in the image.
The image stays clean.

**Overlay** — diff layer on top of the image. When you restart a container,
the overlay persists — packages stay installed, logs from previous runs
are gone (they went to stdout, which goes to `dck logs`).

**Volume** — a bind mount from the host filesystem into the container.
`-v /opt/mybot:/bot` makes `/opt/mybot` visible as `/bot` inside.

**Network** — every container gets IP `10.0.2.X` on bridge `dck0`.
The host is reachable at `10.0.2.1`. To reach container B from container A,
connect to `10.0.2.1:<host_port>` (iptables DNAT forwards to B).

---

## How Containers See Each Other

```
Host:           dck0  10.0.2.1/24
Container A:    eth0  10.0.2.2
Container B:    eth0  10.0.2.3

A → host:         ping 10.0.2.1        (works, host is gateway)
host → A:         ping 10.0.2.2        (works, host has route)
A → B:            ping 10.0.2.3        (works, via bridge)
A → B's port:     curl http://10.0.2.1:8080   (DNAT: host_port → B:container_port)
```

Ports are published **on the host** via iptables DNAT. To access a
container's port from another container, use `10.0.2.1:<host_port>`.

---

## Bot Deployment

### 1. Bot Without Database — Just a Script

#### Python (Discord, Telegram, any)

```bash
# Put your bot files on the server
mkdir -p /opt/mybot
# copy bot.py, requirements.txt into /opt/mybot/

# Run — pip install + start in one container
dck run -d --restart always \
  -n mybot \
  -v /opt/mybot:/bot \
  -e BOT_TOKEN=your_token_here \
  python:3.11-slim sh -c "\
    pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null \
      || pip install -r /bot/requirements.txt; \
    exec python /bot/bot.py"

# Check
dck logs mybot
dck attach mybot
```

Packages install into the overlay layer — they persist across restarts.
The `--dry-run` check skips pip install on subsequent starts if
requirements haven't changed (pip 21.1+).

#### Discord.py

```bash
mkdir -p /opt/discord-bot && cd /opt/discord-bot

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

#### Node.js Discord Bot

```bash
mkdir -p /opt/discord-js-bot && cd /opt/discord-js-bot

cat > index.js << 'EOF'
const { Client, GatewayIntentBits } = require('discord.js');
const client = new Client({ intents: [GatewayIntentBits.Guilds] });
client.on('ready', () => console.log(`Logged in as ${client.user.tag}`));
client.on('interactionCreate', async (i) => {
  if (i.commandName === 'ping') await i.reply('Pong!');
});
client.login(process.env.TOKEN);
EOF

cat > package.json << 'EOF'
{"name":"bot","dependencies":{"discord.js":"^14.14.1"}}
EOF

dck run -d --restart always \
  -n discord-js-bot \
  -v /opt/discord-js-bot:/bot \
  -e TOKEN=your_token_here \
  node:20 sh -c "cd /bot && npm install && node index.js"
```

#### Telegram Bot

```bash
mkdir -p /opt/tg-bot && cd /opt/tg-bot

cat > bot.py << 'EOF'
import os
from telegram import Update
from telegram.ext import Application, CommandHandler
async def start(update, context):
    await update.message.reply_text("Hello from dck!")
app = Application.builder().token(os.environ["TELEGRAM_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
EOF

echo "python-telegram-bot==20.7" > requirements.txt

dck run -d --restart always \
  -n tg-bot \
  -v /opt/tg-bot:/bot \
  -e TELEGRAM_TOKEN=your_token_here \
  python:3.11-slim sh -c "\
    pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null \
      || pip install -r /bot/requirements.txt; \
    exec python /bot/bot.py"
```

#### Generic Python

```bash
dck run -d --restart always \
  -n myapp \
  -v /path/to/app:/app \
  -e KEY=VAL \
  python:3.11-slim sh -c "\
    pip install --dry-run -r /app/requirements.txt -q 2>/dev/null \
      || pip install -r /app/requirements.txt; \
    exec python /app/main.py"
```

---

### 2. Database Containers (Standalone)

Run these **separately** — your app connects to them via the host IP `10.0.2.1`.

#### MySQL

```bash
dck run -d --restart always \
  -n mysql -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=myapp \
  -e MYSQL_USER=myuser \
  -e MYSQL_PASSWORD=mypass \
  mysql:8
```

Connect from another container: `host=10.0.2.1, user=myuser, password=mypass, db=myapp`

#### PostgreSQL

```bash
dck run -d --restart always \
  -n postgres -p 5432:5432 \
  -v pg_data:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=pgpass \
  -e POSTGRES_DB=myapp \
  postgres:16
```

Connect from another container: `host=10.0.2.1, user=postgres, password=pgpass, db=myapp`

#### MariaDB

```bash
dck run -d --restart always \
  -n mariadb -p 3306:3306 \
  -v mariadb_data:/var/lib/mysql \
  -e MARIADB_ROOT_PASSWORD=rootpass \
  -e MARIADB_DATABASE=myapp \
  -e MARIADB_USER=myuser \
  -e MARIADB_PASSWORD=mypass \
  mariadb:10
```

#### Redis

```bash
dck run -d --restart always \
  -n redis -p 6379:6379 \
  -v redis_data:/data \
  redis:7 --appendonly yes
```

Connect: `redis://10.0.2.1:6379`

#### SQLite (no separate container needed)

SQLite is a file-based DB. Mount a volume to persist the file:

```bash
dck run -d --restart always \
  -n myapp \
  -v /opt/myapp:/app \
  -v myapp_data:/data \
  python:3.11-slim sh -c "\
    pip install -r /app/requirements.txt && \
    python /app/app.py"
```

The bot writes to `/data/mydb.sqlite` — it persists in the `myapp_data` volume.

---

### 3. Bot + Database (Two Containers)

Start the database first (from section 2), then the bot connects via `10.0.2.1`.

#### Discord Bot + MySQL (economy, levels)

```bash
# 1. Start MySQL (from section 2)
dck run -d --restart always \
  -n bot-mysql -p 3306:3306 \
  -v bot_mysql_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=botdb \
  -e MYSQL_USER=bot \
  -e MYSQL_PASSWORD=botpass \
  mysql:8

# 2. Create bot files
mkdir -p /opt/discord-mysql-bot && cd /opt/discord-mysql-bot

cat > bot.py << 'EOF'
import discord, os, aiomysql
from discord.ext import commands
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

@bot.event
async def on_ready():
    bot.db = await aiomysql.create_pool(
        host=os.environ["DB_HOST"], port=3306,
        user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
        db=os.environ["DB_NAME"])
    print(f"Bot ready — DB connected")

@bot.command()
async def balance(ctx):
    async with bot.db.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT coins FROM users WHERE id=%s", (ctx.author.id,))
            row = await cur.fetchone()
    await ctx.send(f"You have {row[0] if row else 0} coins!")

bot.run(os.environ["BOT_TOKEN"])
EOF

echo -e "discord.py==2.6.4\naiomysql==0.2.0" > requirements.txt

# 3. Start bot
dck run -d --restart always \
  -n discord-mysql-bot \
  -v /opt/discord-mysql-bot:/bot \
  -e BOT_TOKEN=your_token_here \
  -e DB_HOST=10.0.2.1 \
  -e DB_USER=bot \
  -e DB_PASS=botpass \
  -e DB_NAME=botdb \
  python:3.11-slim sh -c "\
    pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null \
      || pip install -r /bot/requirements.txt; \
    exec python /bot/bot.py"
```

#### Discord Bot + PostgreSQL (analytics, JSON)

```bash
# 1. Start PostgreSQL
dck run -d --restart always \
  -n bot-pg -p 5432:5432 \
  -v bot_pg_data:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=pgpass \
  -e POSTGRES_DB=botdb \
  postgres:16

# 2. Bot files
mkdir -p /opt/discord-pg-bot && cd /opt/discord-pg-bot

cat > bot.py << 'EOF'
import discord, os, asyncpg
from discord.ext import commands
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

@bot.event
async def on_ready():
    bot.db = await asyncpg.create_pool(
        host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"], database=os.environ["DB_NAME"])
    print(f"Bot ready — PG connected")

@bot.command()
async def stats(ctx):
    async with bot.db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT messages, xp FROM user_stats WHERE user_id=$1",
            ctx.author.id)
    await ctx.send(f"Messages: {row['messages']}, XP: {row['xp']}" if row else "No stats")

bot.run(os.environ["BOT_TOKEN"])
EOF

echo -e "discord.py==2.6.4\nasyncpg==0.30.0" > requirements.txt

# 3. Start bot
dck run -d --restart always \
  -n discord-pg-bot \
  -v /opt/discord-pg-bot:/bot \
  -e BOT_TOKEN=your_token_here \
  -e DB_HOST=10.0.2.1 \
  -e DB_USER=postgres \
  -e DB_PASS=pgpass \
  -e DB_NAME=botdb \
  python:3.11-slim sh -c "\
    pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null \
      || pip install -r /bot/requirements.txt; \
    exec python /bot/bot.py"
```

#### Flask Web App + MySQL

```bash
# 1. Start MySQL
dck run -d --restart always \
  -n flask-mysql -p 3306:3306 \
  -v flask_mysql_data:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=webapp \
  -e MYSQL_USER=app \
  -e MYSQL_PASSWORD=apppass \
  mysql:8

# 2. Create app
mkdir -p /opt/flask-app && cd /opt/flask-app

cat > app.py << 'EOF'
from flask import Flask
import mysql.connector, os
app = Flask(__name__)

def get_db():
    return mysql.connector.connect(
        host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"], database=os.environ["DB_NAME"])

@app.route("/")
def hello():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM visits")
    count = cur.fetchone()[0]
    cur.execute("INSERT INTO visits DEFAULT VALUES")
    db.commit()
    return f"Visitor #{count + 1}"

app.run(host="0.0.0.0", port=5000)
EOF

echo -e "flask==3.0.0\nmysql-connector-python==9.2.0" > requirements.txt

# 3. Init table
sleep 5
dck exec flask-mysql mysql -u root -prootpass webapp \
  -e "CREATE TABLE IF NOT EXISTS visits (id INT AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"

# 4. Start Flask
dck run -d --restart always \
  -n flask-app -p 5000:5000 \
  -v /opt/flask-app:/app \
  -e DB_HOST=10.0.2.1 \
  -e DB_USER=app \
  -e DB_PASS=apppass \
  -e DB_NAME=webapp \
  python:3.11-slim sh -c "\
    pip install --dry-run -r /app/requirements.txt -q 2>/dev/null \
      || pip install -r /app/requirements.txt; \
    exec python /app/app.py"
```


#### Node.js + Redis (caching, sessions)

```bash
# 1. Start Redis
dck run -d --restart always \
  -n myredis -p 6379:6379 \
  -v redis_data:/data \
  redis:7 --appendonly yes

# 2. Create app
mkdir -p /opt/node-redis && cd /opt/node-redis

cat > index.js << 'EOF'
const express = require("express");
const redis = require("redis").createClient({ url: process.env.REDIS_URL });
const app = express();

app.get("/", async (req, res) => {
  await redis.connect();
  let c = await redis.get("visits") || 0;
  await redis.set("visits", ++c);
  await redis.disconnect();
  res.send(`Visitor #${c}`);
});

app.listen(3000);
EOF

echo '{"name":"app","dependencies":{"express":"4.21.0","redis":"4.7.0"}}' > package.json

# 3. Start Node.js
dck run -d --restart always \
  -n node-redis -p 3000:3000 \
  -v /opt/node-redis:/app \
  -e REDIS_URL=redis://10.0.2.1:6379 \
  node:20 sh -c "cd /app && npm install && node index.js"

curl http://localhost:3000  # Visitor #1
```

---

## Usage

### Image Commands

```bash
dck pull alpine              # Pull image
dck pull nginx:alpine        # With tag
dck images                   # List local images
dck rmi nginx:alpine         # Remove image
```

### Container Lifecycle

```bash
dck run --rm alpine echo hi          # One-shot
dck run -d -n web -p 80:80 nginx     # Detached
dck run -it alpine sh                # Interactive
dck ps                               # Running containers
dck ps -a                            # All containers
dck stop web                         # Stop
dck start web                        # Start stopped
dck restart web                      # Restart
dck rm web                           # Remove stopped
dck rm -f web                        # Force remove running
```

### Logs & Attach

```bash
dck logs web                         # Last output
dck logs -f web                      # Follow
dck attach web                       # Full history + live stdin/stdout
dck exec web cat /etc/hostname       # Run command inside
dck exec -it web /bin/sh             # Interactive shell
dck console web                      # Auto-detect shell
```

`dck attach` is **disconnect-safe** — Ctrl+C to detach, container keeps running.

`exec` vs `attach`:
- `dck attach <name>` — connect to the **main process** stdin/stdout (like `docker attach`)
- `dck exec <name> <cmd>` — **run a new command** inside the container (like `docker exec`)
- `dck console <name>` — auto-detect shell, shortcut for `dck exec -it <name> /bin/sh` or `/bin/bash`

> **Why `exec python bot.py`?** Without `exec`, the shell (`sh -c "..."`) stays
> as PID 1 and the Python process is its child. With `exec`, Python replaces
> the shell process — one less process, signals go directly to Python.

### Port Mapping

```bash
dck run -d -p 8080:80 nginx:alpine       # host:8080 → container:80
dck run -d -p 25565:25565 minecraft       # host:25565 → container:25565
dck run -d -p 5432:5432 postgres:16       # host:5432 → container:5432
```

Bridge network `10.0.2.0/24`, iptables DNAT rules created automatically.

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
| `--restart` | Restart policy: `no`, `always`, `on-failure` |
| `-h` | Hostname |

> `-w` and `--env-file` not implemented. Use `sh -c "cd /path && ..."` and `-e KEY=VAL`.

---

## Examples

### Web Server (Nginx)

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
  -n flask \
  -p 5000:5000 \
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

### MySQL / MariaDB

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

### Minecraft Server

```bash
# Single server
dck run -d --restart always \
  -n mc -p 25565:25565 \
  -v mc_data:/data \
  -e EULA=TRUE -e TYPE=PAPER -e VERSION=1.20.4 \
  itzg/minecraft-server

# Two servers on different ports
dck run -d --restart always \
  -n mc-paper -p 25565:25565 \
  -v mc_paper_data:/data \
  -e EULA=TRUE -e TYPE=PAPER -e VERSION=1.20.4 \
  itzg/minecraft-server

dck run -d --restart always \
  -n mc-vanilla -p 25566:25565 \
  -v mc_vanilla_data:/data \
  -e EULA=TRUE -e MEMORY=2G \
  itzg/minecraft-server

dck ps                         # Both running
dck attach mc-paper            # Console for server 1
dck attach mc-vanilla          # Console for server 2
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

### Nginx Reverse Proxy

```bash
dck run -d --restart always \
  -n proxy -p 80:80 -p 443:443 \
  -v nginx_conf:/etc/nginx/conf.d \
  -v nginx_html:/usr/share/nginx/html \
  -v ./ssl:/etc/nginx/ssl \
  nginx:alpine
```

### Multi-App Setup (App + DB)

```bash
# Database
dck run -d --restart always \
  -n db -p 5432:5432 \
  -e POSTGRES_DB=myapp -e POSTGRES_PASSWORD=secret \
  postgres:16

# App (connects via host IP)
dck run -d --restart always \
  -n app -p 8080:80 \
  -e DATABASE_URL=postgres://postgres:secret@HOST_IP:5432/myapp \
  nginx:alpine
```

---

## Auto-Start on Boot

```bash
dck bootstrap --install
```

Installs a systemd oneshot service. After reboot, all containers with
`--restart always` start automatically.

```bash
# Manual start (without reboot)
dck bootstrap
```

### How it works

```
System boot → systemd → dck-bootstrap.service → dck bootstrap
  └─ For each container with restart=always:
      1. Setup overlayfs
      2. Run unshare with namespaces
      3. Setup veth + iptables
```

`KillMode=process` prevents systemd from killing the containers when
bootstrap finishes.

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
dck up              # Create/start all containers from dck.toml
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

#### Healthcheck

dck runs the healthcheck command inside the container at the given interval.
After `retries` consecutive failures, the container is killed and restarted.

| Field | Default | Description |
|-------|---------|-------------|
| `cmd` | (required) | Shell command to run (exit 0 = healthy) |
| `interval` | 30 | Seconds between checks |
| `retries` | 3 | Consecutive failures before restart |
| `timeout` | 10 | Seconds before a single check is killed |

#### pip install: install only once

Packages install into the overlay layer. On restart, they're already there,
but `pip install` still checks every line. Skip it when nothing changed:

```bash
pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null \
  || pip install -r /bot/requirements.txt
```

`--dry-run` exits 0 if all packages are present (pip 21.1+). Older pip
doesn't support the flag, falls through to real install.

Combine with `exec` to avoid a dangling shell process:

```bash
sh -c "pip install --dry-run -r /req.txt -q 2>/dev/null || pip install -r /req.txt; exec python app.py"
```

### dck.toml Examples

**Minecraft Server:**
```toml
[container.mc]
image = "itzg/minecraft-server"
ports = ["25565:25565"]
volumes = ["mc_data:/data"]
env = { EULA = "TRUE", TYPE = "PAPER", VERSION = "1.20.4" }
restart = "always"
healthcheck = { cmd = "mc-health", interval = 60, retries = 2 }
```

**Discord Bot (with pip cache):**
```toml
[container.discord-bot]
image = "python:3.11-slim"
command = "sh -c 'pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null || pip install -r /bot/requirements.txt; exec python /bot/bot.py'"
volumes = ["./discord-bot:/bot"]
env = { BOT_TOKEN = "your_token_here" }
restart = "always"
healthcheck = { cmd = "python -c 'import discord'", interval = 60, retries = 2 }
```

**Bot + PostgreSQL (two containers):**
```toml
[container.bot]
image = "python:3.11-slim"
command = "sh -c '\
  pip install --dry-run -r /bot/requirements.txt -q 2>/dev/null \
    || pip install -r /bot/requirements.txt; \
  exec python /bot/bot.py'"
volumes = ["./bot:/bot"]
env = {
  BOT_TOKEN = "your_token_here",
  DB_HOST = "10.0.2.1",
  DB_USER = "postgres",
  DB_PASS = "pgpass",
  DB_NAME = "botdb"
}
restart = "always"
healthcheck = { cmd = "pg_isready -h $DB_HOST" }

[container.db]
image = "postgres:16"
ports = ["5432:5432"]
volumes = ["pg_data:/var/lib/postgresql/data"]
env = { POSTGRES_PASSWORD = "pgpass", POSTGRES_DB = "botdb" }
restart = "always"
healthcheck = { cmd = "pg_isready -U postgres", interval = 15, retries = 5 }
```

**Flask + PostgreSQL:**
```toml
[container.app]
image = "python:3.11-slim"
command = "sh -c '\
  pip install --dry-run -r /app/requirements.txt -q 2>/dev/null \
    || pip install -r /app/requirements.txt; \
  exec python /app/app.py'"
ports = ["5000:5000"]
volumes = ["./app:/app"]
env = {
  FLASK_ENV = "production",
  DB_HOST = "10.0.2.1",
  DB_USER = "postgres",
  DB_PASS = "secret",
  DB_NAME = "myapp"
}
restart = "always"
healthcheck = { cmd = "curl -f http://localhost:5000/health", interval = 30, retries = 3, timeout = 5 }

[container.db]
image = "postgres:16"
ports = ["5432:5432"]
volumes = ["pg_data:/var/lib/postgresql/data"]
env = { POSTGRES_PASSWORD = "secret", POSTGRES_DB = "myapp" }
restart = "always"
healthcheck = { cmd = "pg_isready -U postgres" }
```

**Node.js + Redis:**
```toml
[container.app]
image = "node:20"
command = "sh -c 'cd /app && npm install && exec node index.js'"
ports = ["3000:3000"]
volumes = ["./app:/app"]
env = { REDIS_URL = "redis://10.0.2.1:6379" }
restart = "always"
healthcheck = { cmd = "wget -qO- http://localhost:3000/health", interval = 30 }

[container.db]
image = "redis:7"
ports = ["6379:6379"]
volumes = ["redis_data:/data"]
command = "redis-server --appendonly yes"
healthcheck = { cmd = "redis-cli ping", interval = 15 }
```

---

## Architecture

```
dck run -d
  ├─ unshare --fork --pid --mount --net --uts --ipc dck init <id>
  │   └─ dck init → chroot overlay → setup /proc/lo/eth0 → exec CMD
  └─ dck console-serve <id>
      ├─ reads stdout pipe
      ├─ writes to log file
      ├─ listens on Unix socket
      └─ broadcasts to all attach clients

dck attach <id> → Unix socket → full log history → live stdin/stdout
```

**Storage:** `/root/.dck/`

```
images/        # OCI rootfs per tag
containers/    # State JSON files
overlay/       # upper/work/merged per container
logs/          # Container stdout/stderr
consoles/      # Unix sockets for attach
networks/      # IP allocation pool
```

---

## Changelog

### v1.4.7
- `dck attach` rewritten — Unix socket, full history + live stream, Ctrl+C safe
- `console-serve` — per-container daemon, writes logs + broadcasts to socket
- Console-serve writes logs, no data loss when `dck run -d` exits
- Network readiness — init waits 20s for eth0 before CMD
- Overlay stale mount detection — containers restart after reboot
- Command arguments preserved after LookPath — `pip install -r req.txt` works
- Multi-container, `dck start`/`dck restart`, `dck stop --kill-child`
- session.lock race fix, socket cleanup on stop

### v1.3.0
- `dck.toml` config, `dck up`/`dck down`

### v1.2.1
- KillMode=process, DNAT dedup, PID liveness check
- UFW auto-ports, /root/.dck for root

### v1.1.0
- First stable release

---

## Troubleshooting

```bash
# Permission denied — need root
sudo dck run --rm alpine echo hi

# Container dies after bootstrap
dck bootstrap --install   # reinstall systemd unit

# Network issues
ip link show dck0
iptables -t nat -L -n
ufw status verbose

# No route to host after reboot
systemctl status dck-bootstrap
dck ps
dck rm -f <id> && dck run -d --restart always -n web -p 80:80 nginx:alpine

# DNAT cleanup
iptables -t nat -F PREROUTING
iptables -t nat -F OUTPUT
```

---

## Updating dck

```bash
dck update
```

Downloads the latest binary from GitLab and replaces `/usr/local/bin/dck`.

---

## All Commands

| Command | Description |
|---------|-------------|
| `pull` | Pull image from Docker Hub |
| `run` | Create and start container |
| `ps` | List containers (with PID liveness) |
| `stop` | Stop a running container |
| `start` | Start a stopped container |
| `restart` | Restart a container |
| `rm` | Remove a container |
| `exec` | Run command inside container |
| `console` | Open interactive shell |
| `attach` | Attach to main process (history + live) |
| `logs` | Show or follow container logs |
| `images` | List local images |
| `rmi` | Remove local image |
| `up` | Start containers from `dck.toml` |
| `down` | Stop/remove containers from `dck.toml` |
| `bootstrap` | Start all `--restart always` containers |
| `inspect` | Show container details |
| `version` | Show version |
| `update` | Self-update |

---

## Comparison

| Feature | dck | Docker |
|---------|-----|--------|
| Daemon | No daemon | dockerd required |
| Binary size | ~5 MB | ~100+ MB |
| Namespaces | PID, Mount, Net, UTS, IPC | All |
| Bridge network | dck0 (10.0.2.0/24) | docker0 |
| Port mapping | iptables DNAT (PREROUTING + OUTPUT) | iptables DNAT |
| Auto-start | systemd oneshot (bootstrap) | systemd dockerd |
| Image format | OCI/Docker V2 | OCI/Docker V2 |

---

## Uninstall

```bash
dck bootstrap --remove
rm /usr/local/bin/dck
rm -rf ~/.dck
```

## License

MIT
#   d c k  
 