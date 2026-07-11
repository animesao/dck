package cmd

import (
	"fmt"
	"os"
)

var repoURL = "https://raw.githubusercontent.com/animesao/dck"
var releaseURL = "https://github.com/animesao/dck"
var blueprintRepoURL = "https://raw.githubusercontent.com/dck-organization/dck-blueprints"

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
	case "port":
		Port(args)
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
	case "fs":
		Fs(args)
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
	case "stats":
		Stats(args)
	case "volume":
		Volume(args)
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
	case "cp":
		Cp(args)
	case "top":
		Top(args)
	case "commit":
		Commit(args)
	case "rename":
		Rename(args)
	case "info":
		Info(args)
	case "serve":
		Serve(args)
	case "system":
		System(args)
	case "build":
		Build(args)
	case "push":
		Push(args)
	case "login":
		Login(args)
	case "logout":
		Logout(args)
	case "events":
		Events(args)
	case "export":
		Export(args)
	case "import":
		Import(args)
	case "cluster":
		Cluster(args)
	case "service":
		Service(args)
	case "fn":
		Fn(args)
	case "blueprint":
		Blueprint(args)
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
   dck port <container>         Show port mappings
   dck port add <c> H:C[/p]     Add port mapping to running container
   dck port rm <c> H[/p]        Remove port mapping from running container
  dck start <container>        Start a stopped container
  dck restart <container>      Restart container
  dck stop <container>         Stop container
  dck rm [-f] <container>      Remove container
    dck logs [-f] <container>    Show/follow container logs
    dck fs ls <c> [path]         List files in container
    dck fs cat <c> <path>        Show file content
    dck fs tree <c> [path]       Directory tree
    dck fs find <c> [path] [opts] Find files (--name, --grep, --type, --max-depth)
  dck stats [container]        Show live resource usage stats (CPU, RAM, IO, PIDs)
   dck exec <container> <cmd>   Execute command in container
   dck console <container>      Interactive shell in container
   dck attach <container>       Attach to container's main process
   dck top <container>          Show running processes in container
   dck cp <src> <dst>           Copy files between host and container
   dck images                   List images
   dck rmi <image>[:tag]        Remove image
   dck commit <c> <img>[:tag]   Create image from container
   dck rename <c> <new-name>    Rename container
   dck info                     Show system-wide information
   dck serve [-p 2375]          Start Docker-compatible REST API server
   dck system prune             Remove unused containers and images
   dck volume create <name>     Create a named volume
   dck volume ls                List volumes
   dck volume rm <name>         Remove a volume
   dck volume inspect <name>    Inspect a volume
   dck volume prune             Remove unused volumes
   dck build -t name:tag [opts] .  Build image from Dockerfile
   dck cluster init               Initialize a new cluster
   dck cluster join <peer>       Join an existing cluster
   dck cluster leave              Leave the cluster
   dck cluster ls                List cluster nodes
   dck service create ...        Create a service with replicas
   dck service ls                List services
   dck service rm <name>         Remove a service
   dck service scale <name> N    Scale service
   dck service update <name>     Update service (rolling update)
   dck fn deploy                 Deploy a serverless function
   dck fn ls                     List functions
   dck fn rm <name>              Remove a function
   dck fn call <name>            Invoke a function
   dck push <image>[:tag]        Push image to registry
   dck login <registry>          Log in to a registry
   dck logout <registry>         Log out from a registry
   dck events                    Stream container events
   dck export <image> -o f.tar.gz Export image to file
   dck import <file.tar.gz>      Import image from file
     dck blueprint list           List available blueprints from all repositories
     dck blueprint install <name> Install a blueprint (pull + run container)
     dck blueprint repo add <url> Add a custom blueprint repository
     dck blueprint repo list      List blueprint repositories
    dck fs ls <c> [path]          List files in container
    dck fs cat <c> <path>         Show file content
    dck fs tree <c> [path]        Show directory tree
    dck fs find <c> [path] [opts] Find files (--name, --grep, --type, --max-depth)
    dck update [--check]         Check for updates and self-update
    dck --help                   Show this help
    dck version, --version       Show version

Run options:
  -d              Detach (background)                                    e.g. -d
  -n <name>       Container name                                         e.g. -n myapp
  -p H:C[/proto]  Port mapping (host:container/tcp|udp)                  e.g. -p 8080:80, -p 53:53/udp
  --ports H:C     Port mapping (alias for -p)                            e.g. --ports 8080:80
  -v S:D          Volume mount (src:dst)                                  e.g. -v /data:/data
  --volume S:D    Volume mount (alias for -v)                             e.g. --volume /data:/data
  --vol S:D       Volume mount (alias for -v)                             e.g. --vol myvol:/data
  -e K=V          Environment variable                                   e.g. -e DB_HOST=localhost
  --env-file <f>  Read environment variables from file                    e.g. --env-file .env
  -i              Interactive                                            e.g. -i
  -t              Allocate TTY                                           e.g. -t
  --rm            Remove on exit                                         e.g. --rm
  --restart       Restart policy (no|always|on-failure|unless-stopped)    e.g. --restart always
  --memory <lim>  Memory limit                                           e.g. --memory 1g, --memory 512m
  --ram <lim>     Memory limit (alias for --memory)                      e.g. --ram 2g
  --cpus <num>    CPU limit                                              e.g. --cpus 2, --cpus 0.5
  --cpu <num>     CPU limit (alias for --cpus)                           e.g. --cpu 1.5
  --disk <lim>    Disk limit                                             e.g. --disk 10G
  --workdir <dir> Working directory inside container                     e.g. --workdir /app
  -h <name>       Container hostname                                     e.g. -h myserver
  --entrypoint    Override image entrypoint                              e.g. --entrypoint /bin/bash
  --image <img>   Container image (instead of positional arg)            e.g. --image nginx:alpine
  --cmd <cmd>     Container command (instead of positional args)         e.g. --cmd "python app.py"
  --command <cmd> Container command (alias for --cmd)                    e.g. --command "java -jar server.jar"
  --cap-add       Add Linux capabilities (can repeat)                    e.g. --cap-add NET_ADMIN
  --cap-drop      Drop Linux capabilities (can repeat)                   e.g. --cap-drop ALL
  --user <uid>    Username or UID:GID                                    e.g. --user 1000:1000
  --readonly      Make rootfs read-only                                  e.g. --readonly
  --no-new-privs  Disable acquiring new privileges                       e.g. --no-new-privs
  --sysctl <k=v>  Sysctl options (can repeat)                            e.g. --sysctl net.ipv4.ip_forward=1
  --ulimit <opt>  Ulimit options (name=soft:hard)                        e.g. --ulimit nofile=1024:2048
  -l, --label     Container labels (key=val)                             e.g. -l env=prod
  --dns <ip>      DNS server (can repeat)                                e.g. --dns 8.8.8.8
  --network <m>   Network mode (bridge|none|host)                        e.g. --network host
  --startup <s>   Startup script (inline or @file)                       e.g. --startup @setup.sh
  --healthcheck-cmd <cmd>      Health check command                      e.g. --healthcheck-cmd "curl -f http://localhost"
  --healthcheck-interval <s>   Health check interval (seconds)           e.g. --healthcheck-interval 30
  --healthcheck-retries <n>    Health check retries                      e.g. --healthcheck-retries 5
  --healthcheck-timeout <s>    Health check timeout (seconds)            e.g. --healthcheck-timeout 10`)
}
