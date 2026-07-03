# Примеры Compose — 15 реальных конфигураций

Каждый пример — готовый `compose.yaml`. Бери и используй.

---

## 1. Minecraft Server (Paper)

```yaml
services:
  mc:
    image: eclipse-temurin:21-jdk
    working_dir: /server
    volumes:
      - /opt/mc-server:/server
    command: sh -c "echo eula=true > eula.txt && exec java -Xms512M -Xmx4G -jar paper-*.jar nogui"
    restart: always
    ports:
      - "25565:25565"
    dns:
      - 8.8.8.8
```

- `working_dir` — рабочая директория внутри контейнера
- `volumes` — монтирование папки хоста в контейнер
- `restart: always` — перезапуск при падении и после перезагрузки
- `dns` — фиксит DNS для скачивания плагинов/модов

---

## 2. Веб-сервер (Nginx)

```yaml
services:
  web:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/www/html:/usr/share/nginx/html:ro
      - /etc/nginx/conf.d:/etc/nginx/conf.d:ro
    labels:
      - "app=website"
      - "env=production"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost"]
      interval: 30s
      timeout: 10s
      retries: 3
```

- `:ro` — монтирование только для чтения (безопасность)
- `labels` — метки для фильтрации `dck ps --filter`
- `healthcheck` — проверка каждые 30 секунд

---

## 3. Full-Stack (Node.js + Python + Postgres)

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: always
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    environment:
      POSTGRES_DB: myapp
      POSTGRES_PASSWORD: ${DB_PASSWORD:-secret}
    healthcheck:
      test: pg_isready -U postgres
      interval: 5s
      retries: 10

  api:
    build: ./api
    restart: always
    working_dir: /app
    volumes:
      - ./api:/app
      - /app/node_modules
    ports:
      - "3000:3000"
    environment:
      DB_HOST: db
    depends_on:
      db:
        condition: service_healthy
    ulimits:
      nofile:
        soft: 65536
        hard: 65536

  bot:
    image: python:3.12-slim
    restart: always
    working_dir: /app
    volumes:
      - ./bots:/app
    command: sh -c "pip install -r requirements.txt && exec python main.py"
    environment:
      DB_HOST: db
    secrets:
      - bot_token
    depends_on:
      db:
        condition: service_healthy

volumes:
  pgdata:

secrets:
  bot_token:
    file: ./secrets/bot_token.txt
```

- `volumes: /app/node_modules` — безымянный том, защищает node_modules от перезаписи
- `depends_on: condition: service_healthy` — ждать готовности БД
- `secrets` — секретные файлы в `/run/secrets/<name>`
- `ulimits` — лимиты на количество открытых файлов

---

## 4. Базы данных (MySQL + Redis + Adminer)

```yaml
services:
  mysql:
    image: mysql:8
    restart: always
    volumes:
      - mysql_data:/var/lib/mysql
      - ./my.cnf:/etc/mysql/conf.d/custom.cnf:ro
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASS}
      MYSQL_DATABASE: myapp
      MYSQL_USER: app
      MYSQL_PASSWORD: ${MYSQL_APP_PASS}
    command: >
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --max_connections=200
    cap_add:
      - SYS_NICE
    healthcheck:
      test: mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASS}

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --requirepass ${REDIS_PASS}

  adminer:
    image: adminer:latest
    restart: always
    ports:
      - "8080:8080"
    environment:
      ADMINER_DEFAULT_SERVER: mysql

volumes:
  mysql_data:
  redis_data:
```

- `command: >` — многострочная команда
- `cap_add: SYS_NICE` — нужно MySQL для приоритета потоков
- Adminer — веб-интерфейс на порту 8080

---

## 5. Обратный прокси (Nginx + 2 сервиса)

```yaml
services:
  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - app1
      - app2

  app1:
    image: node:20-alpine
    working_dir: /app
    volumes:
      - ./app1:/app
    command: node server.js
    expose:
      - "3000"
    restart: always

  app2:
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - ./app2:/app
    command: python app.py
    expose:
      - "5000"
    restart: always
