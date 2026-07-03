# Команды и использование

## Базовые команды

### `dck pull <образ>[:тег]`

Скачать образ из registry.

```
dck pull nginx
dck pull alpine:3.19
dck pull registry.example.com/myapp:v1.0
```

Приватные registry: `DOCKER_USERNAME` / `DOCKER_PASSWORD`, или `-u user -p pass`.

---

### `dck run [опции] <образ> [команда]`

Создать и запустить контейнер.

```
dck run nginx
dck run -d --name web -p 80:80 nginx
dck run -it --rm alpine sh
dck run -d --memory 512m --cpus 1.5 node:20 node app.js
dck run -d -v /data:/data -e DB_URL=postgres://... myapp
```

#### Флаги запуска

| Флаг | Описание |
|---|---|
| `-d` | Фоновый режим |
| `-n <имя>` | Имя контейнера |
| `-p H:C[/proto]` | Проброс порта `хост:контейнер/tcp\|udp` |
| `-v S:D` | Монтирование тома `источник:назначение` |
| `-e K=V` | Переменная окружения |
| `--env-file <файл>` | Файл с переменными окружения |
| `-i` | Интерактивный режим |
| `-t` | Выделить TTY |
| `--rm` | Удалить контейнер при выходе |
| `--restart <политика>` | `no`, `always`, `on-failure`, `unless-stopped` |
| `--memory <лимит>` | Лимит памяти: `512m`, `1g`, `2g` |
| `--cpus <число>` | Лимит CPU: `1.5` |
| `--workdir <дир>` | Рабочая директория внутри контейнера |
| `-h <имя>` | Hostname контейнера |
| `--entrypoint <cmd>` | Переопределить entrypoint |
| `--cap-add <cap>` | Добавить capability: `NET_ADMIN` |
| `--cap-drop <cap>` | Убрать capability: `ALL` |
| `--user <uid>` | Запуск от UID или `UID:GID` |
| `--readonly` | Read-only корневая ФС |
| `--no-new-privs` | Запретить повышение привилегий |
| `--sysctl <k=v>` | Sysctl параметр |
| `--ulimit <опция>` | Ulimit: `nofile=1024:2048` |
| `-l, --label <k=v>` | Метка контейнера |
| `--dns <ip>` | DNS сервер |
| `--network <режим>` | Сеть: `bridge`, `none`, `host` |
| `--startup <s>` | Стартовый скрипт (строка или `@файл`) |
| `--healthcheck-cmd <cmd>` | Команда проверки здоровья |
| `--healthcheck-interval <s>` | Интервал проверки |
| `--healthcheck-retries <n>` | Количество попыток |
| `--healthcheck-timeout <s>` | Таймаут проверки |

#### Синтаксис томов

```
# Bind mount
-v /путь/на/хосте:/путь/в/контейнере
-v /путь/на/хосте:/путь/в/контейнере:ro
-v /путь/на/хосте:/путь/в/контейнере:shared

# Именованный том
-v myvolume:/путь/в/контейнере

# tmpfs
-v tmpfs:/путь/в/контейнере:size=1G,mode=0777

# NFS
-v nfs://сервер:/экспорт:/путь/в/контейнере:nfsopts=hard,intr
```

#### Примеры

```
# Веб-сервер
dck run -d --name nginx -p 80:80 -v /www:/usr/share/nginx/html:ro nginx:alpine

# База данных
dck run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=secret postgres:16

# Среда разработки
dck run -it --rm -v .:/work -w /work node:20 bash

# Пакетная задача
dck run --rm -v /data:/data alpine:3.19 sh -c "du -sh /data/*"
```

---

### `dck ps`

Список контейнеров.

```
dck ps           # только запущенные
dck ps -a        # все контейнеры
```

---

### `dck stop <контейнер>`

Остановить контейнер.

```
dck stop web
dck stop web db
```

---

### `dck start <контейнер>`

Запустить остановленный контейнер.

---

### `dck restart <контейнер>`

Перезапустить контейнер.

---

### `dck rm [-f] <контейнер>`

Удалить контейнер. `-f` принудительно удаляет работающий контейнер.

---

### `dck exec <контейнер> <команда>`

Выполнить команду внутри работающего контейнера.

```
dck exec web nginx -s reload
dck exec -it db psql -U postgres
```

---

### `dck logs [-f] <контейнер>`

Показать логи контейнера. `-f` следит за новыми записями.

---

### `dck top <контейнер>`

Показать процессы внутри контейнера.

---

### `dck stats [контейнер]`

Использование CPU, памяти, IO и PIDs.

---

### `dck attach <контейнер>`

Подключиться к главному процессу контейнера.

---

### `dck console <контейнер>`

Интерактивная shell-сессия внутри контейнера.

---

### `dck cp <источник> <назначение>`

Копировать файлы между хостом и контейнером.

```
dck cp myapp.conf web:/etc/nginx/conf.d/
dck cp web:/var/log/nginx/access.log ./logs/
```

---

### `dck rename <контейнер> <новое-имя>`

Переименовать контейнер.

---

### `dck port <контейнер>`

Показать проброс портов контейнера.

---

### `dck images`

Список локально сохранённых образов.

---

### `dck rmi <образ>[:тег]`

Удалить образ.

---

### `dck commit <контейнер> <образ>[:тег]`

Создать образ из текущего состояния контейнера.

---

### `dck build -t <имя>:<тег> [опции] .`

Собрать образ из Dockerfile.

```
dck build -t myapp:v1 .
dck build -t myapp:v1 --build-arg VERSION=1.0 -f Dockerfile.prod .
```

#### Поддерживаемые инструкции Dockerfile

FROM, RUN, COPY, ADD, WORKDIR, ENV, CMD, ENTRYPOINT, EXPOSE, LABEL, USER,
VOLUME, SHELL, ARG, HEALTHCHECK, STOPSIGNAL, ONBUILD.

---

### `dck push <образ>[:тег]`

Отправить образ в registry.

```
dck push myapp:v1
dck push registry.example.com/myapp:v1
```

Авторизация: `-u user -p pass` или `DOCKER_USERNAME` / `DOCKER_PASSWORD`.

---

### `dck info`

Информация о системе: ядро, storage driver, директория данных, CPU, память.

---

### `dck serve [-p <порт>]`

Запустить Docker-совместимый REST API сервер (порт по умолчанию: 2375).

```
dck serve -p 2375
```

Совместим с Docker-клиентами, Portainer, VS Code Dev Containers и CI.

---

### `dck system prune`

Удалить неиспользуемые контейнеры и образы.
