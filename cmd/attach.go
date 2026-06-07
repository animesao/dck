package cmd

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"dck/internal/container"
)

func Attach(args []string) {
	if len(args) < 1 {
		fmt.Println("Usage: dck attach <container>")
		os.Exit(1)
	}

	c, err := container.Load(args[0])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if c.Status != container.Running {
		fmt.Fprintf(os.Stderr, "Container %s is not running\n", args[0])
		os.Exit(1)
	}

	sigCh := make(chan os.Signal, 64)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP, syscall.SIGQUIT, syscall.SIGWINCH)

	go func() {
		for sig := range sigCh {
			if proc, err := os.FindProcess(c.PID); err == nil {
				proc.Signal(sig)
			}
		}
	}()

	err = c.ExecOpts(c.Cmd, true)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
