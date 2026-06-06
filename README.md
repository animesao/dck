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

### Container management
| Command | Description |
|---------|-------------|
| `dck ps [-a]` | List containers (colored status, ports, uptime, restart policy) |
| `dck logs <container> [-f]` | View container logs (tail / follow) |
| `dck start <container> [--restart always]` | Start a container (optional restart policy) |
| `dck stop <container>` | Stop a container |
| `dck restart <container>` | Restart a container |
| `dck rm <container> [-f]` | Remove a container |
| `dck restart-policy <c> <policy>` | Set auto-start policy (always/unless-stopped/on-failure/no) |

### Image management
| Command | Description |
|---------|-------------|
| `dck images` | List Docker images |
| `dck pull <image>` | Pull an image from registry |
| `dck rmi <image> [-f]` | Remove an image |

### Docker Compose
| Command | Description |
|---------|-------------|
| `dck compose up [-d] [--build]` | Create and start containers |
| `dck compose down [-v]` | Stop and remove containers |
| `dck compose ps` | List compose services |
| `dck compose logs [-f]` | View compose logs |

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

### Other
| Command | Description |
|---------|-------------|
| `dck stats` | Live CPU / memory / network monitoring |
| `dck doctor` | Docker diagnostics + install instructions |
| `dck lang` | Switch language (`dck lang ru` / `dck lang en`) |
| `dck uninstall` | Remove dck completely from your system |
