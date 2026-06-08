package cmd

import (
	"bufio"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"

	"dck/internal/container"
)

func findRCONPassword(c *container.Container) string {
	for _, vol := range c.Volumes {
		propsPath := filepath.Join(vol.Source, "server.properties")
		data, err := os.ReadFile(propsPath)
		if err != nil {
			continue
		}
		for _, line := range strings.Split(string(data), "\n") {
			if strings.HasPrefix(line, "rcon.password=") {
				return strings.TrimSpace(strings.TrimPrefix(line, "rcon.password="))
			}
		}
	}
	return ""
}

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

	rconPassword := findRCONPassword(c)

	sigCh := make(chan os.Signal, 64)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP, syscall.SIGQUIT, syscall.SIGWINCH)

	go func() {
		for sig := range sigCh {
			if proc, err := os.FindProcess(c.PID); err == nil {
				proc.Signal(sig)
			}
		}
	}()

	go c.Logs(true)

	fmt.Println("--- attach mode: type commands, Ctrl+C to detach ---")
	if rconPassword != "" {
		fmt.Println("  RCON detected — commands sent to Minecraft server")
		fmt.Println("  Prefix with ! for system commands (e.g. !ls)")
	}

	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		if line == "exit" || line == "quit" {
			break
		}

		if strings.HasPrefix(line, "!") {
			parts := strings.Fields(line[1:])
			if len(parts) > 0 {
				if err := c.ExecOpts(parts, false); err != nil {
					fmt.Fprintf(os.Stderr, "error: %v\n", err)
				}
			}
			continue
		}

		if rconPassword != "" {
			parts := strings.Fields(line)
			rconArgs := append([]string{
				"rcon-cli", "--host", "localhost", "--port", "25575",
				"--password", rconPassword,
			}, parts...)
			if err := c.ExecOpts(rconArgs, false); err == nil {
				continue
			}
		}

		parts := strings.Fields(line)
		if err := c.ExecOpts(parts, false); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
		}
	}
}
