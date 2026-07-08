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

func Ftp(args []string) {
	fs := flag.NewFlagSet("ftp", flag.ExitOnError)
	start := fs.Bool("start", false, "Start FTP server and print connection info")
	stop := fs.Bool("stop", false, "Stop FTP server")
	port := fs.Int("p", 0, "Port to listen on (default: auto)")
	fs.Parse(args)

	remaining := fs.Args()

	if *stop {
		if len(remaining) < 1 {
			fmt.Println("Usage: dck ftp --stop <container>")
			os.Exit(1)
		}
		c, err := container.Load(remaining[0])
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		c.StopFTPServer()
		fmt.Printf("FTP server stopped for container %s\n", c.ID[:12])
		return
	}

	if len(remaining) < 1 {
		fmt.Println("Usage: dck ftp [--start|--stop] <container>")
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

	if c.FTPPort > 0 && !*start {
		fmt.Printf("FTP running for container %s\n", c.ID[:12])
		fmt.Printf("  Connect: ftp://dck@host:%d\n", c.FTPPort)
		fmt.Printf("  Password: %s\n", c.SFTPPass())
		return
	}

	binPath, err := os.Executable()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if *port == 0 {
		used := make(map[int]bool)
		all, _ := container.List(true)
		for _, cont := range all {
			if cont.FTPPort > 0 && cont.ID != c.ID {
				used[cont.FTPPort] = true
			}
		}
		p := 23000
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

	cmd := exec.Command(binPath, "ftp-serve",
		"--root", rootfs,
		"--port", strconv.Itoa(*port),
		"--password", password,
	)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	c.FTPPort = *port
	c.FTPServerPID = cmd.Process.Pid
	c.Save()

	fmt.Printf("FTP server started for container %s\n", c.ID[:12])
	fmt.Printf("  Connect: ftp://dck@host:%d\n", *port)
	fmt.Printf("  Password: %s\n", password)
	fmt.Println("  Press Ctrl+C to stop server")

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	cmd.Process.Signal(syscall.SIGTERM)
	cmd.Wait()

	c.FTPPort = 0
	c.FTPServerPID = 0
	c.Save()
	fmt.Println("FTP server stopped")
}
