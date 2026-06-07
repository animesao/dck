import json
from pathlib import Path

DCK_DIR = Path.home() / ".dck"
CONFIG_FILE = DCK_DIR / "config.json"
LANG = "en"

TRANSLATIONS = {
    "en": {
        "port.mappings": "Port mappings (host:container/protocol)",
        "port.extra": "Add extra port (host:container/protocol) or leave empty",
        "port.invalid": "Invalid format. Use host:container/protocol (e.g. 8080:80/tcp)",
        "env.vars": "Environment variables",
        "env.extra": "Add variable (KEY=value) or leave empty",
        "env.invalid": "Invalid format. Use KEY=value",
        "volume.mounts": "Volume mounts (host path : container path)",
        "volume.extra": "Add volume (host_path:container_path) or leave empty",
        "volume.invalid": "Invalid format. Use /host/path:/container/path",
        "volume.notfound": "Warning: path {path} does not exist. It will be created.",
        "ram.limit": "RAM limit",
        "cpu.limit": "CPU limit (cores)",
        "pulling": "Pulling image",
        "creating": "Creating container...",
        "created": "Container created!",
        "start.now": "Start container now?",
        "status.running": "Started",
        "port.info": "Port",
        "manage.hint": "Manage",
        "container.running": "Running",
        "container.exited": "Exited",
        "error": "Error",
        "memory.invalid": "Invalid memory format. Use: 512m, 2g, 1t (b, k, m, g, t)",
    },
    "ru": {
        "port.mappings": "Проброс портов (хост:контейнер/протокол)",
        "port.extra": "Добавить порт (хост:контейнер/протокол) или оставьте пустым",
        "port.invalid": "Неверный формат. Используйте хост:контейнер/протокол (например 8080:80/tcp)",
        "env.vars": "Переменные окружения",
        "env.extra": "Добавить переменную (КЛЮЧ=значение) или оставьте пустым",
        "env.invalid": "Неверный формат. Используйте КЛЮЧ=значение",
        "volume.mounts": "Монтирование томов (путь на хосте : путь в контейнере)",
        "volume.extra": "Добавить том (путь_на_хосте:путь_в_контейнере) или оставьте пустым",
        "volume.invalid": "Неверный формат. Используйте /хост/путь:/контейнер/путь",
        "volume.notfound": "Предупреждение: путь {path} не существует. Он будет создан.",
        "ram.limit": "Лимит RAM",
        "cpu.limit": "Лимит CPU (ядра)",
        "pulling": "Загрузка образа",
        "creating": "Создание контейнера...",
        "created": "Контейнер создан!",
        "start.now": "Запустить контейнер сейчас?",
        "status.running": "Запущен",
        "port.info": "Порт",
        "manage.hint": "Управление",
        "container.running": "Работает",
        "container.exited": "Остановлен",
        "error": "Ошибка",
        "memory.invalid": "Неверный формат памяти. Используйте: 512m, 2g, 1t (b, k, m, g, t)",
    },
}


def load_config():
    global LANG
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            LANG = cfg.get("lang", "en")
        except (json.JSONDecodeError, Exception):
            pass


def save_config():
    DCK_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"lang": LANG}, indent=2))


def set_lang(code):
    global LANG
    LANG = code
    save_config()


def t(key, **kwargs):
    lang = LANG
    translations = TRANSLATIONS.get(lang, TRANSLATIONS.get("en", {}))
    template = translations.get(key, key)
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


load_config()
