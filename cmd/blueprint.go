package cmd

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"

	"dck/internal/container"
	"dck/internal/image"
)

type blueprintRegistry struct {
	Version    int                    `json:"version"`
	Description string                `json:"description"`
	BaseURL    string                `json:"base_url"`
	Blueprints map[string]blueprintEntry `json:"blueprints"`
}

type blueprintEntry struct {
	Name        string `json:"name"`
	Category    string `json:"category"`
	Description string `json:"description"`
	Image       string `json:"image"`
	File        string `json:"file"`
}

type templateJSON struct {
	Name        string `json:"name"`
	Category    string `json:"category"`
	Description string `json:"description"`
	Image       string `json:"image"`
	Tag         string `json:"tag"`
	Command     string `json:"command"`
	Env         string `json:"env"`
	Ports       string `json:"ports"`
	Volumes     string `json:"volumes"`
	Memory      string `json:"memory"`
	CPUs        string `json:"cpus"`
	Restart     string `json:"restart"`
}

func Blueprint(args []string) {
	if len(args) < 1 {
		printBlueprintUsage()
		os.Exit(1)
	}

	sub := args[0]
	subArgs := args[1:]

	switch sub {
	case "list", "ls":
		blueprintList()
	case "install", "i":
		blueprintInstall(subArgs)
	case "--help", "-h", "help":
		printBlueprintUsage()
	default:
		fmt.Printf("unknown blueprint subcommand: %s\n", sub)
		printBlueprintUsage()
		os.Exit(1)
	}
}

func printBlueprintUsage() {
	fmt.Println(`Blueprint commands:
  dck blueprint list              List available blueprints from registry
  dck blueprint ls                Alias for list
  dck blueprint install <name>    Install a blueprint (pull image + create container)
  dck blueprint i <name>          Alias for install

Options for install:
  -n, --name <name>               Container name (default: blueprint name)
  -d                              Detach (background, default: true)
  --memory <limit>                Override memory limit
  --cpus <count>                  Override CPU count
  -e, --env KEY=VAL               Override environment variable (can repeat)
  -y, --yes                       Skip interactive prompts`)
}

func blueprintList() {
	reg, err := fetchBlueprintRegistry()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error fetching blueprint registry: %v\n", err)
		os.Exit(1)
	}

	if len(reg.Blueprints) == 0 {
		fmt.Println("No blueprints available.")
		return
	}

	fmt.Println("Available blueprints:")
	fmt.Println()

	// Group by category
	type catEntry struct {
		Name        string
		Image       string
		Description string
	}
	categories := make(map[string][]catEntry)
	catOrder := make([]string, 0)

	for _, bp := range reg.Blueprints {
		if _, ok := categories[bp.Category]; !ok {
			catOrder = append(catOrder, bp.Category)
		}
		categories[bp.Category] = append(categories[bp.Category], catEntry{
			Name:        bp.Name,
			Image:       bp.Image,
			Description: bp.Description,
		})
	}

	for _, cat := range catOrder {
		entries := categories[cat]
		fmt.Printf("  %s:\n", strings.ToUpper(cat))
		for _, e := range entries {
			fmt.Printf("    \033[1m%-20s\033[0m %-30s %s\n", e.Name, e.Image, e.Description)
		}
		fmt.Println()
	}
}

