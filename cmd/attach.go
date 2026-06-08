package cmd

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"dck/internal/container"
	"dck/internal/state"
)

type sessionInfo struct {
	ContainerID string    `json:"container_id"`
	AttachedAt  time.Time `json:"attached_at"`
	LastCmd     string    `json:"last_cmd,omitempty"`
}

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

func saveSession(c *container.Container, lastCmd string) {
	s := sessionInfo{
		ContainerID: c.ID,
		AttachedAt:  time.Now(),
		LastCmd:     lastCmd,
	}
	state.WriteJSON(state.SessionPath(c.ID), &s)
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

	state.EnsureDirs()

	var prev sessionInfo
	if data, err := os.ReadFile(state.SessionPath(c.ID)); err == nil {
		json.Unmarshal(data, &prev)
	}

	go c.Logs(true)

	fmt.Println("--- attach mode: type commands, Ctrl+C to detach ---")
	if prev.LastCmd != "" {
		fmt.Printf("  Previous session: last command was %q\n", prev.LastCmd)
	}
	if rconPassword != "" {
		fmt.Println("  Built-in RCON — commands sent to Minecraft server")
		fmt.Println("  Prefix with ! for system commands (e.g. !ls)")
	}

	var rcon *container.RCON
	if rconPassword != "" {
		rconAddr := "127.0.0.1:25575"
		if c.IP != "" {
			rconAddr = c.IP + ":25575"
		}
		rcon = container.NewRCON(rconAddr, rconPassword)
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

		if rcon != nil {
			resp, err := rcon.Command(line)
			if err == nil {
				if resp != "" {
					fmt.Println(resp)
				}
				saveSession(c, line)
				continue
			}
			fmt.Fprintf(os.Stderr, "rcon: %v\n", err)
		}

		parts := strings.Fields(line)
		if err := c.ExecOpts(parts, false); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
		}
	}
}
