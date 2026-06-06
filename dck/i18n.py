import json
import os
from pathlib import Path

DCK_DIR = Path.home() / ".dck"
CONFIG_FILE = DCK_DIR / "config.json"
LANG = "en"

TRANSLATIONS = {
    "ru": {
        "lang.name": "Русский",
        "select.template": "Выберите номер или имя шаблона",
        "custom.image": "Свой образ (любой Docker образ)",
        "invalid.choice": "Неверный выбор. Попробуйте снова.",
        "create.this": "Создать этот контейнер?",
        "cancelled": "Отменено.",
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
        "tip": "Совет",
        "container.running": "Работает",
        "container.exited": "Остановлен",
        "container.dead": "Ошибка",
        "save.template": "Сохранить как шаблон для повторного использования?",
        "template.name": "Имя шаблона",
        "template.desc": "Описание",
        "template.saved": "Шаблон '{name}' сохранён",
        "template.updated": "Шаблон '{name}' обновлён",
        "update.template": "Обновить сохранённый шаблон этими настройками?",
        "custom.container": "Произвольный контейнер",
        "custom.image.prompt": "Docker образ",
        "start.with.restart": "Установить политику автозапуска после запуска",
        "restart.policy": "Политика автозапуска",
        "restart.policy.set": "Политика автозапуска установлена на '{policy}' для '{container}'",
        "containers.notfound": "Контейнеры не найдены.",
        "images.notfound": "Образы не найдены.",
        "error": "Ошибка",
        "container.notfound": "Контейнер '{name}' не найден.",
        "image.notfound": "Образ '{name}' не найден.",
        "memory.invalid": "Неверный формат памяти. Используйте: 512m, 2g, 1t (b, k, m, g, t)",
        "docker.notfound": "Docker не установлен. Запустите 'dck doctor' для инструкций.",
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


# Load config on import
load_config()