func blueprintInstall(args []string) {
	if len(args) < 1 || args[0] == "" {
		fmt.Println("Usage: dck blueprint install <name> [--name <container-name>]")
		os.Exit(1)
	}

	bpName := args[0]
	containerName := bpName
	detach := true
	memoryOverride := ""
	cpusOverride := 0.0
	noPrompt := false
	var envOverrides []string

	// Parse remaining flags
	for i := 1; i < len(args); i++ {
		switch args[i] {
		case "-n", "--name":
			if i+1 < len(args) {
				i++
				containerName = args[i]
			}
		case "-d":
			detach = true
		case "--memory":
			if i+1 < len(args) {
				i++
				memoryOverride = args[i]
			}
		case "--cpus":
			if i+1 < len(args) {
				i++
				cpusOverride, _ = strconv.ParseFloat(args[i], 64)
			}
		case "-e", "--env":
			if i+1 < len(args) {
				i++
				envOverrides = append(envOverrides, args[i])
			}
		case "-y", "--yes":
			noPrompt = true
		}
	}

	reg, err := fetchBlueprintRegistry()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error fetching blueprint registry: %v\n", err)
		os.Exit(1)
	}

	bp, ok := reg.Blueprints[bpName]
	if !ok {
		fmt.Fprintf(os.Stderr, "Blueprint %q not found in registry\n", bpName)
		fmt.Println("Use 'dck blueprint list' to see available blueprints.")
		os.Exit(1)
	}

	// Fetch the template JSON
	tplURL := fmt.Sprintf("%s/main/%s", blueprintRepoURL, bp.File)
	tplData, err := fetchURL(tplURL)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error fetching blueprint %q: %v\n", bpName, err)
		os.Exit(1)
	}

	var tpl templateJSON
	if err := json.Unmarshal([]byte(tplData), &tpl); err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing blueprint %q: %v\n", bpName, err)
		os.Exit(1)
	}

	fmt.Printf("Installing blueprint: %s\n", bpName)
	fmt.Printf("  Image: %s\n", bp.Image)
	fmt.Printf("  Description: %s\n", bp.Description)

	// Pull image
	imageRef := bp.Image
	img, err := image.Pull(imageRef)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error pulling image %s: %v\n", imageRef, err)
		os.Exit(1)
	}
	fmt.Printf("  Image pulled: %s\n", imageRef)

	// Check if container name already exists
	if existing := container.FindByName(containerName); existing != nil {
		fmt.Fprintf(os.Stderr, "Error: container with name %q already exists (%s)\n", containerName, existing.ID[:12])
		os.Exit(1)
	}

	// Parse command
	var cmd []string
	if tpl.Command != "" {
		cmd = strings.Fields(tpl.Command)
	}

	// Collect used host ports from existing containers
	usedPorts := make(map[int]bool)
	if allContainers, err := container.List(true); err == nil {
		for _, c := range allContainers {
			for _, p := range c.Ports {
				usedPorts[p.HostPort] = true
			}
		}
	}

	// Parse and resolve ports
	type portEntry struct {
		HostPort      int
		ContainerPort int
		Protocol      string
	}
	var portEntries []portEntry
	if tpl.Ports != "" {
		for _, p := range strings.Split(tpl.Ports, ",") {
			p = strings.TrimSpace(p)
			if p == "" {
				continue
			}
			proto := "tcp"
			portSpec := p
			if parts := strings.SplitN(p, "/", 2); len(parts) == 2 {
				proto = parts[1]
				portSpec = parts[0]
			}
			parts := strings.SplitN(portSpec, ":", 2)
			if len(parts) == 2 {
				host, _ := strconv.Atoi(parts[0])
				cont, _ := strconv.Atoi(parts[1])
				if host > 0 && cont > 0 {
					portEntries = append(portEntries, portEntry{
						HostPort:      host,
						ContainerPort: cont,
						Protocol:      proto,
					})
				}
			}
		}
	}

	// Auto-resolve port conflicts and prompt
	for i := range portEntries {
		base := portEntries[i].HostPort
		for usedPorts[portEntries[i].HostPort] {
			portEntries[i].HostPort++
		}
		if portEntries[i].HostPort != base {
			fmt.Printf("  Port %d is in use, using %d instead\n", base, portEntries[i].HostPort)
		}
		usedPorts[portEntries[i].HostPort] = true
	}

	if len(portEntries) > 0 && !noPrompt {
		reader := bufio.NewReader(os.Stdin)
		fmt.Println()
		fmt.Println("  Port mappings (press Enter to keep default):")
		for i := range portEntries {
			prompt := fmt.Sprintf("    %s port (host:%d container:%d): ",
				portEntries[i].Protocol, portEntries[i].HostPort, portEntries[i].ContainerPort)
			fmt.Print(prompt)
			input, _ := reader.ReadString('\n')
			input = strings.TrimSpace(input)
			if input != "" {
				parts := strings.SplitN(input, ":", 2)
				if len(parts) == 2 {
					h, err1 := strconv.Atoi(parts[0])
					c, err2 := strconv.Atoi(parts[1])
					if err1 == nil && err2 == nil && h > 0 && c > 0 {
						// Check if the new host port is free
						for usedPorts[h] {
							h++
						}
						usedPorts[portEntries[i].HostPort] = false
						usedPorts[h] = true
						portEntries[i].HostPort = h
						portEntries[i].ContainerPort = c
					}
				}
			}
		}
		fmt.Println()
	}

	var ports []container.PortMap
	for _, pe := range portEntries {
		ports = append(ports, container.PortMap{
			HostPort:      pe.HostPort,
			ContainerPort: pe.ContainerPort,
			Protocol:      pe.Protocol,
		})
	}

	// Parse volumes
	var volumes []container.VolumeMount
	if tpl.Volumes != "" {
		for _, v := range strings.Split(tpl.Volumes, ",") {
			v = strings.TrimSpace(v)
			if v == "" {
				continue
			}
			parts := strings.SplitN(v, ":", 2)
			if len(parts) == 2 {
				volumes = append(volumes, container.VolumeMount{
					Source: parts[0],
					Target: parts[1],
				})
			}
		}
	}

	// Parse environment variables
	var envPairs []struct {
		Key   string `json:"key"`
		Value string `json:"value"`
	}
	if tpl.Env != "" {
		json.Unmarshal([]byte(tpl.Env), &envPairs)
	}

	// Apply CLI env overrides
	for _, o := range envOverrides {
		parts := strings.SplitN(o, "=", 2)
		if len(parts) == 2 {
			found := false
			for i := range envPairs {
				if envPairs[i].Key == parts[0] {
					envPairs[i].Value = parts[1]
					found = true
					break
				}
			}
			if !found {
				envPairs = append(envPairs, struct {
					Key   string `json:"key"`
					Value string `json:"value"`
				}{parts[0], parts[1]})
			}
		}
	}

	// Interactive env editing
	if len(envPairs) > 0 && !noPrompt {
		reader := bufio.NewReader(os.Stdin)
		fmt.Println()
		fmt.Println("  Environment variables (press Enter to keep default):")
		for i := range envPairs {
			fmt.Printf("    %s [%s]: ", envPairs[i].Key, envPairs[i].Value)
			input, _ := reader.ReadString('\n')
			input = strings.TrimSpace(input)
			if input != "" {
				envPairs[i].Value = input
			}
		}
		fmt.Println()
	}

	var env []string
	for _, p := range envPairs {
		env = append(env, p.Key+"="+p.Value)
	}

	// Memory
	memoryLimit := int64(0)
	memStr := memoryOverride
	if memStr == "" {
		memStr = tpl.Memory
	}
	if memStr != "" {
		memoryLimit, _ = container.ParseMemoryString(memStr)
	}

	// CPUs
	cpus := cpusOverride
	if cpus == 0 && tpl.CPUs != "" {
		cpus, _ = strconv.ParseFloat(tpl.CPUs, 64)
	}

	// Restart policy
	restart := tpl.Restart
	if restart == "" {
		restart = "no"
	}

	opts := container.CreateOpts{
		Name:     containerName,
		Cmd:      cmd,
		Ports:    ports,
		Volumes:  volumes,
		Env:      env,
		Restart:  restart,
		Detach:   detach,
		MemoryLimit: memoryLimit,
		CPUCount: cpus,
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

	fmt.Printf("  Container created: %s (%s)\n", c.Name, c.ID[:12])
	fmt.Println("  Use 'dck ps' to see running containers")
	fmt.Println("  Use 'dck logs "+c.Name+"' to view logs")
}

func fetchBlueprintRegistry() (*blueprintRegistry, error) {
	registryURL := fmt.Sprintf("%s/main/registry.json", blueprintRepoURL)
	data, err := fetchURL(registryURL)
	if err != nil {
		return nil, err
	}

	var reg blueprintRegistry
	if err := json.Unmarshal([]byte(data), &reg); err != nil {
		return nil, fmt.Errorf("parse registry: %w", err)
	}

	return &reg, nil
}
