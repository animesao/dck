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

type stringSlice []string

func (s *stringSlice) String() string {
	return strings.Join(*s, ",")
}

func (s *stringSlice) Set(v string) error {
	*s = append(*s, v)
	return nil
}

func Run(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	detach := fs.Bool("d", false, "Detach mode")
	name := fs.String("n", "", "Container name")
	interactive := fs.Bool("i", false, "Interactive mode")
	tty := fs.Bool("t", false, "Allocate TTY")
	rm := fs.Bool("rm", false, "Remove container on exit")
	hostname := fs.String("h", "", "Container hostname")
	restart := fs.String("restart", "", "Restart policy")
	var envVars stringSlice
	fs.Var(&envVars, "e", "Environment variables (key=val)")
	envFile := fs.String("env-file", "", "Path to .env file")
	portMapping := fs.String("p", "", "Port mapping (host:container[/protocol])")
	volumeMounts := fs.String("v", "", "Volume mounts (src:dst)")
	memory := fs.String("memory", "", "Memory limit (e.g. 512m, 1g)")
	cpus := fs.Float64("cpus", 0, "CPU limit (number of CPUs, e.g. 1.5)")
	workdir := fs.String("workdir", "", "Working directory inside container")
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

	parsePort := func(s string) (container.PortMap, error) {
		proto := "tcp"
		if parts := strings.SplitN(s, "/", 2); len(parts) == 2 {
			proto = parts[1]
			s = parts[0]
		}
		parts := strings.Split(s, ":")
		if len(parts) != 2 {
			return container.PortMap{}, fmt.Errorf("invalid port mapping: %s", s)
		}
		host, _ := strconv.Atoi(parts[0])
		cont, _ := strconv.Atoi(parts[1])
		return container.PortMap{HostPort: host, ContainerPort: cont, Protocol: proto}, nil
	}

	var ports []container.PortMap
	if *portMapping != "" {
		for _, p := range strings.Split(*portMapping, ",") {
			pm, err := parsePort(p)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error: %v\n", err)
				os.Exit(1)
			}
			ports = append(ports, pm)
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
	for _, e := range envVars {
		env = append(env, e)
	}
	if *envFile != "" {
		fileEnv, err := container.ParseEnvFile(*envFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error reading env file: %v\n", err)
			os.Exit(1)
		}
		env = append(env, fileEnv...)
	}

	memoryLimit, _ := container.ParseMemoryString(*memory)
	if *memory != "" && memoryLimit == 0 {
		fmt.Fprintf(os.Stderr, "Error: invalid memory value: %s\n", *memory)
		os.Exit(1)
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
		MemoryLimit:  memoryLimit,
		CPUCount:     *cpus,
		WorkingDir:   *workdir,
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
