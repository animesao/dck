# Changelog

## 1.15.0 (2026-06-13)

### Security
- **pivot_root** вместо chroot — исправлен container escape vector
- Build tags (`//go:build linux`) добавлены на Linux-only файлы

### Bug Fixes
- **Disk limit**: исправлен path mismatch — overlay монтируется в правильную merged директорию
- **Race condition StoppedByUser**: `sync.Map` для атомарного флага между Stop() и monitor goroutine
- **Error swallowing**: логируются ошибки cgroup, mount, network, kill, overlay
- **Context/Timeout**: volume и network команды теперь с 30s timeout через `exec.CommandContext`
- **RCON**: мёртвый код помечен комментарием

### Features
- **`dck stop --all`**: остановка всех запущенных контейнеров
- **`dck exec -i/-t`**: флаги парсятся и применяются корректно
- **`dck console`**: TTY handling через ExecOpts

### Maintenance
- Debian control version синхронизирована с VERSION (1.15.0)

## 1.14.0 (Previous)
- DiskLimit support + loop device quota enforcement
- dck run --disk human-readable format
- Fix overlay mount ordering
- Multi-arch image resolution
