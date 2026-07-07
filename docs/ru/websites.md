# Развёртывание сайтов с dck

Полные примеры развёртывания сайтов с разными стеками — статические сайты,
Python, Node.js, PHP, Java и полноценные приложения с базами данных.

Все примеры предполагают, что dck установлен на Linux-сервере с публичным IP.

---

## Содержание

- [Статический сайт (nginx)](#статический-сайт-nginx)
- [Статический сайт с HTTPS](#статический-сайт-с-https)
- [Python Flask](#python-flask)
- [Python FastAPI](#python-fastapi)
- [Python Django](#python-django)
- [Node.js Express](#nodejs-express)
- [Node.js Next.js](#nodejs-nextjs)
- [PHP + Nginx](#php--nginx)
- [Java Spring Boot](#java-spring-boot)
- [Go HTTP сервер](#go-http-сервер)
- [Полный стек с БД](#полный-стек-с-бд)
- [Multi-Container с Compose](#multi-container-с-compose)
- [Чеклист для продакшена](#чеклист-для-продакшена)

---

## Статический сайт (nginx)

Самый простой — отдавать HTML/CSS/JS файлы через nginx.

```bash
# Создать папку с сайтом
mkdir -p /var/www/mysite
echo "<h1>Hello from dck!</h1>" > /var/www/mysite/index.html

# Запустить nginx с примонтированными файлами
dck run -d --restart always \
  -n mysite -p 80:80 \
  -v /var/www/mysite:/usr/share/nginx/html:ro \
  nginx:alpine

# Проверить
curl http://localhost:80
```

### Свой конфиг nginx

```bash
mkdir -p /var/www/mysite /etc/nginx-conf

# Создать конфиг
cat > /etc/nginx-conf/default.conf << 'EOF'
server {
    listen 80;
    server_name mysite.example.com;
    root /usr/share/nginx/html;
    index index.html;
    location / { try_files $uri $uri/ =404; }
    location /api/ { proxy_pass http://backend:3000; }
}
EOF

dck run -d --restart always \
  -n mysite -p 80:80 \
  -v /var/www/mysite:/usr/share/nginx/html:ro \
  -v /etc/nginx-conf:/etc/nginx/conf.d:ro \
  nginx:alpine
```

---

## Статический сайт с HTTPS

### Самоподписанный сертификат (для теста)

```bash
mkdir -p /root/ssl /root/nginx-conf/ssl

# Сгенерировать сертификат
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /root/ssl/server.key \
  -out /root/ssl/server.crt \
  -subj "/CN=localhost"

# Скопировать в папку конфига
cp /root/ssl/server.crt /root/nginx-conf/ssl/
cp /root/ssl/server.key /root/nginx-conf/ssl/

# Конфиг nginx
cat > /root/nginx-conf/default.conf << 'EOF'
server {
    listen 443 ssl http2;
    server_name localhost;
    ssl_certificate /etc/nginx/conf.d/ssl/server.crt;
    ssl_certificate_key /etc/nginx/conf.d/ssl/server.key;
    root /usr/share/nginx/html;
    index index.html;
}
EOF

# Запустить
dck run -d --restart always \
  -n mysite -p 443:443 \
  -v /var/www/mysite:/usr/share/nginx/html:ro \
  -v /root/nginx-conf:/etc/nginx/conf.d \
  nginx:alpine

# Проверить
curl -k https://localhost:443
```

### Let's Encrypt (для продакшена)

```bash
# Установить certbot на хосте
apt-get install -y certbot

# Получить сертификат
certbot certonly --standalone -d mysite.example.com

# Создать конфиг nginx
mkdir -p /etc/nginx-ssl
cat > /etc/nginx-ssl/default.conf << 'EOF'
server {
    listen 80;
    server_name mysite.example.com;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl http2;
    server_name mysite.example.com;
    ssl_certificate /etc/letsencrypt/live/mysite.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mysite.example.com/privkey.pem;
    root /usr/share/nginx/html;
    index index.html;
}
EOF

# Запустить nginx
dck run -d --restart always \
  -n mysite -p 80:80 -p 443:443 \
  -v /var/www/mysite:/usr/share/nginx/html:ro \
  -v /etc/nginx-ssl:/etc/nginx/conf.d:ro \
  -v /etc/letsencrypt:/etc/letsencrypt:ro \
  nginx:alpine
```

---

## Python Flask

```bash
mkdir -p /opt/flask-app
cd /opt/flask-app

cat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return '<h1>Hello from Flask on dck!</h1>'

@app.route('/api')
def api():
    return {'message': 'Hello from dck!'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOF

echo "flask==3.0.0\ngunicorn==22.0.0" > requirements.txt

dck run -d --restart always \
  -n flask-app -p 5000:5000 \
  -v /opt/flask-app:/app \
  --workdir /app \
  --startup "pip install -r /app/requirements.txt && gunicorn -w 4 -b 0.0.0.0:5000 app:app" \
  python:3.11-slim

curl http://localhost:5000
```

---

## Python FastAPI

```bash
mkdir -p /opt/fastapi-app
cd /opt/fastapi-app

cat > main.py << 'EOF'
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI on dck!"}

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
EOF

echo "fastapi==0.109.0\nuvicorn==0.27.0" > requirements.txt

dck run -d --restart always \
  -n fastapi-app -p 8000:8000 \
  -v /opt/fastapi-app:/app \
  --workdir /app \
  --startup "pip install -r /app/requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000" \
  python:3.11-slim

curl http://localhost:8000
curl http://localhost:8000/docs   # Swagger UI
```

---

## Python Django

```bash
mkdir -p /opt/django-app
cd /opt/django-app

echo "django==5.0.0\ngunicorn==22.0.0\npsycopg2-binary==2.9.9" > requirements.txt

cat > start.sh << 'SCRIPT'
#!/bin/sh
set -e
cd /app
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn myproject.wsgi:application -w 4 -b 0.0.0.0:8000
SCRIPT

# Создать Django проект
dck run --rm \
  -v /opt/django-app:/app \
  --workdir /app \
  python:3.11-slim sh -c "pip install django && django-admin startproject myproject ."

# Запустить с БД
dck run -d --restart always \
  -n django-db \
  -v django-pgdata:/var/lib/postgresql/data \
  -e POSTGRES_DB=django \
  -e POSTGRES_USER=django \
  -e POSTGRES_PASSWORD=secret \
  postgres:16

dck run -d --restart always \
  -n django-app -p 8000:8000 \
  -v /opt/django-app:/app \
  --workdir /app \
  -e DB_HOST=10.0.2.1 \
  -e DB_NAME=django \
  -e DB_USER=django \
  -e DB_PASSWORD=secret \
  --startup @/app/start.sh \
  python:3.11-slim
```

---

## Node.js Express

```bash
mkdir -p /opt/express-app
cd /opt/express-app

cat > index.js << 'EOF'
const express = require('express');
const app = express();
const port = 3000;

app.get('/', (req, res) => {
  res.send('<h1>Hello from Express on dck!</h1>');
});

app.listen(port, () => {
  console.log(`App listening on port ${port}`);
});
EOF

echo '{ "name": "express-app", "scripts": { "start": "node index.js" }, "dependencies": { "express": "^4.18.2" } }' > package.json

dck run -d --restart always \
  -n express-app -p 3000:3000 \
  -v /opt/express-app:/app \
  --workdir /app \
  --startup "npm install && npm start" \
  node:20

curl http://localhost:3000
```

---

## PHP + Nginx

```bash
mkdir -p /opt/php-app
cd /opt/php-app

cat > index.php << 'EOF'
<?php
echo '<h1>Hello from PHP on dck!</h1>';
echo '<p>PHP version: ' . phpversion() . '</p>';
EOF

# Конфиг nginx для PHP-FPM
mkdir -p /etc/php-nginx
cat > /etc/php-nginx/default.conf << 'EOF'
server {
    listen 80;
    root /var/www/html;
    index index.php;
    location ~ \.php$ {
        fastcgi_pass 127.0.0.1:9000;
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }
}
EOF

# PHP-FPM контейнер
dck run -d --restart always \
  -n php-fpm \
  -v /opt/php-app:/var/www/html \
  php:8.2-fpm

# Узнать IP PHP контейнера
PHP_IP=$(dck inspect php-fpm | grep -o '"ip":"[^"]*"' | grep -o '[0-9.]*')
sed -i "s/127.0.0.1:9000/$PHP_IP:9000/" /etc/php-nginx/default.conf

# Nginx
dck run -d --restart always \
  -n php-web -p 80:80 \
  -v /opt/php-app:/var/www/html:ro \
  -v /etc/php-nginx:/etc/nginx/conf.d:ro \
  nginx:alpine
```

---

## Полный стек с БД

### Flask + PostgreSQL

```bash
# 1. PostgreSQL
dck run -d --restart always \
  -n pg \
  -v pgdata:/var/lib/postgresql/data \
  -e POSTGRES_DB=myapp \
  -e POSTGRES_USER=myapp \
  -e POSTGRES_PASSWORD=secret \
  postgres:16

# 2. Flask приложение
mkdir -p /opt/flask-pg
cd /opt/flask-pg

cat > app.py << 'EOF'
from flask import Flask, jsonify
import psycopg2, os

app = Flask(__name__)

def get_db():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', '10.0.2.1'),
        dbname=os.environ.get('DB_NAME', 'myapp'),
        user=os.environ.get('DB_USER', 'myapp'),
        password=os.environ.get('DB_PASS', 'secret')
    )

@app.route('/')
def home():
    return '<h1>Flask + PostgreSQL on dck!</h1>'

@app.route('/db')
def db_test():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT version()")
    ver = cur.fetchone()
    cur.close(); conn.close()
    return jsonify({'database': ver[0]})
EOF

echo -e "flask==3.0.0\ngunicorn==22.0.0\npsycopg2-binary==2.9.9" > requirements.txt

dck run -d --restart always \
  -n flask-app -p 5000:5000 \
  -v /opt/flask-pg:/app \
  --workdir /app \
  -e DB_HOST=10.0.2.1 \
  -e DB_NAME=myapp \
  -e DB_USER=myapp \
  -e DB_PASS=secret \
  --startup "pip install -r /app/requirements.txt && gunicorn -w 4 -b 0.0.0.0:5000 app:app" \
  python:3.11-slim
```

### Node.js + MySQL

```bash
# 1. MySQL
dck run -d --restart always \
  -n mysql \
  -v mysqldata:/var/lib/mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=myapp \
  -e MYSQL_USER=myapp \
  -e MYSQL_PASSWORD=secret \
  mysql:8

# 2. Express + MySQL
mkdir -p /opt/node-mysql
cd /opt/node-mysql

cat > index.js << 'EOF'
const express = require('express');
const mysql = require('mysql2/promise');
const app = express();
const PORT = 3000;

app.get('/', (req, res) => {
    res.send('<h1>Node.js + MySQL on dck!</h1>');
});

app.listen(PORT);
EOF

echo '{ "name": "app", "scripts": { "start": "node index.js" }, "dependencies": { "express": "^4.18.2", "mysql2": "^3.6.0" } }' > package.json

dck run -d --restart always \
  -n node-app -p 3000:3000 \
  -v /opt/node-mysql:/app \
  --workdir /app \
  --startup "npm install && node index.js" \
  node:20
```

---

## Multi-Container с Compose

### WordPress + MySQL

```yaml
services:
  db:
    image: mysql:8
    restart: always
    volumes:
      - wp_data:/var/lib/mysql
    environment:
      MYSQL_ROOT_PASSWORD: rootpass
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wpuser
      MYSQL_PASSWORD: wppass

  wordpress:
    image: wordpress:6-php8.2
    restart: always
    ports:
      - "8080:80"
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wpuser
      WORDPRESS_DB_PASSWORD: wppass
      WORDPRESS_DB_NAME: wordpress
    depends_on:
      db:
        condition: service_started

volumes:
  wp_data:
```

```bash
dck up -d
```

---

## Чеклист для продакшена

### Безопасность
- `--restart always` для авто-восстановления
- `--cap-drop ALL --cap-add NET_BIND_SERVICE` для минимальных прав
- Запуск от непривилегированного пользователя `--user`
- `--readonly` для rootfs где возможно
- HTTPS через Let's Encrypt
- Регулярное обновление образов

### Постоянство данных
- Использовать именованные тома или bind mounts
- Данные БД → смонтированный том
- Загрузки (uploads) → смонтированный том

### Производительность
- Установить `--memory` и `--cpus` для каждого контейнера
- Использовать `--startup` для кастомной логики инициализации
- Gunicorn/uvicorn с несколькими воркерами для Python
- PM2 или cluster mode для Node.js

### Мониторинг

```bash
# Использование ресурсов
dck stats

# Логи в реальном времени
dck logs -f web

# Статус
dck ps
```

### Бэкап

```bash
# Бэкап overlay контейнера (все изменения)
tar -czf container-backup.tar.gz /root/.dck/overlay/<id>/

# Бэкап томов
tar -czf volume-backup.tar.gz /root/.dck/volumes/<name>/

# Экспорт образа
dck export myapp:v1 -o myapp-backup.tar.gz
```
