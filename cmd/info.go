package cmd

import (
	"fmt"
	"runtime"

	"dck/internal/container"
	"dck/internal/image"
	"dck/internal/state"
)

func Info(args []string) {
	containers, _ := container.List(true)
	var running, stopped int
	for _, c := range containers {
		if c.Status == container.Running {
			running++
		} else {
			stopped++
		}
	}

	images, _ := image.ListImages()

	dataDir := state.DataDir()
	fmt.Printf("%-20s %s\n", "Data directory:", dataDir)
	fmt.Printf("%-20s %d\n", "Running containers:", running)
	fmt.Printf("%-20s %d\n", "Stopped containers:", stopped)
	fmt.Printf("%-20s %d\n", "Images:", len(images))
	fmt.Printf("%-20s %s\n", "OS:", runtime.GOOS)
	fmt.Printf("%-20s %s\n", "Architecture:", runtime.GOARCH)
	fmt.Printf("%-20s %s\n", "Version:", version)
}
