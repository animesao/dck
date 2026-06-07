# dck — Simple Docker CLI client

A lightweight CLI wrapper to simplify daily Docker operations. Features Pterodactyl-style egg system, game server support, container manifests, firewall management, and language switching (RU/EN).

## Quick Install

```bash
curl -sSL https://gitlab.com/animesao/dck/-/raw/main/install.sh | bash
```

Or via pip:
```bash
pip install .
```

## Short Aliases

| Alias | Full command | Description |
|-------|-------------|-------------|
| `dck l <container>` | `dck logs <container>` | View container logs |
| `dck s <container>` | `dck start <container>` | Start a container |
| `dck st <container>` | `dck stop <container>` | Stop a container |
| `dck r <container>` | `dck restart <container>` | Restart a container |
| `dck i` | `dck images` | List Docker images |
| `dck e <container>` | `dck exec <container>` | Execute command in container |

## Container Management

| Command | Description |
|---------|-------------|
| `dck ps [-a]` | List containers (colored status, ports, uptime) |
| `dck logs <container> [-f]` | View container logs (tail / follow) |
| `dck start <container> [--restart always]` | Start a container (optional restart policy) |
| `dck stop <container>` | Stop a container |
| `dck restart <container>` | Restart a container |
| `dck rm <container> [-f]` | Remove a container |
| `dck restart-policy <c> <policy>` | Set auto-start policy (always/unless-stopped/on-failure/no) |
| `dck console <container> [-m <mode>] [-t N] [-s]` | Pterodactyl-style console |
| `dck attach <container>` | Attach to container's main process (Ctrl+P Ctrl+Q to detach) |
| `dck resources <container> [--ram <size>] [--cpu <cores>] [--restart <policy>]` | Update RAM/CPU limits and restart policy |

## Pterodactyl Console (v0.5.0)

| Command | Mode | Description |
|---------|------|-------------|
| `dck console <container>` | auto | Shows info/logs, then choose action |
| `dck console <container> -m shell` | shell | Interactive shell via `docker exec -it` |
| `dck console <container> -m attach` | attach | Attach to main process (shows recent logs) |
| `dck console <container> -m logs` | logs | Stream live container logs |
| `dck console <container> -m ptero` | ptero | Real-time log streaming + commands via `docker exec` |
| `dck console <container> -m ptero -s` | ptero+stdin | Commands piped to PID 1 stdin (for game servers) |
| `dck attach <container>` | — | Attach to main process with recent logs shown |

### How Ptero Console Works

**`dck console -m ptero`** (default mode) — commands are executed inside the container via `docker exec`. Works for: web servers (nginx, apache), databases (postgres, mysql), applications (python, node), scripts (`ls`, `ps`, `cat`, `npm install`, `python manage.py`).

**`dck console -m ptero -s`** (stdin mode, Pterodactyl-like) — dck opens a **Docker attach socket** directly to the container's main process (PID 1). This is the same mechanism Pterodactyl uses: commands are written to the server's stdin, and all output (logs + command responses) appears in a **single stream** — no RCON noise, no separate command output.

For **Minecraft** (`itzg/minecraft-server`): commands like `tps`, `pl`, `list`, `say Hello`, `give`, `stop` go directly to the server console via the attach socket. The server's response appears in the same log stream — exactly like Pterodactyl panel.

If the attach socket is unavailable, dck falls back to `docker exec` mode (with a hint to use `--stdin` for game servers).

## Eggs — Pterodactyl-Style (v0.4.0)

Pre-configured container blueprints with optimal settings for popular runtimes and servers.

| Command | Description |
|---------|-------------|
| `dck eggs` | List all available eggs |
| `dck egg <name>` | Interactive container creation from egg (sets name, ports, volumes) |

### Available Eggs

| Category | Egg | Image | Details |
|----------|-----|-------|---------|
| **Python** | `python-slim` | python:3.12-slim | Lightweight, 128MB RAM, port 8000 |
| **Python** | `python-full` | python:3.12 | Full dev tools, git, 256MB RAM, port 8000 |
| **Node.js** | `node` | node:22-alpine | LTS, 128MB RAM, port 3000 |
| **Node.js** | `node-dev` | node:22 | Nodemon, git, 256MB RAM, port 3000 |
| **Go** | `golang` | golang:1.22-alpine | 256MB RAM, port 8080 |
| **Rust** | `rust` | rust:alpine | Cargo, 256MB RAM, port 8080 |
| **Java** | `java` | maven:3-eclipse-temurin-21 | Maven, 512MB RAM, port 8080 |
| **Database** | `postgres` | postgres:16-alpine | 256MB RAM, port 5432 |
| **Database** | `mysql` | mysql:8 | 512MB RAM, port 3306 |
| **Database** | `redis` | redis:7-alpine | 128MB RAM, port 6379 |
| **Web** | `nginx-proxy` | nginx:alpine | Reverse proxy, 128MB RAM, port 80 |

