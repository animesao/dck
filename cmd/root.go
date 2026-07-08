package cmd

import (
	"fmt"
	"os"
)

var repoURL = "https://raw.githubusercontent.com/animesao/dck"
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
	case "sftp":
		Sftp(args)
	case "ftp":
		Ftp(args)
	case "sshkey":
		Sshkey(args)
	case "sftp-serve":
		SFTPServe(args)
	case "ftp-serve":
		FTPServe(args)
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
   dck sftp <container>          SSH+SFTP info for container (terminal + file transfer)
   dck ftp <container>           FTP info for container
   dck sshkey <container>        Show SSH private key for terminal access
   dck sshkey --gen <container>  Generate new SSH keypair
     dck blueprint list           List available blueprints from all repositories
     dck blueprint install <name> Install a blueprint (pull + run container)
     dck blueprint repo add <url> Add a custom blueprint repository
     dck blueprint repo list      List blueprint repositories
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
  --startup <s>   Startup script (inline or @file)
  --healthcheck-cmd <cmd>      Health check command
  --healthcheck-interval <s>   Health check interval
  --healthcheck-retries <n>    Health check retries
  --healthcheck-timeout <s>    Health check timeout
   --sftp                       Enable SSH+SFTP server (file transfer + terminal, jailed)
   --ssh                        Enable SSH terminal access via nsenter (file transfer + shell)
   --ftp                        Enable built-in FTP server (jailed to container root)

SSH/SFTP/FTP commands:
   dck sftp <container>         Show SSH/SFTP connection info
   dck sftp --start <c>         Start SSH/SFTP server (blocking)
   dck sftp --stop <c>          Stop SSH/SFTP server
   dck ftp <container>          Show FTP connection info
   dck ftp --start <c>          Start FTP server (blocking)
   dck ftp --stop <c>           Stop FTP server
   dck sshkey <container>       Show SSH private key path and public key
   dck sshkey --gen <container> Generate new SSH keypair

When run with --sftp/--ssh, a separate SSH server process is started
that Jails the user to the container's filesystem (chroot via overlay).
Connect via SSH: ssh -p <port> -i <key> dck@host
Connect via SFTP: sftp -P <port> dck@host (password = container ID)
Connect via FTP: ftp dck@host:<port> (password = container ID)`)
}
