package cmd

import (
	"flag"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"syscall"

	"dck/internal/container"
)

func Sftp(args []string) {
	fs := flag.NewFlagSet("sftp", flag.ExitOnError)
	start := fs.Bool("start", false, "Start SFTP server and print connection info")
	stop := fs.Bool("stop", false, "Stop SFTP server")
	port := fs.Int("p", 0, "Port to listen on (default: auto)")
	fs.Parse(args)

	remaining := fs.Args()

	if *stop {
		if len(remaining) < 1 {
			fmt.Println("Usage: dck sftp --stop <container>")
			os.Exit(1)
		}
		c, err := container.Load(remaining[0])
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		c.StopSFTPServer()
		fmt.Printf("SFTP server stopped for container %s\n", c.ID[:12])
		return
	}

	if len(remaining) < 1 {
		fmt.Println("Usage: dck sftp [--start|--stop] <container>")
		os.Exit(1)
	}

	c, err := container.Load(remaining[0])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	if c.Status != container.Running {
		fmt.Fprintf(os.Stderr, "Container %s is not running\n", remaining[0])
		os.Exit(1)
	}

	if c.SFTPPort > 0 && !*start {
		user := c.SFTPUser
		if user == "" {
			user = "dck"
		}
		fmt.Printf("SFTP running for container %s (%s)\n", c.Name, c.ID[:12])
		fmt.Printf("  Connect: sftp://%s@host:%d\n", user, c.SFTPPort)
		fmt.Printf("  Password: %s\n", c.SFTPPass())
		return
	}

	// Start SFTP server process
	binPath, err := os.Executable()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if *port == 0 {
		used := make(map[int]bool)
		all, _ := container.List(true)
		for _, cont := range all {
			if cont.SFTPPort > 0 && cont.ID != c.ID {
				used[cont.SFTPPort] = true
			}
		}
		p := 22000
		for used[p] {
			p++
		}
		*port = p
	}

	password := c.SFTPPass()
	rootfs := ""
	_, _, merged := c.OverlayDirs()
	if _, err := os.Stat(merged); err == nil {
		rootfs = merged
	}

	user := c.SFTPUser
	if user == "" {
		user = "dck"
	}

	cmd := exec.Command(binPath, "sftp-serve",
		"--root", rootfs,
		"--port", strconv.Itoa(*port),
		"--user", user,
		"--password", password,
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	c.SFTPPort = *port
	c.SFTPServerPID = cmd.Process.Pid
	c.Save()

	fmt.Printf("SFTP server started for container %s\n", c.Name)
	fmt.Printf("  Connect: sftp://%s@host:%d\n", user, *port)
	fmt.Printf("  Password: %s\n", password)
	fmt.Println("  Press Ctrl+C to stop server")

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	cmd.Process.Signal(syscall.SIGTERM)
	cmd.Wait()

	c.SFTPPort = 0
	c.SFTPServerPID = 0
	c.Save()
	fmt.Println("SFTP server stopped")
}