## Templates & Container Creation

Pre-defined server templates for game servers and web services.

| Command | Description |
|---------|-------------|
| `dck templates` | List available templates (built-in + custom) |
| `dck create [template]` | Interactive container creation from template |
| `dck run <image>` | Run any Docker image with interactive setup |

### Built-in Templates

| Template | Purpose | Ports | RAM |
|----------|---------|-------|-----|
| **Nginx** | Web server / reverse proxy | 80 | 128MB |
| **Minecraft** | Java Edition game server | 25565 | 2GB |
| **Terraria** | Dedicated game server | 7777 | 1GB |
| **Valheim** | Dedicated game server | 2456-2457/udp | 2GB |
| **CS2** | Counter-Strike 2 server | 27015 | 4GB |
| **Satisfactory** | Dedicated server | 7777 | 4GB |

Port input supports comma-separated values: `80:80,443:443` or just `80,443`. Custom templates are saved to `~/.dck/templates.json` for reuse.

## Container Manifest (v0.4.0)

Define and deploy multiple containers declaratively in `dck.yml`, `dck.yaml`, or `dck.json`:

```yaml
containers:
  - name: web
    image: nginx:alpine
    ports:
      - "80:80/tcp"
    env:
      NGINX_HOST: example.com
    volumes:
      - "./html:/usr/share/nginx/html"
    ram: 128m
    cpu: 0.5
    restart: always
  - name: db
    image: postgres:16-alpine
    env:
      POSTGRES_PASSWORD: secret
    ram: 256m
    restart: unless-stopped
```

| Command | Description |
|---------|-------------|
| `dck up` | Deploy containers from manifest (create/pull/start) |
| `dck down` | Stop and remove manifest containers |
| `dck manifest` | Show manifest containers status |

## Startup Config (v0.4.0)

Per-container startup configuration stored in `~/.dck/startup.json`. Set custom entrypoints, startup commands, or script paths that override Docker defaults.

| Command | Description |
|---------|-------------|
| `dck startup <container>` | Show current startup config |
| `dck startup <container> -c "cmd"` | Set custom startup command (`CMD`) |
| `dck startup <container> -e "entry"` | Set custom entrypoint (`ENTRYPOINT`) |
| `dck startup <container> -f "/path"` | Run a startup script path |
| `dck startup <container> -C` | Clear startup config |

You can also set startup settings interactively during `dck create`.

## Image Management

| Command | Description |
|---------|-------------|
| `dck images` | List Docker images |
| `dck pull <image>` | Pull an image from registry |
| `dck rmi <image> [-f]` | Remove an image |
| `dck export-image <image> [path]` | Export image to tar archive |
| `dck import-image <path>` | Import image from tar archive |

## Docker Compose

| Command | Description |
|---------|-------------|
| `dck compose up [-d] [--build]` | Create and start containers |
| `dck compose down [-v]` | Stop and remove containers |
| `dck compose ps` | List compose services |
| `dck compose logs [-f]` | View compose logs |

## Firewall & Ports

| Command | Description |
|---------|-------------|
| `dck ports` | List listening ports |
| `dck ports check <port>` | Check if port is available |
| `dck ports open <port> [--proto udp]` | Open port in firewall (UFW) |
| `dck ports close <port>` | Close port in firewall |

When creating a container with `dck create`, dck will ask to auto-open required ports in the firewall.

## Other Commands

| Command | Description |
|---------|-------------|
| `dck stats` | Live CPU / memory / network monitoring |
| `dck exec <container> [cmd]` | Execute command (interactive shell if no command) |
| `dck inspect <container>` | Show detailed container info |
| `dck doctor` | Docker diagnostics + install instructions |
| `dck lang [ru/en]` | Switch language (Русский / English) |
| `dck update` | Update dck to latest version |
| `dck uninstall` | Remove dck completely from your system |

## Language

dck supports switching between English and Russian:

```bash
dck lang ru    # переключиться на русский
dck lang en    # switch to English
dck lang       # show current language
```

## Configuration

All local configuration is stored in `~/.dck/`:
- `~/.dck/lang` — language setting
- `~/.dck/startup.json` — per-container startup configs
- `~/.dck/templates.json` — custom templates

## License

MIT
