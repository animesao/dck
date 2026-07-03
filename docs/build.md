# Build & Versioning

## Requirements

- Go 1.18+
- Linux (for container execution features)
- Optional: `git` (for version injection)

## Quick build

```bash
go build -o dck .
```

Produces a single static binary.

## Cross-compile from any OS

```bash
GOOS=linux GOARCH=amd64 go build -o dck .
```

## Version injection

Version is embedded from `cmd/VERSION`:

```
echo "1.2.3" > cmd/VERSION
go build -o dck .
dck version   # → dck version 1.2.3
```

### With build date and commit (recommended for releases)

```bash
go build -ldflags \
  "-X dck/internal/build.version=$(cat cmd/VERSION) \
   -X dck/internal/build.date=$(date -u +%FT%TZ) \
   -X dck/internal/build.commit=$(git rev-parse --short HEAD)" \
  -o dck .
```

Where `internal/build` package contains:

```go
package build

var (
    version string
    date    string
    commit  string
)
```

## Binary size

| Build mode | Size |
|---|---|
| Default (no cgo) | ~4.8 MB |
| `-ldflags="-s -w"` | ~3.9 MB |
| `-ldflags="-s -w"` + UPX | ~1.2 MB |

```bash
# Strip and pack
go build -ldflags="-s -w" -o dck .
upx --best dck
```

## Verify

```bash
./dck version
./dck info
```

## Update check

```bash
dck update --check   # Check latest release
dck update           # Self-update
```
