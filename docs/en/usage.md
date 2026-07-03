# Usage & Commands

## Basic commands

### `dck pull <image>[:tag]`

Pull an image from a registry.

```
dck pull nginx
dck pull alpine:3.19
dck pull registry.example.com/myapp:v1.0
```

Private registries: set `DOCKER_USERNAME` / `DOCKER_PASSWORD` env vars,
or use `-u user -p pass` on push.

---

### `dck run [options] <image> [command]`

Create and start a container.

```
dck run nginx
dck run -d --name web -p 80:80 nginx
dck run -it --rm alpine sh
dck run -d --memory 512m --cpus 1.5 node:20 node app.js
dck run -d -v /data:/data -e DB_URL=postgres://... myapp
```

#### Run options

| Flag | Description |
|---|---|
| `-d` | Detach (run in background) |
| `-n <name>` | Container name |
| `-p H:C[/proto]` | Port mapping `host:container/tcp\|udp` |
| `-v S:D` | Volume mount `source:dest` |
| `-e K=V` | Environment variable |
| `--env-file <f>` | Read env vars from file |
| `-i` | Interactive |
| `-t` | Allocate TTY |
| `--rm` | Remove container on exit |
| `--restart <policy>` | Restart: `no`, `always`, `on-failure`, `unless-stopped` |
| `--memory <lim>` | Memory limit: `512m`, `1g`, `2g` |
| `--cpus <num>` | CPU limit: `1.5` |
| `--workdir <dir>` | Working directory inside container |
| `-h <name>` | Container hostname |
| `--entrypoint <cmd>` | Override entrypoint |
| `--cap-add <cap>` | Add capability: `NET_ADMIN`, `SYS_PTRACE` |
| `--cap-drop <cap>` | Drop capability: `ALL` |
| `--user <uid>` | Run as UID or `UID:GID` |
| `--readonly` | Read-only rootfs |
| `--no-new-privs` | Disable privilege escalation |
| `--sysctl <k=v>` | Sysctl parameter |
| `--ulimit <opt>` | Ulimit: `nofile=1024:2048` |
| `-l, --label <k=v>` | Container label |
| `--dns <ip>` | DNS server |
| `--network <mode>` | Network: `bridge`, `none`, `host` |
| `--startup <s>` | Startup script (inline or `@file`) |
| `--healthcheck-cmd <cmd>` | Health check command |
| `--healthcheck-interval <s>` | Health check interval |
| `--healthcheck-retries <n>` | Health check retries |
| `--healthcheck-timeout <s>` | Health check timeout |

#### Volume syntax

```
# Bind mount
-v /host/path:/container/path
-v /host/path:/container/path:ro
-v /host/path:/container/path:shared

# Named volume
-v myvolume:/container/path

# tmpfs
-v tmpfs:/container/path:size=1G,mode=0777

# NFS
-v nfs://server:/export:/container/path:nfsopts=hard,intr
```

#### Examples

```
# Web server
dck run -d --name nginx -p 80:80 -v /www:/usr/share/nginx/html:ro nginx:alpine

# Database
dck run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=secret postgres:16

# Dev environment
dck run -it --rm -v .:/work -w /work node:20 bash

# Batch job
dck run --rm -v /data:/data alpine:3.19 sh -c "du -sh /data/*"
```

---

### `dck ps`

List containers.

```
dck ps           # running only
dck ps -a        # all containers
```

---

### `dck stop <container>`

Stop a running container.

```
dck stop web
dck stop web db
```

---

### `dck start <container>`

Start a stopped container.

---

### `dck restart <container>`

Restart a container.

---

### `dck rm [-f] <container>`

Remove a container. `-f` forces removal of running containers.

---

### `dck exec <container> <command>`

Execute a command inside a running container.

```
dck exec web nginx -s reload
dck exec -it db psql -U postgres
```

---

### `dck logs [-f] <container>`

Show container logs. `-f` follows the log stream.

---

### `dck top <container>`

Show running processes inside a container.

---

### `dck stats [container]`

Show live CPU, memory, IO, and PID usage.

---

### `dck attach <container>`

Attach to the container's main process.

---

### `dck console <container>`

Get an interactive shell in the container.

---

### `dck cp <src> <dst>`

Copy files between host and container.

```
dck cp myapp.conf web:/etc/nginx/conf.d/
dck cp web:/var/log/nginx/access.log ./logs/
```

---

### `dck rename <container> <new-name>`

Rename a container.

---

### `dck port <container>`

Show port mappings for a container.

---

### `dck images`

List locally stored images.

---

### `dck rmi <image>[:tag]`

Remove an image.

---

### `dck commit <container> <image>[:tag]`

Create an image from a container's current state.

---

### `dck build -t <name>:<tag> [options] .`

Build an image from a Dockerfile.

```
dck build -t myapp:v1 .
dck build -t myapp:v1 --build-arg VERSION=1.0 -f Dockerfile.prod .
```

#### Supported Dockerfile instructions

FROM, RUN, COPY, ADD, WORKDIR, ENV, CMD, ENTRYPOINT, EXPOSE, LABEL, USER,
VOLUME, SHELL, ARG, HEALTHCHECK, STOPSIGNAL, ONBUILD.

---

### `dck push <image>[:tag]`

Push an image to a registry.

```
dck push myapp:v1
dck push registry.example.com/myapp:v1
```

Auth: `-u user -p pass` or `DOCKER_USERNAME` / `DOCKER_PASSWORD`.

---

### `dck info`

Show system information: kernel, storage driver, data directory, CPU, memory.

---

### `dck serve [-p <port>]`

Start a Docker-compatible REST API server (default port: 2375).

```
dck serve -p 2375
```

Compatible with Docker clients, Portainer, VS Code Dev Containers, and CI tools.

---

### `dck system prune`

Remove unused containers and images.
