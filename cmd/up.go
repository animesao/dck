package cmd

import (
	"flag"
	"fmt"
	"os"
	"strings"

	"dck/internal/config"
	"dck/internal/container"
	"dck/internal/image"
)

func Up(args []string) {
	fs := flag.NewFlagSet("up", flag.ExitOnError)
	configPath := fs.String("f", "", "Path to config file")
	fs.Parse(args)

	freeArgs := fs.Args()
	var filter string
	if len(freeArgs) > 0 {
		filter = freeArgs[0]
	}

	cfg, path, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Using config: %s\n", path)

	started := 0
	for name, cc := range cfg.Container {
		if filter != "" && name != filter {
			continue
		}

		if cc.Image == "" {
			fmt.Fprintf(os.Stderr, "container %q: no image specified\n", name)
			continue
		}

		img, err := image.Pull(cc.Image)
		if err != nil {
			fmt.Fprintf(os.Stderr, "container %q: error pulling image %s: %v\n", name, cc.Image, err)
			continue
		}

		existing := container.FindByName(name)
		if existing != nil {
			if existing.Status == container.Running {
				fmt.Printf("  %s: already running\n", name)
				continue
			}
			fmt.Printf("  %s: starting existing container...\n", name)
			existing.Status = container.Created
			if err := existing.Start(); err != nil {
				fmt.Fprintf(os.Stderr, "  %s: error starting: %v\n", name, err)
			} else {
				fmt.Printf("  %s: started\n", name)
				started++
			}
			continue
		}

		opts := container.CreateOpts{
			Name:    name,
			Detach:  true,
			Restart: cc.Restart,
		}
		if opts.Restart == "" {
			opts.Restart = "always"
		}

		if cc.Command != "" {
			opts.Cmd = strings.Fields(cc.Command)
		}
		if cc.Hostname != "" {
			opts.Hostname = cc.Hostname
		}
		if cc.Memory != "" {
			mem, err := container.ParseMemoryString(cc.Memory)
			if err == nil {
				opts.MemoryLimit = mem
			}
		}
		if cc.CPUs > 0 {
			opts.CPUCount = cc.CPUs
		}

		for _, p := range cc.Ports {
			proto := "tcp"
			portSpec := p
			if parts := strings.SplitN(p, "/", 2); len(parts) == 2 {
				proto = parts[1]
				portSpec = parts[0]
			}
			parts := strings.SplitN(portSpec, ":", 2)
			if len(parts) == 2 {
				var host, cont int
				fmt.Sscanf(parts[0], "%d", &host)
				fmt.Sscanf(parts[1], "%d", &cont)
				if host > 0 && cont > 0 {
					opts.Ports = append(opts.Ports, container.PortMap{
						HostPort:      host,
						ContainerPort: cont,
						Protocol:      proto,
					})
				}
			}
		}

		for _, v := range cc.Volumes {
			parts := strings.SplitN(v, ":", 2)
			if len(parts) == 2 {
				opts.Volumes = append(opts.Volumes, container.VolumeMount{
					Source: parts[0],
					Target: parts[1],
				})
			}
		}

		for k, v := range cc.Env {
			opts.Env = append(opts.Env, k+"="+v)
		}
		if cc.EnvFile != "" {
			fileEnv, err := container.ParseEnvFile(cc.EnvFile)
			if err != nil {
				fmt.Fprintf(os.Stderr, "  %s: error reading env_file %s: %v\n", name, cc.EnvFile, err)
				continue
			}
			opts.Env = append(opts.Env, fileEnv...)
		}

		if cc.Healthcheck != nil {
			opts.Healthcheck = &container.HealthcheckConfig{
				Cmd:      cc.Healthcheck.Cmd,
				Interval: cc.Healthcheck.Interval,
				Retries:  cc.Healthcheck.Retries,
				Timeout:  cc.Healthcheck.Timeout,
			}
		}

		c := container.New(img, opts)
		if err := c.Save(); err != nil {
			fmt.Fprintf(os.Stderr, "  %s: error saving: %v\n", name, err)
			continue
		}
		if err := c.Start(); err != nil {
			fmt.Fprintf(os.Stderr, "  %s: error starting: %v\n", name, err)
			continue
		}
		fmt.Printf("  %s: created and started (%s)\n", name, c.ID[:12])
		started++
	}

	fmt.Printf("Up complete: %d containers started\n", started)
}
