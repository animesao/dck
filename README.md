# dck — Simple Docker CLI client

A lightweight CLI wrapper to simplify daily Docker operations.

## Quick Install

```bash
curl -sSL https://gitlab.com/animesao/dck/-/raw/main/install.sh | bash
```

Or via pip:
```bash
pip install .
```

## Usage

### Short aliases
| Alias | Full command | Description |
|-------|-------------|-------------|
| `dck l <container>` | `dck logs <container>` | View container logs |
| `dck s <container>` | `dck start <container>` | Start a container |
| `dck st <container>` | `dck stop <container>` | Stop a container |
| `dck r <container>` | `dck restart <container>` | Restart a container |
| `dck i` | `dck images` | List Docker images |
| `dck e <container>` | `dck exec <container>` | Execute command in container |

### Container management
| Command | Description |
|---------|-------------|
| `dck ps [-a]` | List containers (colored status, ports, uptime) |
| `dck logs <container> [-f]` | View container logs (tail / follow) |
| `dck start <container> [--restart always]` | Start a container (optional restart policy) |
| `dck stop <container>` | Stop a container |
| `dck restart <container>` | Restart a container |
| `dck rm <container> [-f]` | Remove a container |
| `dck restart-policy <c> <policy>` | Set auto-start policy (always/unless-stopped/on-failure/no) |
| `dck console <container> [-m <mode>] [-t N]` | Pterodactyl-style console: shell, attach, logs, or ptero mode |
| `dck attach <container>` | Attach to container's main process (Ctrl+P Ctrl+Q to detach) |
| `dck resources <container> [--ram <size>] [--cpu <cores>] [--restart <policy>]` | Update RAM/CPU limits and restart policy |

### Startup config (v0.4.0)
| Command | Description |
|---------|-------------|
| `dck startup <container>` | Show startup config |
| `dck startup <container> -c "cmd"` | Set custom startup command |
| `dck startup <container> -e "entry"` | Set custom entrypoint |
| `dck startup <container> -f "/path"` | Set startup script path |
| `dck startup <container> -C` | Clear startup config |

You can also set startup settings interactively during `dck create`.

### Container Manifest (v0.4.0)
Define containers in `dck.yml`, `dck.yaml`, or `dck.json`:

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
```

| Command | Description |
|---------|-------------|
| `dck up` | Deploy containers from manifest |
| `dck down` | Stop and remove manifest containers |
| `dck manifest` | Show manifest containers status |

### Image management
| Command | Description |
|---------|-------------|
| `dck images` | List Docker images |
| `dck pull <image>` | Pull an image from registry |
| `dck rmi <image> [-f]` | Remove an image |
| `dck export-image <image> [path]` | Export image to tar archive |
| `dck import-image <path>` | Import image from tar archive |

### Docker Compose
| Command | Description |
|---------|-------------|
| `dck compose up [-d] [--build]` | Create and start containers |
| `dck compose down [-v]` | Stop and remove containers |
| `dck compose ps` | List compose services |
| `dck compose logs [-f]` | View compose logs |

### Eggs (Pterodactyl-style)
| Command | Description |
|---------|-------------|
| `dck eggs` | List all available eggs |
| `dck egg <name>` | Create a container from an egg |

**Built-in eggs by category:**

| Category | Eggs |
|----------|------|
| Python | `python-slim` (3.12, lightweight), `python-full` (with dev tools) |
| Node.js | `node` (22 LTS), `node-dev` (with nodemon) |
| Go | `golang` (1.22) |
| Rust | `rust` (with cargo) |
| Java | `java` (21, Maven) |
| Database | `postgres` (16), `mysql` (8), `redis` (7) |
| Web | `nginx-proxy` (reverse proxy) |

### Templates & Container Creation
| Command | Description |
|---------|-------------|
| `dck templates` | List available templates |
| `dck create [template]` | Interactive container creation from template |
| `dck run <image>` | Run any Docker image with interactive setup |

**Built-in templates:**
- **Nginx** — web server / reverse proxy (port 80, 128MB RAM)
- **Minecraft** — Java Edition server (port 25565, 2GB RAM)
- **Terraria** — dedicated server (port 7777, 1GB RAM)
- **Valheim** — dedicated server (ports 2456-2457/udp, 2GB RAM)
- **CS2** — Counter-Strike 2 server (port 27015, 4GB RAM)
- **Satisfactory** — dedicated server (port 7777, 4GB RAM)

Port input supports comma-separated values: `80:80,443:443` or just `80,443`.
Custom templates are saved to `~/.dck/templates.json` for reuse.

### Firewall & Ports
| Command | Description |
|---------|-------------|
| `dck ports` | List listening ports |
| `dck ports check <port>` | Check if port is available |
| `dck ports open <port> [--proto udp]` | Open port in firewall (UFW) |
| `dck ports close <port>` | Close port in firewall |

When creating a container with `dck create`, it will ask to auto-open required ports in the firewall.

### Console (Pterodactyl-style)
| Command | Description |
|---------|-------------|
| `dck console <container>` | Auto mode: shows info/logs, then choose shell/attach/ptero |
| `dck console <container> -m shell` | Directly enter interactive shell inside container |
| `dck console <container> -m attach` | Attach to container's main process (shows logs first) |
| `dck console <container> -m logs` | Stream live container logs |
| `dck console <container> -m ptero` | Pterodactyl mode: real-time log streaming + command input |
| `dck attach <container>` | Attach to main process with recent logs shown |

### Other
| Command | Description |
|---------|-------------|
| `dck stats` | Live CPU / memory / network monitoring |
| `dck exec <container> [cmd]` | Execute command (interactive shell if no command) |
| `dck inspect <container>` | Show detailed container info |
| `dck doctor` | Docker diagnostics + install instructions |
| `dck lang [ru/en]` | Switch language (Русский / English) |
| `dck update` | Update dck to latest version |
| `dck uninstall` | Remove dck completely from your system |
