# dck

**dck** — 5 MB static binary, no daemon. Drop-in Docker replacement for Linux containers.

```
dck pull nginx                  dck pull alpine
dck run -d -p 80:80 nginx       dck run -it --rm alpine sh
dck up                          dck cluster init
dck serve                       dck fn deploy --name hello myfunc
```

## Documentation

| English | Русский |
|---|---|---|
| [Usage & Commands](en/usage.md) | [Команды и использование](ru/usage.md) |
| [Deploying Websites](en/websites.md) | [Развёртывание сайтов](ru/websites.md) |
| [Bots (Telegram, Discord)](en/bots.md) | [Боты (Telegram, Discord)](ru/bots.md) |
| [Compose / Deployment](en/compose.md) | [Compose / Развёртывание](ru/compose.md) |
| [Cluster Orchestration](en/cluster.md) | [Кластерная оркестрация](ru/cluster.md) |
| [FaaS / Serverless](en/faas.md) | [FaaS / Serverless](ru/faas.md) |
| [Build & Versioning](build.md) | [Сборка и версионирование](build.md) |
