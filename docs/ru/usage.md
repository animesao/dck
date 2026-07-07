# Команды и использование

dck — лёгкий container runtime. Нет демона, нет Docker. Просто контейнеры.
~5 MB статический бинарник, OCI образы, bridge-сеть, кластеризация, FaaS.

---

## Содержание

- [Развёртывание сайтов](websites.md)
- [Управление образами](#управление-образами)
- [Жизненный цикл контейнера](#жизненный-цикл-контейнера)
- [Запуск контейнеров (`dck run`)](#dck-run)
- [Работа с контейнерами](#работа-с-контейнерами)
- [Exec & Attach](#exec--attach)
- [Логи и мониторинг](#логи-и-мониторинг)
- [Сеть](#сеть)
- [Хранилище и тома](#хранилище-и-тома)
- [Лимиты ресурсов](#лимиты-ресурсов)
- [Безопасность](#безопасность)
- [Переменные окружения](#переменные-окружения)
- [Проверки здоровья (Healthchecks)](#проверки-здоровья-healthchecks)
- [Стартовые скрипты](#стартовые-скрипты)
- [Проброс портов](#проброс-портов)
- [dck.toml / Compose](#dcktoml--compose)
- [dck up / dck down](#dck-up--dck-down)
- [Кластеризация](#кластеризация)
- [Управление сервисами](#управление-сервисами)
- [FaaS / Serverless](#faas--serverless)
- [Блюпринты](#блюпринты)
- [Сборка и экспорт образов](#сборка-и-экспорт-образов)
- [Регистры](#регистры)
- [Системные команды](#системные-команды)
- [События](#события)
- [Архитектура](#архитектура)
- [Решение проблем](#решение-проблем)

---

## Управление образами

### `dck pull <образ>[:тег]`

Скачать образ из registry (по умолчанию Docker Hub).

```bash
dck pull nginx
dck pull alpine:3.19
dck pull registry.example.com/myapp:v1.0
```

Приватные registry: `DOCKER_USERNAME` / `DOCKER_PASSWORD`, или `-u user -p pass` на push.

### `dck images`

Список локально сохранённых образов.

```bash
dck images
```

### `dck rmi <образ>[:тег]`

Удалить образ.

```bash
dck rmi nginx:alpine
```

### `dck export <образ> -o <файл.tar.gz>`

Экспортировать образ в tar.gz (для бэкапа или переноса).

```bash
dck export myapp:v1 -o myapp-v1.tar.gz
```

### `dck import <файл.tar.gz>`

Импортировать образ из tar.gz.

```bash
dck import myapp-v1.tar.gz
```

### `dck build -t <имя>:<тег> [опции] .`

Собрать образ из Dockerfile.

```bash
dck build -t myapp:v1 .
dck build -t myapp:v1 --build-arg VERSION=1.0 -f Dockerfile.prod .
```

**Поддерживаемые инструкции Dockerfile:**
FROM, RUN, COPY, ADD, WORKDIR, ENV, CMD, ENTRYPOINT, EXPOSE, LABEL, USER,
VOLUME, SHELL, ARG, HEALTHCHECK, STOPSIGNAL, ONBUILD.

### `dck commit <контейнер> <образ>[:тег]`

Создать образ из текущего состояния контейнера (со всеми изменениями в overlay).

```bash
dck commit myproject myproject-snapshot:v1
```

Сохраняет всё, что вы установили (пакеты, файлы, конфиги) в переиспользуемый образ.

### `dck push <образ>[:тег]`

Отправить образ в registry.

```bash
dck push myapp:v1
dck push registry.example.com/myapp:v1
```

Авторизация: `-u user -p pass` или `DOCKER_USERNAME` / `DOCKER_PASSWORD`.

### `dck login <registry>` / `dck logout <registry>`

Войти/выйти из registry для авторизованных pull/push.

```bash
dck login registry.example.com
dck logout registry.example.com
```

---

## Жизненный цикл контейнера

### `dck ps`

Список контейнеров.

```bash
dck ps           # только запущенные
dck ps -a        # все (включая остановленные)
```

### `dck run [опции] <образ> [команда]`

Создать и запустить контейнер. Главная команда.

```bash
# Одноразовая команда
dck run --rm alpine echo "hello"

# Веб-сервер в фоне
dck run -d -n web -p 80:80 nginx:alpine

# Интерактивный shell
dck run -i -t --rm alpine sh

# С лимитами ресурсов
dck run -d --memory 512m --cpus 1.5 node:20 node app.js

# С томом и переменными
dck run -d -v /data:/data -e DB_URL=postgres://... myapp
```

**Важно:** dck использует пакет `flag` из Go, поэтому флаги нужно передавать раздельно:
- ✅ `dck run -i -t alpine sh` (правильно)
- ❌ `dck run -it alpine sh` (ошибка — используйте `-i -t`)

#### Флаги запуска

| Флаг | Описание |
|---|---|
| `-d` | Фоновый режим (detach) |
| `-n <имя>` | Имя контейнера |
| `-p H:C[/proto]` | Проброс порта `хост:контейнер/tcp\|udp` |
| `-v S:D` | Монтирование тома `источник:назначение` |
| `-e K=V` | Переменная окружения |
| `--env-file <файл>` | Файл с переменными окружения |
| `-i` | Интерактивный режим (держать stdin открытым) |
| `-t` | Выделить TTY (псевдотерминал) |
| `--rm` | Удалить контейнер при выходе |
| `--restart <политика>` | `no`, `always`, `on-failure`, `unless-stopped` |
| `--memory <лимит>` | Лимит памяти: `512m`, `1g`, `2g` |
| `--disk <лимит>` | Лимит диска: `1G`, `512M`, `2T` (создаёт ext4 образ) |
| `--cpus <число>` | Лимит CPU: `1.5` |
| `--workdir <дир>` | Рабочая директория внутри контейнера |
| `-h <имя>` | Hostname контейнера |
| `--entrypoint <cmd>` | Переопределить entrypoint |
| `--cap-add <cap>` | Добавить capability: `NET_ADMIN`, `SYS_PTRACE` |
| `--cap-drop <cap>` | Убрать capability: `ALL` |
| `--user <uid>` | Запуск от UID или `UID:GID` |
| `--readonly` | Read-only корневая ФС |
| `--no-new-privs` | Запретить повышение привилегий |
| `--sysctl <k=v>` | Sysctl параметр (например `net.ipv4.ip_forward=1`) |
| `--ulimit <опция>` | Ulimit: `nofile=1024:2048` |
| `-l, --label <k=v>` | Метка контейнера |
| `--dns <ip>` | DNS сервер (можно повторять) |
| `--network <режим>` | Сеть: `bridge` (по умолч.), `none`, `host` |
| `--startup <s>` | Стартовый скрипт (строка или `@файл`) — заменяет CMD |
| `--healthcheck-cmd <cmd>` | Команда проверки здоровья |
| `--healthcheck-interval <s>` | Интервал проверки (секунды) |
| `--healthcheck-retries <n>` | Количество попыток |
| `--healthcheck-timeout <s>` | Таймаут проверки (секунды) |

### `dck stop <контейнер>`

Остановить контейнер (SIGTERM, затем SIGKILL).

```bash
dck stop web
dck stop web db       # несколько
```

### `dck start <контейнер>`

Запустить остановленный контейнер. Все данные в overlay сохраняются.

```bash
dck start web
```

### `dck restart <контейнер>`

Перезапустить контейнер (stop + start).

```bash
dck restart web
```

### `dck rm [-f] <контейнер>`

Удалить контейнер. `-f` принудительно удаляет работающий.

```bash
dck rm web
dck rm -f web         # удалить даже если запущен
```

**Важно:** При удалении контейнера стирается его overlay-слой — все изменения (установленные пакеты, файлы) пропадают.

### `dck rename <контейнер> <новое-имя>`

Переименовать контейнер.

```bash
dck rename web web-new
```

### `dck port <контейнер>`

Показать проброс портов контейнера.

```bash
dck port web
```

### `dck top <контейнер>`

Показать процессы внутри контейнера.

```bash
dck top web
```

---

## Exec & Attach

### `dck exec [-i] [-t] <контейнер> <команда>`

Выполнить команду внутри работающего контейнера.

```bash
# Неинтерактивная команда
dck exec web nginx -s reload

# Интерактивный shell с TTY
dck exec -i -t myproject sh

# Интерактивный Python
dck exec -i -t myproject python3
```

Создаёт **новый процесс** внутри контейнера. Входит в неймспейсы контейнера (PID, mount, network, IPC)
и запускает команду прямо в корневой ФС контейнера (chroot не нужен — корень уже установлен через pivot_root).

### `dck attach <контейнер>`

Подключиться к **главному процессу** контейнера (работает только для контейнеров с `-d`).

```bash
dck run -d -i -t -n myproject alpine sh
dck attach myproject    # подключиться к sh
```

> **exec vs attach:** `attach` подключается к stdin/stdout главного процесса. `exec` запускает новую команду внутри контейнера. `console` — сокращение для `exec -i -t` с автоопределением shell.

`dck attach` **устойчив к Ctrl+C** — контейнер продолжает работать.

### `dck console <контейнер>`

Автоматически определить и запустить интерактивный shell внутри контейнера.
Эквивалент `dck exec -i -t <контейнер> sh`.

```bash
dck console myproject
```

---

## Логи и мониторинг

### `dck logs [-f] <контейнер>`

Показать логи контейнера.

```bash
dck logs web            # последние логи
dck logs -f web         # следить (tail -f)
```

### `dck stats [контейнер]`

Использование CPU, памяти, I/O и PIDs в реальном времени. Через cgroups v2.

```bash
dck stats               # все контейнеры
dck stats web           # конкретный
```

### `dck info`

Информация о системе: версия ядра, storage driver, директория данных, CPU, память, диск.

```bash
dck info
```

---

## Сеть

### Режимы сети

| Режим | Описание |
|---|---|
| `bridge` (по умолч.) | Каждый контейнер получает IP `10.0.2.X` на bridge `dck0`. Хост: `10.0.2.1`. |
| `none` | Без сети (только loopback) |
| `host` | Общая сеть с хостом (для VPN, сниффинга) |

```bash
dck run -d -n web -p 80:80 nginx:alpine       # bridge (по умолч.)
dck run -d --network none alpine sleep infinity
dck run -d --network host myvpn-container
```

### Схема сети

```
Хост:        dck0  10.0.2.1/24
Контейнер A: eth0  10.0.2.2
Контейнер B: eth0  10.0.2.3

A → хост:      ping 10.0.2.1      (хост — шлюз)
хост → A:      ping 10.0.2.2      (есть маршрут)
A → B:         ping 10.0.2.3      (через bridge)
A → порт B:    curl 10.0.2.1:8080 (DNAT: порт_хоста → порт_контейнера)
```

### Проброс портов

```bash
# TCP (по умолчанию)
-p 8080:80
-p 8080:80/tcp

# UDP
-p 53:53/udp

# Несколько портов
-p 80:80 -p 443:443
```

Проброс портов использует iptables DNAT с авто-настройкой UFW.

### Свой DNS

```bash
dck run -d --dns 1.1.1.1 --dns 8.8.8.8 nginx
```

---

## Хранилище и тома

### Синтаксис томов

```bash
# Bind mount (директория хоста)
-v /путь/на/хосте:/путь/в/контейнере
-v /путь/на/хосте:/путь/в/контейнере:ro     # только чтение
-v /путь/на/хосте:/путь/в/контейнере:shared # shared mount

# Именованный том (управляется dck)
-v myvolume:/путь/в/контейнере

# tmpfs (в памяти)
-v tmpfs:/путь/в/контейнере:size=1G,mode=0777

# NFS
-v nfs://сервер:/экспорт:/путь/в/контейнере:nfsopts=hard,intr
```

### Именованные тома

Тома хранятся в `~/.dck/volumes/`.

```bash
# Создать том
dck volume create mydata

# Список томов
dck volume ls

# Информация о томе
dck volume inspect mydata

# Удалить том
dck volume rm mydata

# Удалить неиспользуемые тома
dck volume prune
```

### Как работает хранилище

```
Хранилище: /root/.dck/

images/        OCI rootfs для каждого тега (только чтение)
containers/    JSON-файлы состояния
overlay/       upper/work/merged для каждого контейнера (слой записи)
volumes/       Именованные тома
logs/          stdout/stderr контейнера
consoles/      Unix сокеты для attach
networks/      Пул IP-адресов
```

**Overlay:** Каждый контейнер получает слой поверх read-only образа.
Изменения (установленные пакеты, файлы, правки) живут в overlay.
Они сохраняются между перезапусками (`dck stop` + `dck start`), но **удаляются**
при удалении контейнера (`dck rm`).

Чтобы сохранить изменения навсегда — используйте `dck commit`.

### Копирование файлов

```bash
# Из контейнера на хост
dck cp web:/etc/nginx/nginx.conf ./nginx.conf

# С хоста в контейнер
dck cp ./app.py web:/app/
```

---

## Лимиты ресурсов

### Память

```bash
dck run -d --memory 512m nginx    # 512 мегабайт
dck run -d --memory 1g nginx      # 1 гигабайт
dck run -d --memory 2g nginx      # 2 гигабайта
```

Через cgroups v2 memory controller. При превышении — OOM kill.

### CPU

```bash
dck run -d --cpus 1.5 nginx       # 1.5 ядра
dck run -d --cpus 2 nginx         # 2 ядра
```

Через CFS quota в cgroups v2.

### Диск

```bash
dck run -d --disk 1G nginx        # 1 GB
dck run -d --disk 10G nginx       # 10 GB
```

Создаёт sparse ext4 образ, который монтируется как overlay. Требует `mkfs.ext4`.

---

## Безопасность

### Пользователь

Запуск от непривилегированного пользователя:

```bash
dck run -d --user 1000 nginx
dck run -d --user 1000:1000 nginx   # UID:GID
```

### Capabilities

По умолчанию dck отключает опасные capability (SYS_ADMIN, SYS_MODULE и т.д.).

```bash
# Добавить capability
dck run -d --cap-add NET_ADMIN nginx
dck run -d --cap-add NET_ADMIN --cap-add SYS_PTRACE nginx

# Отключить все
dck run -d --cap-drop ALL nginx

# Вернуть конкретные после --cap-drop ALL
dck run -d --cap-drop ALL --cap-add NET_BIND_SERVICE nginx
```

### Read-only rootfs

```bash
dck run -d --readonly nginx
```

Корневая ФС только для чтения. Запись в тома по-прежнему работает.

### Запрет привилегий

```bash
dck run -d --no-new-privs nginx
```

Запрещает получение новых привилегий (setuid, setgid, capability) всем процессам в контейнере.

### Sysctls

```bash
dck run -d --sysctl net.ipv4.ip_forward=1 nginx
```

---

## Переменные окружения

```bash
# Одна переменная
dck run -e MY_VAR=value nginx

# Несколько
dck run -e DB_HOST=localhost -e DB_PORT=5432 nginx

# Из файла
dck run --env-file .env nginx
```

**Формат .env файла:**
```
DB_HOST=localhost
DB_PORT=5432
DB_USER=admin
```

### Авто-внедрённые DCK_* переменные

При запуске контейнера dck внедряет:

| Переменная | Описание |
|---|---|
| `DCK_CONTAINER_ID` | ID контейнера |
| `DCK_CONTAINER_NAME` | Имя контейнера |
| `DCK_IMAGE_NAME` | Имя образа (например `library/alpine`) |
| `DCK_IMAGE_TAG` | Тег образа (например `latest`) |
| `DCK_HOSTNAME` | Hostname контейнера |
| `DCK_MEMORY` | Лимит памяти в байтах |
| `DCK_CPU` | Лимит CPU в ядрах |
| `DCK_IP` | IP адрес контейнера |
| `DCK_RESTART` | Политика рестарта |
| `DCK_PORT_TCP_80` | Проброс портов |

Внутри контейнера доступны скрипты в `/dck/`:
- `/dck/info` — информация о контейнере
- `/dck/env` — переменные DCK_*
- `/dck/help` — справка

---

## Проверки здоровья (Healthchecks)

Запускает команду внутри контейнера через заданный интервал. После `retries` неудач контейнер убивается и перезапускается.

```bash
dck run -d \
  --healthcheck-cmd "curl -f http://localhost || exit 1" \
  --healthcheck-interval 30 \
  --healthcheck-retries 3 \
  --healthcheck-timeout 10 \
  nginx
```

Healthchecks можно также задавать в compose-файлах и dck.toml.

---

## Стартовые скрипты

`--startup` запускает кастомный скрипт вместо команды из образа:

```bash
# Скрипт строкой
dck run -d --startup "#!/bin/sh\necho 'Hello from startup'" alpine sleep infinity

# Из файла
dck run -d --startup @./myscript.sh ubuntu
```

Скрипт записывается в `/startup.sh` и выполняется через `/bin/sh`.
При наличии `--startup` он **заменяет** стандартный CMD/entrypoint.

---

## dck.toml / Compose

### Формат dck.toml

Определите контейнеры в TOML-файле, запускайте всё одной командой.

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

### compose.yaml / docker-compose.yaml

dck поддерживает стандартный формат Docker Compose YAML. Полная документация — в [compose.md](compose.md).

---

## dck up / dck down

### `dck up [имя] [-f <файл>]`

Создать и запустить контейнеры из compose-файла.

Автоопределение (по порядку):
1. `dck.toml`
2. `compose.yaml`
3. `compose.yml`
4. `docker-compose.yaml`
5. `docker-compose.yml`

```bash
dck up                    # автоопределение
dck up myapp              # только сервис "myapp"
dck up -f compose.prod.yaml
dck up --no-net           # без настройки сети
dck up --no-start         # создать, но не запускать
dck up --build            # пересобрать образы
dck up --pull             # скачать образы
dck up -d                 # в фоне
dck up --autostart        # установить systemd сервис для автозапуска
```

### `dck down [имя] [-f <файл>]`

Остановить и удалить контейнеры из compose-файла.

```bash
dck down                  # stop + remove
dck down myapp            # только "myapp"
dck down -f dck.toml
dck down -a               # удалить ВСЕ контейнеры
dck down --volumes        # также удалить тома
dck down --rmi            # также удалить образы
```

---

## dck serve

Запустить Docker-совместимый REST API сервер.

```bash
dck serve -p 2375
```

Совместим с Docker-клиентами, Portainer, VS Code Dev Containers и CI.

---

## Автозапуск при загрузке

```bash
dck bootstrap --install
```

Устанавливает systemd-сервис. После перезагрузки все контейнеры с `--restart always` запустятся автоматически.

```
Загрузка → systemd → dck-bootstrap.service → dck bootstrap
  └─ Для каждого контейнера с restart=always:
      1. Настройка overlayfs
      2. Запуск unshare с неймспейсами
      3. Настройка veth + iptables
```

---

## Кластеризация

dck поддерживает multi-node кластеризацию с управлением сервисами, DNS-обнаружением
и rolling updates. Полная документация — [cluster.md](cluster.md).

```bash
# Инициализировать кластер
dck cluster init --name prod --bind 0.0.0.0 --port 2375

# Присоединиться
dck cluster join 10.0.0.1:2375

# Список нод
dck cluster ls

# Покинуть кластер
dck cluster leave
```

---

## Управление сервисами

Сервисы позволяют запускать реплицированные контейнеры по кластеру.
Полная документация — [cluster.md](cluster.md).

```bash
dck service create --name web --replicas 3 --port 80:80 nginx:alpine
dck service ls
dck service scale web 5
dck service update web --image nginx:1.25
dck service rm web
```

---

## FaaS / Serverless

dck может запускать образы как serverless-функции с авто-масштабированием.
Полная документация — [faas.md](faas.md).

```bash
# Развернуть функцию
dck fn deploy --name hello --port 8080 --timeout 30 --idle 300 ghcr.io/myorg/hello-func

# Вызвать
dck fn call hello --data '{"name": "dck"}'

# Список
dck fn ls

# Удалить
dck fn rm hello
```

---

## Блюпринты

Блюпринты — предварительно настроенные шаблоны контейнеров из репозиториев.

```bash
# Список доступных
dck blueprint list

# Установить
dck blueprint install nginx-proxy

# Добавить свой репозиторий
dck blueprint repo add https://github.com/user/my-blueprints

# Список репозиториев
dck blueprint repo list

# Удалить репозиторий
dck blueprint repo remove my-blueprints
```

---

## События

Поток событий жизненного цикла контейнеров в JSON.

```bash
dck events                          # в реальном времени
dck events --since "2026-07-07 12:00:00"  # события с указанного времени
```

События: `start`, `stop`, `kill`, `oom`, `healthcheck_failed` и другие.

---

## Системные команды

### `dck system prune`

Удалить неиспользуемые контейнеры и образы.

```bash
dck system prune
```

### `dck update [--check]`

Проверить обновления и обновить dck.

```bash
dck update              # обновить
dck update --check      # только проверить
```

### `dck version`

Версия.

```bash
dck version
```

---

## Архитектура

```
dck run -d
  ├─ unshare --fork --pid --mount --net --uts --ipc dck init <id>
  │   └─ dck init → pivot_root в overlay → настройка /proc/lo/eth0 → exec CMD
  └─ dck console-serve <id>
      ├─ читает stdout pipe
      ├─ пишет в лог-файл
      ├─ слушает Unix сокет
      └─ рассылает всем attach-клиентам
```

### Ключевые концепции

| Понятие | Описание |
|---|---|
| **Образ (Image)** | Read-only rootfs (`python:3.11-slim`, `nginx:alpine`). Скачивается один раз через `dck pull`. |
| **Контейнер** | Образ + слой записи (overlay). Изменения живут в overlay, не в образе. |
| **Overlay** | Дифф-слой поверх образа. Сохраняется между перезапусками — пакеты остаются установленными. |
| **Том (Volume)** | Bind mount с хоста в контейнер. `-v /opt/mybot:/bot` монтирует `/opt/mybot` как `/bot`. |
| **Сеть** | Каждый контейнер получает IP `10.0.2.X` на bridge `dck0`. Хост: `10.0.2.1`. |

### Как это работает

1. `dck run` скачивает образ (если нет в кеше)
2. Создаёт overlay ФС (lower=rootfs образа, upper=слой контейнера, merged=корень контейнера)
3. Запускает `unshare` с неймспейсами PID, mount, net, UTS, IPC
4. Внутри неймспейса `dck init` делает `pivot_root` в overlay, монтирует /proc, настраивает сеть
5. Запускает команду контейнера (CMD или `--startup` скрипт)
6. Если в фоне — `dck console-serve` перехватывает stdout и раздаёт через Unix сокет для `dck attach`

---

## Решение проблем

### dck rm -f <контейнер> зависает

```bash
# Принудительно убить процесс
kill -9 $(grep -o '"pid":[0-9]*' /root/.dck/containers/*.json | grep -o '[0-9]*')

# Затем удалить
dck rm -f <контейнер>

# Ручная очистка если файлы состояния битые
rm -f /root/.dck/containers/<id>.json
```

### Overlay не монтируется

```bash
lsmod | grep overlay
modprobe overlay   # если не загружен
```

### Сеть не работает

```bash
# Проверить bridge
ip link show dck0

# Включить IP forwarding
sysctl net.ipv4.ip_forward

# Переустановить
dck system prune && dck pull alpine && dck run --rm alpine ping 8.8.8.8
```

### Проброс портов не работает

```bash
# Проверить iptables
iptables -t nat -L -n | grep dck

# UFW может блокировать — проверить
ufw status
```

### Rootless режим

dck поддерживает rootless-запуск на системах с `newuidmap`/`newgidmap`.
Rootless контейнеры используют userspace networking.

### Сравнение с Docker

| Возможность | dck | Docker |
|---|---|---|
| Демон | Нет демона | dockerd обязателен |
| Размер | ~5 MB | ~100+ MB |
| Неймспейсы | PID, Mount, Net, UTS, IPC | Все |
| Bridge сеть | dck0 (10.0.2.0/24) | docker0 |
| Проброс портов | iptables DNAT | iptables DNAT |
| Автозапуск | systemd oneshot | systemd dockerd |
| Формат образов | OCI/Docker V2 | OCI/Docker V2 |
