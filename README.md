# dck — Simple Docker CLI client

A lightweight CLI wrapper to simplify daily Docker operations.

## Install

```bash
pip install .
```

## Usage

```
dck ps [-a]                     List containers
dck logs <container> [-f]       View logs
dck start/stop/restart/rm       Manage containers
dck restart-policy <c> <p>      Set auto-restart policy
dck images                      List images
dck pull <image>                Pull an image
dck rmi <image>                 Remove an image
dck compose up/down/ps/logs     Docker Compose
dck stats                       Live resource monitor
dck doctor                      Docker diagnostics
```