```

- `expose` — порт доступен только соседним сервисам
- Nginx резолвит `app1:3000`, `app2:5000`

---

## 6. Cron / Плановые задачи

```yaml
services:
  cron:
    image: alpine:3.19
    restart: always
    volumes:
      - ./scripts:/scripts
    command: >
      sh -c "
        echo '* * * * * cd /scripts && sh task.sh' > /var/spool/cron/crontabs/root &&
        crond -f -l 2
      "
    environment:
      - TZ=Europe/Moscow
    stop_grace_period: 5s
```

- `stop_grace_period` — время на завершение перед SIGKILL (по умолч. 10с)
- `TZ` — часовой пояс

---

## 7. Файловый сервер (nginx + tmpfs)

```yaml
services:
  storage:
    image: nginx:alpine
    restart: always
    ports:
      - "9000:80"
    volumes:
      - /mnt/storage:/usr/share/nginx/html:ro
      - /mnt/uploads:/uploads:rw
    user: "1000:1000"
    read_only: true
    tmpfs:
      - /var/cache/nginx
      - /var/run
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    security_opt:
      - no-new-privileges:true
```

- `user: "1000:1000"` — запуск от непривилегированного пользователя
- `read_only: true` — корневая ФС только для чтения
- `tmpfs` — временная ФС в памяти
- `cap_drop: ALL` + `cap_add: NET_BIND_SERVICE` — минимум привилегий

---

## 8. CI Runner (GitHub Actions)

```yaml
services:
  runner:
    image: summerwind/actions-runner:latest
    restart: always
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - runner_data:/home/runner
    environment:
      - RUNNER_NAME=my-runner
      - RUNNER_REPO=https://github.com/user/repo
      - RUNNER_TOKEN=${GITHUB_TOKEN}
    privileged: true
    dns:
      - 8.8.8.8

volumes:
  runner_data:
```

- `privileged: true` — для Docker-in-Docker

---

## 9. Production-стек (nginx + API + DB + Redis)

```yaml
services:
  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "443:443"
    volumes:
      - ./site/public:/var/www/html:ro
    configs:
      - source: nginx_conf
        target: /etc/nginx/conf.d/default.conf
    secrets:
      - ssl_cert
      - ssl_key

  api:
    build: ./api
    restart: always
    ports:
      - "3000:3000"
    environment:
      DB_HOST: db
      NODE_ENV: production
    secrets:
      - db_password
    deploy:
      replicas: 2
      resources:
        limits:
          memory: "512m"
          cpus: "1.0"
        reservations:
          memory: "256m"

  db:
    image: postgres:16-alpine
    restart: always
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    healthcheck:
      test: pg_isready -U postgres
      interval: 5s

  redis:
    image: redis:7-alpine
    restart: always
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

volumes:
  pgdata:
  redis_data:

configs:
  nginx_conf:
    file: ./nginx/default.conf

secrets:
  ssl_cert:
    file: /etc/ssl/certs/domain.crt
  ssl_key:
    file: /etc/ssl/private/domain.key
    mode: 0600
  db_password:
    file: ./secrets/db_pass.txt
```

- `configs` — конфиги (путь по умолчанию: `/<name>`)
- `secrets` — секреты (путь по умолчанию: `/run/secrets/<name>`)
- `deploy.resources.limits` — жёсткий лимит
- `deploy.resources.reservations` — гарантированные ресурсы
- `replicas: 2` — для режима кластера

---

## 10. Среда разработки (hot-reload)

```yaml
services:
  frontend:
    image: node:20
    working_dir: /app
    volumes:
      - ./frontend:/app
      - /app/node_modules
    ports:
      - "5173:5173"
    command: npm run dev
    stdin_open: true
    tty: true

  backend:
    build: ./backend
    working_dir: /app
    volumes:
      - ./backend:/app
      - /app/node_modules
    ports:
      - "3000:3000"
    command: npx nodemon server.js
    environment:
      DB_HOST: db

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: devpass
    ports:
      - "5432:5432"

