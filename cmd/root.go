package cmd

import (
	"fmt"
	"os"
)

var version = "1.7.0"
var repoURL = "https://raw.githubusercontent.com/animesao/dck"

func Execute() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	command := os.Args[1]
	args := os.Args[2:]

	switch command {
	case "pull":
		Pull(args)
	case "run":
		Run(args)
	case "ps":
		Ps(args)
	case "stop":
		Stop(args)
	case "start":
		StartCmd(args)
	case "restart":
		Restart(args)
	case "rm":
		Rm(args)
	case "logs":
		Logs(args)
	case "exec":
		Exec(args)
	case "console":
		Console(args)
	case "console-serve":
		ConsoleServe(args)
	case "attach":
		Attach(args)
	case "init":
		initContainer(args)
	case "images":
		Images(args)
	case "rmi":
		Rmi(args)
	case "update":
		Update(args)
	case "up":
		Up(args)
	case "down":
		Down(args)
	case "bootstrap":
		Bootstrap(args)
	case "--help", "-h", "help":
		printUsage()
	case "version", "--version", "-v":
		fmt.Println("dck version", version)
		fmt.Printf("Run 'dck update --check' to check for newer versions.\n")
	default:
		fmt.Printf("unknown command: %s\n", command)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println(`dck - simple container runtime

Usage:
  dck pull <image>[:tag]       Pull image from registry
  dck run [opts] <image> [cmd] Run container
  dck ps                       List running containers
  dck ps -a                    List all containers
  dck start <container>        Start a stopped container
  dck restart <container>      Restart container
  dck stop <container>         Stop container
  dck rm [-f] <container>      Remove container
  dck logs [-f] <container>    Show/follow container logs
  dck exec <container> <cmd>   Execute command in container
  dck console <container>      Interactive shell in container
  dck attach <container>       Attach to container's main process
  dck images                   List images
  dck rmi <image>[:tag]        Remove image
  dck up [name] [-f dck.toml]  Create/start containers from dck.toml
  dck down [name] [-f dck.toml] Stop/remove containers from dck.toml
  dck down -a                  Remove all containers
  dck bootstrap [--install]    Start all containers (--install = add systemd service)
  dck update [--check]         Check for updates and self-update
  dck --help                   Show this help
  dck version, --version       Show version

Run options:
  -d              Detach (background)
  -n <name>       Container name
  -p H:C[/proto]  Port mapping (host:container/tcp|udp, default tcp)
  -v S:D          Volume mount (src:dst)
  -e K=V          Environment variable
  --env-file <f>  Read environment variables from file
  -i              Interactive
  -t              Allocate TTY
  --rm            Remove on exit
  --restart       Restart policy (no, always, on-failure, unless-stopped)
  --memory <lim>  Memory limit (512m, 1g, 2g, etc.)
  --cpus <num>    CPU limit (e.g. 1.5)
  --workdir <dir> Working directory inside container
  -h <name>       Container hostname
  --entrypoint    Override image entrypoint
  --cap-add       Add Linux capabilities (e.g. NET_ADMIN)
  --cap-drop      Drop Linux capabilities (e.g. ALL)
  --user <uid>    Username or UID:GID
  --readonly      Make rootfs read-only
  --no-new-privs  Disable acquiring new privileges
  --sysctl <k=v>  Sysctl options (can repeat)
  --ulimit <opt>  Ulimit options (name=soft:hard)
  -l, --label     Container labels (key=val)
  --dns <ip>      DNS server (can repeat)
  --network <m>   Network mode (bridge/none/host)
  --healthcheck-cmd <cmd>      Health check command
  --healthcheck-interval <s>   Health check interval
  --healthcheck-retries <n>    Health check retries
  --healthcheck-timeout <s>    Health check timeout`)
}
