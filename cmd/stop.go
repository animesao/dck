package cmd

import (
	"fmt"
	"os"

	"dck/internal/container"
)

func Stop(args []string) {
	if len(args) < 1 {
		fmt.Println("Usage: dck stop <container>")
		os.Exit(1)
	}

	c, err := container.Load(args[0])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if err := c.Stop(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Println(c.ID[:12])
}
