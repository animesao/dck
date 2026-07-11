package cmd

import (
	"fmt"
	"os"
	"strings"
	"time"

	"dck/internal/container"
)

func Inspect(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: dck inspect <container>")
		os.Exit(1)
	}

	c, err := container.Load(args[0])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("  ID:         %s\n", c.ID)
	fmt.Printf("  Name:       %s\n", c.Name)
	fmt.Printf("  Image:      %s:%s\n", c.ImageName, c.ImageTag)
	fmt.Printf("  Status:     %s\n", c.Status)
	fmt.Printf("  PID:        %d\n", c.PID)
	fmt.Printf("  IP:         %s\n", c.IP)
	fmt.Printf("  Hostname:   %s\n", c.Hostname)
	fmt.Printf("  Created:    %s\n", c.CreatedAt.Format(time.RFC1123))
	r := c.Restart
	if r == "" {
		r = "no"
	}
	fmt.Printf("  Restart:    %s\n", r)
	if c.WorkingDir != "" {
		fmt.Printf("  WorkDir:    %s\n", c.WorkingDir)
	}
	if c.Entrypoint != "" {
		fmt.Printf("  Entrypoint: %s\n", c.Entrypoint)
	}
	if c.User != "" {
		fmt.Printf("  User:       %s\n", c.User)
	}
	nm := c.NetworkMode
	if nm == "" {
		nm = "bridge"
	}
	fmt.Printf("  Network:    %s\n", nm)
	if c.CgroupPath != "" {
		fmt.Printf("  Cgroup:     %s\n", c.CgroupPath)
	}
	if c.StartupScript != "" {
		script := c.StartupScript
		if len(script) > 120 {
			script = script[:117] + "..."
		}
		fmt.Printf("  Startup:    %s\n", script)
	}

	fmt.Println()
	fmt.Println("  Resources:")
	showMem := ""
	if c.MemoryLimit > 0 {
		showMem = formatBytes(uint64(c.MemoryLimit))
	} else {
		showMem = "unlimited"
	}
	fmt.Printf("    Memory:     %s\n", showMem)
	fmt.Printf("    CPUs:      %.1f\n", c.CPUCount)
	if c.DiskLimit > 0 {
		fmt.Printf("    Disk:      %s\n", formatBytes(uint64(c.DiskLimit)))
	}

	if len(c.Ports) > 0 {
		fmt.Println()
		fmt.Println("  Ports:")
		for _, p := range c.Ports {
			fmt.Printf("    -p %d:%d/%s\n", p.HostPort, p.ContainerPort, p.Protocol)
		}
	}

	if len(c.Volumes) > 0 {
		fmt.Println()
		fmt.Println("  Volumes:")
		for _, v := range c.Volumes {
			fmt.Printf("    -v %s:%s\n", v.Source, v.Target)
		}
	}

	if len(c.Env) > 0 {
		fmt.Println()
		fmt.Println("  Environment:")
		for _, e := range c.Env {
			if idx := strings.Index(e, "="); idx > 0 {
				key := e[:idx]
				val := e[idx+1:]
				fmt.Printf("    -e %s=%s\n", key, val)
			} else {
				fmt.Printf("    %s\n", e)
			}
		}
	}

	if len(c.Labels) > 0 {
		fmt.Println()
		fmt.Println("  Labels:")
		for k, v := range c.Labels {
			fmt.Printf("    %s=%s\n", k, v)
		}
	}

	if len(c.CapAdd) > 0 {
		fmt.Printf("  CapAdd:     %s\n", strings.Join(c.CapAdd, ", "))
	}
	if len(c.CapDrop) > 0 {
		fmt.Printf("  CapDrop:    %s\n", strings.Join(c.CapDrop, ", "))
	}
	if c.ReadonlyRootfs {
		fmt.Println("  Readonly:   true")
	}
	if c.NoNewPrivileges {
		fmt.Println("  NoNewPrivs: true")
	}
	if len(c.DNS) > 0 {
		fmt.Printf("  DNS:        %s\n", strings.Join(c.DNS, ", "))
	}
	if len(c.Sysctls) > 0 {
		fmt.Println("  Sysctls:")
		for k, v := range c.Sysctls {
			fmt.Printf("    %s=%s\n", k, v)
		}
	}
	if len(c.Ulimits) > 0 {
		fmt.Println("  Ulimits:")
		for _, u := range c.Ulimits {
			fmt.Printf("    %s=%d:%d\n", u.Name, u.Soft, u.Hard)
		}
	}
	if c.Healthcheck != nil {
		fmt.Println("  Healthcheck:")
		fmt.Printf("    Cmd:      %s\n", c.Healthcheck.Cmd)
		fmt.Printf("    Interval: %ds\n", c.Healthcheck.Interval)
		fmt.Printf("    Retries:  %d\n", c.Healthcheck.Retries)
		fmt.Printf("    Timeout:  %ds\n", c.Healthcheck.Timeout)
	}
	if c.RemoveOnExit {
		fmt.Println("  AutoRemove: true")
	}
	if c.Interactive || c.TTY {
		fmt.Printf("  Interactive: %v  TTY: %v\n", c.Interactive, c.TTY)
	}

	if len(c.Cmd) > 0 {
		fmt.Println()
		fmt.Println("  Command:")
		fmt.Printf("    %s\n", strings.Join(c.Cmd, " "))
	}
	fmt.Println()
}

