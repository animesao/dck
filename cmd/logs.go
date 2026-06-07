package cmd

import (
	"flag"
	"fmt"
	"os"

	"dck/internal/container"
)

func Logs(args []string) {
	fs := flag.NewFlagSet("logs", flag.ExitOnError)
	follow := fs.Bool("f", false, "Follow log output")
	fs.Parse(args)

	if fs.NArg() < 1 {
		fmt.Println("Usage: dck logs [-f] <container>")
		os.Exit(1)
	}

	c, err := container.Load(fs.Arg(0))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if err := c.Logs(*follow); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