volumes:
  pgdata:
```

- `stdin_open: true` + `tty: true` — интерактивный режим (`-it`)
- `npx nodemon` — авто-перезапуск при изменении файлов

---

## 11. Разовая задача (backup)

```yaml
services:
  backup:
    image: alpine:3.19
    volumes:
      - /mnt/data:/data:ro
      - /mnt/backups:/backups
    command: >
      sh -c "tar czf /backups/data-$(date +%Y%m%d).tar.gz /data"
    restart: "no"
```

- `restart: "no"` — запустить один раз и остановиться

---

## 12. Зеркало Docker Hub

```yaml
services:
  registry:
    image: registry:2
    restart: always
    ports:
      - "5000:5000"
    volumes:
      - registry_data:/var/lib/registry
    environment:
      - REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io
      - REGISTRY_STORAGE_DELETE_ENABLED=true

volumes:
  registry_data:
```

---

## 13. Prometheus + Grafana (мониторинг)

```yaml
services:
  prometheus:
    image: prom/prometheus
    restart: always
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prom_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=30d

  grafana:
    image: grafana/grafana
    restart: always
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

volumes:
  prom_data:
  grafana_data:
```

---

## Шпаргалка по всем полям compose

| Поле | Описание | Пример |
|---|---|---|
| `image` | Образ контейнера | `nginx:alpine` |
| `build` | Dockerfile для сборки | `./api` |
| `command` | Переопределить CMD | `node app.js` |
| `entrypoint` | Переопределить ENTRYPOINT | `["/bin/sh", "-c"]` |
| `ports` | Проброс портов | `"80:80"` |
| `expose` | Порт только для связанных сервисов | `"3000"` |
| `volumes` | Монтирование файлов/папок | `./src:/app:ro` |
| `environment` | Переменные окружения | `KEY=val` |
| `env_file` | Загрузить из файла | `.env.prod` |
| `restart` | Политика перезапуска | `no`, `always`, `on-failure`, `unless-stopped` |
| `dns` | DNS-серверы | `8.8.8.8` |
| `cap_add` | Добавить capability | `NET_ADMIN` |
| `cap_drop` | Убрать capability | `ALL` |
| `user` | Запуск от пользователя | `1000:1000` |
| `working_dir` | Рабочая директория | `/app` |
| `hostname` | Hostname контейнера | `myserver` |
| `labels` | Метки | `app=myapp` |
| `healthcheck` | Проверка здоровья | `test: curl -f http://localhost` |
| `depends_on` | Порядок запуска | `db: condition: service_healthy` |
| `networks` | Подключение к сетям | `frontend` |
| `network_mode` | Режим сети | `bridge`, `host`, `none` |
| `sysctls` | Параметры ядра | `net.core.somaxconn=1024` |
| `ulimits` | Лимиты ресурсов | `nofile: 1024:2048` |
| `secrets` | Секретные файлы | `- db_password` |
| `configs` | Конфигурационные файлы | `- nginx_conf` |
| `deploy` | Настройки развёртывания | `replicas: 3` |
| `stdin_open` | Держать stdin открытым | `true` |
| `tty` | Выделить TTY | `true` |
| `read_only` | Read-only корневая ФС | `true` |
| `tmpfs` | ФС в памяти | `/tmp:size=100M` |
| `privileged` | Полные привилегии | `true` (осторожно) |
| `stop_signal` | Сигнал остановки | `SIGTERM` |
| `stop_grace_period` | Время на завершение | `10s` |
| `extra_hosts` | Доп. записи в /etc/hosts | `"host.docker.internal:host-gateway"` |
