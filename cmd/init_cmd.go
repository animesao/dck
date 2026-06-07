package cmd

import (
	"fmt"
	"os"

	"dck/internal/container"
)

func initContainer(args []string) {
	if len(args) < 1 {
		fmt.Fprintf(os.Stderr, "Usage: dck init <container-id>\n")
		os.Exit(1)
	}

	if err := container.InitContainer(args[0]); err != nil {
		fmt.Fprintf(os.Stderr, "Init error: %v\n", err)
		os.Exit(1)
	}
}
