package cmd

import (
	"fmt"
	"os"
)

var version = "1.2.0"
var repoURL = "https://gitlab.com/animesao/dck"

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
	case "rm":
		Rm(args)
	case "logs":
		Logs(args)
	case "exec":
		Exec(args)
	case "console":
		Console(args)
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
  dck stop <container>         Stop container
  dck rm [-f] <container>      Remove container
  dck logs [-f] <container>    Show/follow container logs
  dck exec <container> <cmd>   Execute command in container
  dck console <container>      Interactive shell in container
  dck attach <container>       Attach to container's main process
  dck images                   List images
  dck rmi <image>[:tag]        Remove image
  dck bootstrap [--install]    Start all containers (--install = add systemd service)
  dck update [--check]         Check for updates and self-update
  dck --help                   Show this help
  dck version, --version       Show version

Run options:
  -d          Detach (background)
  -n <name>   Container name
  -p H:C      Port mapping (host:container)
  -v S:D      Volume mount (src:dst)
  -e K=V      Environment variable
  -i          Interactive
  -t          Allocate TTY
  --rm        Remove on exit
  --restart   Restart policy (no, always, on-failure)
  -h <name>   Container hostname`)
}
