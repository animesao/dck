TEMPLATES = {
    "nginx": {
        "name": "Nginx Web Server",
        "desc": "Lightweight web server and reverse proxy",
        "image": "nginx:alpine",
        "ports": [{"host": 80, "container": 80, "proto": "tcp"}],
        "ram": "128m",
        "cpu": "0.5",
        "disk": "~100MB",
        "tty": False,
        "volumes": [
            {"path": "/usr/share/nginx/html", "label": "HTML files", "default": "./html"},
        ],
        "env": [],
        "note": "Place index.html and other static files in ./html, then refresh your browser",
    },
    "minecraft": {
        "name": "Minecraft Server (Java Edition)",
            "desc": "Minecraft Java Edition dedicated server (Paper, latest stable by default)",
        "image": "itzg/minecraft-server",
        "ports": [{"host": 25565, "container": 25565, "proto": "tcp"}],
        "ram": "2g",
        "cpu": "2",
        "disk": "~1GB",
        "tty": True,
        "volumes": [
            {"path": "/data", "label": "World data & config", "default": "./minecraft-data/{name}"},
        ],
        "env": [
            {"key": "EULA", "default": "TRUE", "desc": "Accept EULA (must be TRUE)"},
            {"key": "TYPE", "default": "PAPER", "desc": "Server type: VANILLA | PAPER | SPIGOT | FABRIC | FORGE"},
            {"key": "VERSION", "default": "", "desc": "Minecraft version (e.g. 1.21, 1.20.4, LATEST). Leave empty for latest stable."},
            {"key": "OVERRIDE_SERVER_PROPERTIES", "default": "true", "desc": "Force overwrite server.properties on start"},
            {"key": "REMOVE_OLD_MODS_DIR", "default": "true", "desc": "Clean old mods when switching server types"},
            {"key": "DIFFICULTY", "default": "easy", "desc": "peaceful | easy | normal | hard"},
            {"key": "GAMEMODE", "default": "survival", "desc": "survival | creative | adventure"},
            {"key": "MAX_PLAYERS", "default": "20", "desc": "Max players"},
            {"key": "MOTD", "default": "dck Minecraft Server!", "desc": "Server message of the day"},
            {"key": "MEMORY", "default": "2g", "desc": "Java heap memory (e.g. 1g, 2g, 4g)"},
        ],
        "note": "Auto-restart unless-stopped. Server restarts automatically on crash.",
    },
    "terraria": {
        "name": "Terraria Server",
        "desc": "Terraria dedicated server (TShock)",
        "image": "ryshe/terraria:latest",
        "ports": [{"host": 7777, "container": 7777, "proto": "tcp"}],
        "ram": "1g",
        "cpu": "1",
        "disk": "~500MB",
        "tty": True,
        "volumes": [
            {"path": "/world", "label": "World files", "default": "./terraria-world"},
        ],
        "env": [],
        "note": "Connect via Terraria client on port 7777",
    },
    "valheim": {
        "name": "Valheim Dedicated Server",
        "desc": "Valheim server with auto-backup",
        "image": "lloesche/valheim-server",
        "ports": [
            {"host": 2456, "container": 2456, "proto": "udp"},
            {"host": 2457, "container": 2457, "proto": "udp"},
        ],
        "ram": "2g",
        "cpu": "2",
        "disk": "~2GB",
        "tty": True,
        "volumes": [
            {"path": "/config", "label": "Server config & worlds", "default": "./valheim-config"},
        ],
        "env": [
            {"key": "SERVER_NAME", "default": "dck Valheim", "desc": "Server display name"},
            {"key": "SERVER_PASS", "default": "secret123", "desc": "Password (min 5 chars)"},
            {"key": "WORLD_NAME", "default": "Dedicated", "desc": "World name"},
        ],
        "note": "Password must be at least 5 characters",
    },
    "cs2": {
        "name": "Counter-Strike 2 Server",
        "desc": "CS2 dedicated server (SRCDS)",
        "image": "cm2network/cs2",
        "ports": [
            {"host": 27015, "container": 27015, "proto": "tcp"},
            {"host": 27015, "container": 27015, "proto": "udp"},
        ],
        "ram": "4g",
        "cpu": "4",
        "disk": "~10GB",
        "tty": True,
        "volumes": [
            {"path": "/home/steam/cs2-dedicated", "label": "Game files", "default": "./cs2-files"},
        ],
        "env": [],
        "note": "First run downloads ~8GB of game files (may take a while)",
    },
    "satisfactory": {
        "name": "Satisfactory Server",
        "desc": "Satisfactory dedicated server",
        "image": "wolveix/satisfactory-server",
        "ports": [
            {"host": 7777, "container": 7777, "proto": "udp"},
            {"host": 7777, "container": 7777, "proto": "tcp"},
        ],
        "ram": "4g",
        "cpu": "4",
        "disk": "~5GB",
        "tty": True,
        "volumes": [
            {"path": "/config", "label": "Server config", "default": "./satisfactory-config"},
        ],
        "env": [
            {"key": "MAXPLAYERS", "default": "4", "desc": "Max players"},
            {"key": "SERVERQUERYPORT", "default": "15777", "desc": "Query port"},
        ],
        "note": "Satisfactory server needs at least 4GB RAM",
    },
}


def list_templates():
    return dict(TEMPLATES)


def get_template(name):
    return TEMPLATES.get(name)
