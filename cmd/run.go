package cmd

import (
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	"dck/internal/container"
	"dck/internal/image"
)

func Run(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	detach := fs.Bool("d", false, "Detach mode")
	name := fs.String("n", "", "Container name")
	interactive := fs.Bool("i", false, "Interactive mode")
	tty := fs.Bool("t", false, "Allocate TTY")
	rm := fs.Bool("rm", false, "Remove container on exit")
	hostname := fs.String("h", "", "Container hostname")
	restart := fs.String("restart", "", "Restart policy")
	envVars := fs.String("e", "", "Environment variables (key=val,key=val)")
	portMapping := fs.String("p", "", "Port mapping (host:container)")
	volumeMounts := fs.String("v", "", "Volume mounts (src:dst)")
	fs.Parse(args)

	freeArgs := fs.Args()
	if len(freeArgs) < 1 {
		fmt.Println("Usage: dck run [opts] <image> [cmd...]")
		os.Exit(1)
	}

	imageRef := freeArgs[0]
	var cmd []string
	if len(freeArgs) > 1 {
		cmd = freeArgs[1:]
	}

	img, err := image.Pull(imageRef)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error pulling image: %v\n", err)
		os.Exit(1)
	}

	var ports []container.PortMap
	if *portMapping != "" {
		for _, p := range strings.Split(*portMapping, ",") {
			parts := strings.Split(p, ":")
			if len(parts) == 2 {
				host, _ := strconv.Atoi(parts[0])
				cont, _ := strconv.Atoi(parts[1])
				ports = append(ports, container.PortMap{HostPort: host, ContainerPort: cont, Protocol: "tcp"})
			}
		}
	}

	var volumes []container.VolumeMount
	if *volumeMounts != "" {
		for _, v := range strings.Split(*volumeMounts, ",") {
			parts := strings.Split(v, ":")
			if len(parts) == 2 {
				volumes = append(volumes, container.VolumeMount{Source: parts[0], Target: parts[1]})
			}
		}
	}

	var env []string
	if *envVars != "" {
		env = strings.Split(*envVars, ",")
	}

	if *name != "" {
		if existing := container.FindByName(*name); existing != nil {
			fmt.Fprintf(os.Stderr, "Error: container with name %q already exists (%s)\n", *name, existing.ID[:12])
			os.Exit(1)
		}
	}

	opts := container.CreateOpts{
		Name:        *name,
		Cmd:         cmd,
		Ports:       ports,
		Volumes:     volumes,
		Env:         env,
		Hostname:    *hostname,
		Restart:     *restart,
		Detach:      *detach,
		Interactive: *interactive || *tty,
		TTY:         *tty,
		RemoveOnExit: *rm,
	}

	c := container.New(img, opts)
	if err := c.Save(); err != nil {
		fmt.Fprintf(os.Stderr, "Error saving container: %v\n", err)
		os.Exit(1)
	}

	if err := c.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Error starting container: %v\n", err)
		os.Exit(1)
	}
}
