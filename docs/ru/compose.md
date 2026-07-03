# Compose / Развёртывание

## `dck up [имя] [-f <файл>]`

Создать и запустить контейнеры из compose-файла.

Автоопределение (по приоритету):
1. `dck.toml`
2. `compose.yaml`
3. `compose.yml`
4. `docker-compose.yaml`
5. `docker-compose.yml`

```
dck up                    # автоопределение
dck up myapp              # запустить только "myapp"
dck up -f docker-compose.prod.yaml
dck up --no-net           # без настройки сети
dck up --no-start         # создать, но не запускать
dck up --build            # пересобрать образы перед запуском
dck up --pull             # скачать образы перед запуском
dck up -d                 # фоновый режим (только ID контейнеров)
dck up --autostart        # установить systemd-сервис для автостарта при загрузке
```

## `dck down [имя] [-f <файл>]`

Остановить и удалить контейнеры из compose-файла.

```
dck down                  # остановить + удалить
dck down myapp            # только "myapp"
dck down -f dck.toml
dck down -a               # удалить ВСЕ контейнеры
dck down --volumes        # также удалить тома
dck down --rmi            # также удалить образы
```

## compose.yaml справочник

```yaml
services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./www:/usr/share/nginx/html
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    environment:
      - NGINX_HOST=example.com
    restart: unless-stopped
    depends_on:
      - api
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost"]
      interval: 30s
      timeout: 10s
      retries: 3
    dns:
      - 8.8.8.8
    networks:
      - frontend

  api:
    image: myapi:latest
    ports:
      - "3000:3000"
    environment:
      DB_HOST: db
      DB_NAME: ${DB_NAME:-test}
    env_file:
      - .env.prod
    volumes:
      - api-data:/app/data
    restart: always
    depends_on:
      db:
        condition: service_healthy
    ulimits:
      nofile:
        soft: 1024
        hard: 2048
    cap_add:
      - NET_ADMIN
    cap_drop:
      - ALL
    command: ["node", "server.js"]
    working_dir: /app
    networks:
      - backend

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: myapp
      POSTGRES_PASSWORD_FILE: /run/secrets/db_pass
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432"
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - backend

volumes:
  api-data:
    driver: local
  pgdata:

networks:
  frontend:
  backend:
    internal: true
```

### Поддерживаемые поля compose

| Поле | Статус | Примечания |
|---|---|---|
| `services.<name>.image` | ✅ | |
| `services.<name>.build` | ✅ | Путь или inline-сборка |
| `services.<name>.ports` | ✅ | `HOST:CONTAINER`, `HOST:CONTAINER/PROTO` |
| `services.<name>.environment` | ✅ | Map или список |
| `services.<name>.env_file` | ✅ | |
| `services.<name>.volumes` | ✅ | Bind, named, tmpfs |
| `services.<name>.command` | ✅ | |
| `services.<name>.working_dir` | ✅ | |
| `services.<name>.user` | ✅ | |
| `services.<name>.restart` | ✅ | |
| `services.<name>.depends_on` | ✅ | Простой или с condition |
| `services.<name>.healthcheck` | ✅ | Полная поддержка |
| `services.<name>.dns` | ✅ | |
| `services.<name>.dns_search` | ✅ | |
| `services.<name>.cap_add` | ✅ | |
| `services.<name>.cap_drop` | ✅ | |
| `services.<name>.ulimits` | ✅ | |
| `services.<name>.sysctls` | ✅ | |
| `services.<name>.labels` | ✅ | |
| `services.<name>.networks` | ✅ | |
| `services.<name>.entrypoint` | ✅ | |
| `services.<name>.expose` | ✅ | |
| `services.<name>.stop_signal` | ✅ | |
| `volumes` | ✅ | Именованные тома |
| `networks` | ✅ | Bridge-сети |
| `services.<name>.deploy` | ✅ | replicas, resources, restart_policy, update_config, placement |
| `services.<name>.secrets` | ✅ | Инжекция секретов как файлов (source, target, uid, gid, mode) |
| `services.<name>.configs` | ✅ | Инжекция конфигов как файлов (source, target, uid, gid, mode) |

### Пример: full-stack приложение

**compose.yaml:**

```yaml
services:
  frontend:
    image: node:20
    working_dir: /app
    volumes:
      - ./frontend:/app
    ports:
      - "5173:5173"
    command: npm run dev
    environment:
      - VITE_API_URL=http://localhost:3000

  backend:
    build: ./backend
    ports:
      - "3000:3000"
    environment:
      DB_URL: postgres://user:pass@db:5432/myapp
      REDIS_URL: redis://redis:6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: myapp
    healthcheck:
      test: pg_isready -U user -d myapp
      interval: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    healthcheck:
      test: redis-cli ping
      interval: 5s

volumes:
  pgdata:
```

## Secrets (Секреты)

Определяются на верхнем уровне и используются в сервисах:

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    file: ./secrets/api_key.txt

services:
  app:
    image: myapp:latest
    secrets:
      - db_password
      - source: db_password
        target: /app/config/db_pass
        uid: "1000"
        gid: "1000"
        mode: 0600
```

Секреты монтируются как файлы:
- По умолчанию: `/run/secrets/<имя>`
- Права по умолчанию: `0444`

## Configs (Конфиги)

Работают как секреты, но монтируются в `/`:

```yaml
configs:
  nginx_conf:
    file: ./nginx.conf
  app_config:
    file: ./config/app.yml

services:
  web:
    image: nginx:alpine
    configs:
      - nginx_conf
      - source: app_config
        target: /app/config.yml
        mode: 0644
```

Конфиги монтируются как файлы:
- По умолчанию: `/<имя>`
- Права по умолчанию: `0444`

## Формат dck.toml

Для обратной совместимости с существующими проектами dck:

```toml
containers = ["web", "api"]

[web]
image = "nginx:alpine"
ports = ["80:80"]
volumes = ["./www:/usr/share/nginx/html"]
environment = ["NGINX_HOST=example.com"]
restart = "unless-stopped"
```
