package cmd

import (
	"fmt"
	"os"

	"dck/internal/image"
)

func Pull(args []string) {
	if len(args) < 1 {
		fmt.Println("Usage: dck pull <image>[:<tag>]")
		os.Exit(1)
	}

	ref := args[0]
	_, err := image.Pull(ref)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
