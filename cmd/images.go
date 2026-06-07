package cmd

import (
	"fmt"
	"os"

	"dck/internal/image"
)

func Images(args []string) {
	images, err := image.ListImages()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if len(images) == 0 {
		fmt.Println("No images found")
		return
	}

	fmt.Println("REPOSITORY\tTAG")
	for _, img := range images {
		fmt.Printf("%s\t%s\n", img.Name, img.Tag)
	}
}

func Rmi(args []string) {
	if len(args) < 1 {
		fmt.Println("Usage: dck rmi <image>[:<tag>]")
		os.Exit(1)
	}

	name, tag := "library/"+args[0], "latest"
	if i := stringsLastIndex(args[0], ":"); i > 0 {
		tag = args[0][i+1:]
		name = args[0][:i]
		if !stringsContains(name, "/") {
			name = "library/" + name
		}
	}

	if err := image.RemoveImage(name, tag); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Removed:", args[0])
}

func stringsLastIndex(s, substr string) int {
	for i := len(s) - 1; i >= 0; i-- {
		if i+len(substr) <= len(s) && s[i:i+len(substr)] == substr {
			return i
		}
	}
	return -1
}

func stringsContains(s, substr string) bool {
	return stringsLastIndex(s, substr) >= 0
}
