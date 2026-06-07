package cmd

import (
	"fmt"
	"os"

	"dck/internal/container"
)

func Bootstrap(args []string) {
	all, err := container.List(true)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error listing containers: %v\n", err)
		os.Exit(1)
	}

	count := 0
	for _, c := range all {
		if c.Restart != "always" {
			continue
		}
		if c.Status == container.Running {
			fmt.Printf("  %s (%s) already running\n", c.ID[:12], c.Name)
			continue
		}
		fmt.Printf("  Starting %s (%s)... ", c.ID[:12], c.Name)
		if err := c.Start(); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			continue
		}

		fmt.Println("OK")
		count++
	}

	fmt.Printf("Bootstrap complete: %d containers started\n", count)
}
