package container

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"dck/internal/image"
	"dck/internal/network"
	"dck/internal/state"
)

func (c *Container) Start() error {
	if c.Status != Created && c.Status != Stopped {
		return fmt.Errorf("container %s is %s, cannot start", c.ID, c.Status)
	}

	state.EnsureDirs()

	img := image.LoadFromStore(c.ImageName, c.ImageTag)
	if img == nil {
		return fmt.Errorf("image %s:%s not found", c.ImageName, c.ImageTag)
	}

	rootfsDir := state.ImageRootfsDir(c.ImageName, c.ImageTag)
	upper, work, merged := c.OverlayDirs()
	os.RemoveAll(filepath.Dir(upper))
	os.MkdirAll(filepath.Dir(upper), 0755)

	if err := SetupOverlay(rootfsDir, upper, work, merged); err != nil {
		return fmt.Errorf("overlay: %w", err)
	}

	for _, vol := range c.Volumes {
		target := filepath.Join(merged, vol.Target)
		os.MkdirAll(target, 0755)
		os.MkdirAll(vol.Source, 0755)
		if err := exec.Command("mount", "--bind", vol.Source, target).Run(); err != nil {
			return fmt.Errorf("mount volume %s -> %s: %w", vol.Source, vol.Target, err)
		}
	}

	logFile, err := os.Create(c.LogFile())
	if err != nil {
		return fmt.Errorf("log: %w", err)
	}
	defer logFile.Close()

	binPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("executable: %w", err)
	}

	unshareArgs := []string{
		"--fork", "--pid", "--mount", "--net", "--uts", "--ipc",
		binPath, "init", c.ID,
	}

	cmd := exec.Command("unshare", unshareArgs...)
	cmd.Stdout = logFile
	cmd.Stderr = logFile

	if c.Detach {
	} else if c.Interactive || c.TTY {
		cmd.Stdin = os.Stdin
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	} else {
		cmd.Stdout = io.MultiWriter(logFile, os.Stdout)
		cmd.Stderr = io.MultiWriter(logFile, os.Stderr)
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start: %w", err)
	}

	unsharePID := cmd.Process.Pid
	childPID := findChildPID(unsharePID)
	if childPID == 0 {
		childPID = unsharePID + 1
	}

	c.PID = childPID

	if c.NeedsNetwork() {
		if runtime.GOOS == "linux" {
			if err := setupNetworking(c, childPID); err != nil {
				fmt.Fprintf(os.Stderr, "Network setup: %v (container will run without network)\n", err)
			}
		}
	}

	c.Status = Running
	c.Save()

	if c.Detach {
		monitorContainer(c, cmd)
		fmt.Println(c.ID[:12])
		return nil
	}

	err = cmd.Wait()
	c.PID = 0
	c.Status = Stopped
	c.Save()

	exitCode := 0
	if exitErr, ok := err.(*exec.ExitError); ok {
		exitCode = exitErr.ExitCode()
	}

	if c.Restart == "always" || (c.Restart == "on-failure" && exitCode != 0) {
		return c.restart()
	}

	if c.RemoveOnExit {
		cleanupContainer(c)
	}

	return err
}

func (c *Container) NeedsNetwork() bool {
	return true
}

func findChildPID(ppid int) int {
	for i := 0; i < 100; i++ {
		out, err := exec.Command("pgrep", "-P", strconv.Itoa(ppid)).Output()
		if err == nil {
			lines := strings.Split(string(out), "\n")
			for _, line := range lines {
				pidStr := strings.TrimSpace(line)
				if pidStr == "" {
					continue
				}
				pid, err := strconv.Atoi(pidStr)
				if err == nil && pid > 0 {
					return pid
				}
			}
		}
		time.Sleep(10 * time.Millisecond)
	}

	data, err := os.ReadFile("/proc/" + strconv.Itoa(ppid) + "/task/" + strconv.Itoa(ppid) + "/children")
	if err == nil {
		fields := strings.Fields(string(data))
		if len(fields) > 0 {
			if pid, err := strconv.Atoi(fields[0]); err == nil && pid > 0 {
				return pid
			}
		}
	}

	return 0
}

func setupNetworking(c *Container, pid int) error {
	network.EnsureBridge()

	ip, err := network.AllocateIP()
	if err != nil {
		return err
	}

	if err := network.SetupVeth(c.ID, pid, ip); err != nil {
		network.ReleaseIP(ip)
		return err
	}

	for _, p := range c.Ports {
		if err := network.AddPortForwarding(ip, p.HostPort, p.ContainerPort, p.Protocol); err != nil {
			fmt.Fprintf(os.Stderr, "  port %d -> %d: %v\n", p.HostPort, p.ContainerPort, err)
		}
	}

	c.IP = ip
	return nil
}

func (c *Container) restart() error {
	time.Sleep(1 * time.Second)
	c.Status = Created
	return c.Start()
}

func monitorContainer(c *Container, cmd *exec.Cmd) {
	go func() {
		err := cmd.Wait()
		exitCode := 0
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		}

		c.PID = 0
		c.Status = Stopped
		c.cleanupNetwork()
		c.Save()

		shouldRestart := c.Restart == "always" || (c.Restart == "on-failure" && exitCode != 0)
		if shouldRestart {
			go func() {
				time.Sleep(1 * time.Second)
				c.Status = Created
				c.Start()
			}()
		} else if c.RemoveOnExit {
			cleanupContainer(c)
		}
	}()
}

func (c *Container) cleanupNetwork() {
	if c.IP == "" {
		return
	}
	var ports []network.PortRule
	for _, p := range c.Ports {
		ports = append(ports, network.PortRule{
			HostPort:      p.HostPort,
			ContainerPort: p.ContainerPort,
			Protocol:      p.Protocol,
			ContainerIP:   c.IP,
		})
	}
	network.CleanupContainerNetwork(c.ID, c.IP, ports)
	c.IP = ""
}

func cleanupContainer(c *Container) {
	if runtime.GOOS != "linux" {
		return
	}
	c.cleanupNetwork()
	upper, _, merged := c.OverlayDirs()
	exec.Command("umount", "-l", merged).Run()
	os.RemoveAll(filepath.Dir(upper))
	os.Remove(c.LogFile())
	c.DeleteState()
}
