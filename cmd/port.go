package cmd

import (
	"fmt"
	"os"

	"dck/internal/container"
)

func Port(args []string) {
	if len(args) < 1 {
		fmt.Println("Usage: dck port <container>")
		os.Exit(1)
	}

	c, err := container.Load(args[0])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if len(c.Ports) == 0 {
		fmt.Printf("Container %s has no port mappings\n", c.Name)
		return
	}

	for _, p := range c.Ports {
		fmt.Printf("%s -> %d:%d/%s\n", c.Name, p.HostPort, p.ContainerPort, p.Protocol)
	}
}
