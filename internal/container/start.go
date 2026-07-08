package container

import (
	"context"
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

func commandContext30(name string, arg ...string) *exec.Cmd {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	cmd := exec.CommandContext(ctx, name, arg...)
	go func() {
		<-ctx.Done()
		cancel()
	}()
	return cmd
}

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
	os.MkdirAll(filepath.Dir(upper), 0755)

	if err := SetupDiskLimit(state.OverlayDir(), c.ID, c.DiskLimit); err != nil {
		return fmt.Errorf("disk limit: %w", err)
	}

	// When disk limit is set, upper and work live inside the mounted data dir
	dataMnt := filepath.Join(state.OverlayDir(), c.ID, "data")
	if isMounted(dataMnt) {
		upper = filepath.Join(dataMnt, "upper")
		work = filepath.Join(dataMnt, "work")
	}

	if _, err := os.Stat(merged); os.IsNotExist(err) || !isOverlayMounted(merged) {
		if err := SetupOverlay(rootfsDir, upper, work, merged); err != nil {
			return fmt.Errorf("overlay: %w", err)
		}
	}

	for _, vol := range c.Volumes {
		spec := ParseVolumeString(vol.Source + ":" + vol.Target)
		if err := MountVolume(spec, merged); err != nil {
			return fmt.Errorf("mount volume %s -> %s: %w", vol.Source, vol.Target, err)
		}
	}

	// Inject secrets/configs into rootfs
	if err := c.InjectSecrets(merged); err != nil {
		return fmt.Errorf("inject secrets: %w", err)
	}

	binPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("executable: %w", err)
	}

	unshareArgs := []string{
		"--fork", "--pid", "--mount", "--uts", "--ipc", "--kill-child",
		binPath, "init", c.ID, merged,
	}

	// Only create a new network namespace for bridge/none modes.
	// host mode shares the host's network namespace (needed for VPN containers).
	if c.NetworkMode != "host" {
		unshareArgs = append([]string{"--net"}, unshareArgs...)
	}

	cmd := exec.Command("unshare", unshareArgs...)

	if c.Detach {
		stdinR, stdinW, err := os.Pipe()
		if err != nil {
			return fmt.Errorf("stdin pipe: %w", err)
		}
		stdoutR, stdoutW, err := os.Pipe()
		if err != nil {
			stdinR.Close()
			stdinW.Close()
			return fmt.Errorf("stdout pipe: %w", err)
		}

		cmd.Stdin = stdinR
		cmd.Stdout = stdoutW
		cmd.Stderr = stdoutW

		serve := exec.Command(binPath, "console-serve", c.ID)
		serve.ExtraFiles = []*os.File{stdinW, stdoutR}
		serve.Start()
		c.ConsoleServePID = serve.Process.Pid
		stdinW.Close()
		stdoutR.Close()
	} else if c.Interactive || c.TTY {
		cmd.Stdin = os.Stdin
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	} else {
		RotateLogFile(c.LogFile())
		logFile, err := os.OpenFile(c.LogFile(), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err != nil {
			return fmt.Errorf("log: %w", err)
		}
		defer logFile.Close()
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

	// Always create cgroup (for stats), best-effort for limits
	cpath, err := setupContainerCgroup(c.ID, childPID, c.MemoryLimit, c.CPUCount)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Cgroup setup: %v (container will run without resource limits)\n", err)
	} else {
		c.CgroupPath = cpath
	}

	if c.NeedsNetwork() {
		if runtime.GOOS == "linux" {
			if IsRootless() {
				if ip, err := SetupRootlessNetwork(childPID, c.ID); err != nil {
					fmt.Fprintf(os.Stderr, "Rootless network: %v (container will run without network)\n", err)
				} else {
					c.IP = ip
					// Set up port forwarding
					for _, p := range c.Ports {
						if err := RootlessPortForward(p.HostPort, p.ContainerPort, p.Protocol); err != nil {
							fmt.Fprintf(os.Stderr, "  port %d -> %d: %v\n", p.HostPort, p.ContainerPort, err)
						}
					}
				}
			} else {
				if err := setupNetworking(c, childPID); err != nil {
					fmt.Fprintf(os.Stderr, "Network setup: %v (container will run without network)\n", err)
				}
			}
		}
	}

	c.Status = Running
	c.Save()
	EmitEvent(EventStart, c)

	if c.EnableSFTP || c.EnableSSH {
		if err := c.StartSFTPServer(binPath); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: SSH/SFTP: %v\n", err)
		}
	}
	if c.EnableFTP {
		if err := c.StartFTPServer(binPath); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: FTP: %v\n", err)
		}
	}

	if c.Detach {
		ctx, cancel := context.WithCancel(context.Background())
		c.cancelHealth = cancel
		monitorContainer(c, cmd, ctx)
		fmt.Println(c.ID[:12])
		return nil
	}

	err = cmd.Wait()
	c.PID = 0
	c.Status = Stopped
	c.cleanupNetwork()
	c.StopSFTPServer()
	c.StopFTPServer()
	c.Save()

	exitCode := 0
	if exitErr, ok := err.(*exec.ExitError); ok {
		exitCode = exitErr.ExitCode()
	}

	if shouldRestart(c.Restart, exitCode, c.StoppedByUser) {
		return c.restart()
	}

	if c.RemoveOnExit {
		cleanupContainer(c)
	} else {
		_, _, merged := c.OverlayDirs()
		unmountOverlay(merged)
	}

	return err
}

type ignoreErrWriter struct{ w io.Writer }

func (w *ignoreErrWriter) Write(p []byte) (int, error) {
	n, _ := w.w.Write(p)
	return n, nil
}

func newIgnoreErrWriter(w io.Writer) *ignoreErrWriter {
	return &ignoreErrWriter{w: w}
}

func (c *Container) NeedsNetwork() bool {
	if c.NetworkMode == "none" || c.NetworkMode == "host" {
		return false
	}
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
	network.EnsureNetBase()

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

func shouldRestart(policy string, exitCode int, stoppedByUser bool) bool {
	switch policy {
	case "always":
		return true
	case "unless-stopped":
		return !stoppedByUser
	case "on-failure":
		return exitCode != 0
	default:
		return false
	}
}

func (c *Container) restart() error {
	time.Sleep(1 * time.Second)
	c.Status = Created
	return c.Start()
}

func monitorContainer(c *Container, cmd *exec.Cmd, ctx context.Context) {
	if c.Healthcheck != nil {
		go c.runHealthcheck(ctx)
	}

	go func() {
		err := cmd.Wait()
		exitCode := 0
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		}

		c.mu.Lock()
		if c.cleanupStarted {
			c.mu.Unlock()
			return
		}
		c.cleanupStarted = true
		c.mu.Unlock()

		stoppedByUser := c.StoppedByUser
		if !stoppedByUser {
			if _, ok := stoppedContainers.Load(c.ID); ok {
				stoppedByUser = true
			}
		}

		c.PID = 0
		c.Status = Stopped
		c.cleanupNetwork()
		c.StopSFTPServer()
		c.StopFTPServer()
		c.Save()

		if shouldRestart(c.Restart, exitCode, stoppedByUser) {
			go func() {
				time.Sleep(1 * time.Second)
				c.Status = Created
				c.Start()
			}()
		} else if c.RemoveOnExit {
			cleanupContainer(c)
		} else {
			_, _, merged := c.OverlayDirs()
			unmountOverlay(merged)
		}
	}()
}

func (c *Container) runHealthcheck(ctx context.Context) {
	hc := c.Healthcheck
	interval := time.Duration(hc.Interval) * time.Second
	if interval == 0 {
		interval = 30 * time.Second
	}
	retries := hc.Retries
	if retries == 0 {
		retries = 3
	}
	timeout := time.Duration(hc.Timeout) * time.Second
	if timeout == 0 {
		timeout = 10 * time.Second
	}

	failures := 0
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(interval):
		}

		if c.Status != Running {
			return
		}

		err := c.execHealthcheck(hc.Cmd, timeout)
		if err != nil {
			failures++
			if failures >= retries {
				if err := commandContext30("kill", "-9", strconv.Itoa(c.PID)).Run(); err != nil {
					fmt.Fprintf(os.Stderr, "Warning: kill -9 %d: %v\n", c.PID, err)
				}
				return
			}
		} else {
			failures = 0
		}
	}
}

func (c *Container) execHealthcheck(cmd string, timeout time.Duration) error {
	args := []string{
		"-t", strconv.Itoa(c.PID),
		"-m", "-p", "-i", "-n",
		"--",
		"sh", "-c", cmd,
	}

	ecmd := exec.Command("nsenter", args...)

	done := make(chan error, 1)
	go func() {
		done <- ecmd.Run()
	}()

	select {
	case err := <-done:
		return err
	case <-time.After(timeout):
		ecmd.Process.Kill()
		return fmt.Errorf("healthcheck timed out after %v", timeout)
	}
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
	if c.ConsoleServePID > 0 {
		if proc, err := os.FindProcess(c.ConsoleServePID); err == nil {
			proc.Kill()
		}
		c.ConsoleServePID = 0
	}
	if c.cancelHealth != nil {
		c.cancelHealth()
		c.cancelHealth = nil
	}
	c.StopSFTPServer()
	c.StopFTPServer()
	c.cleanupNetwork()
	upper, _, merged := c.OverlayDirs()
	unmountOverlay(merged)
	TeardownDiskLimit(state.OverlayDir(), c.ID)
	os.Remove(state.ConsolePath(c.ID))
	os.RemoveAll(filepath.Dir(upper))
	os.Remove(c.LogFile())
	cleanupContainerCgroup(c.ID, c.CgroupPath)
	c.DeleteState()
}

func isDirEmpty(path string) (bool, error) {
	f, err := os.Open(path)
	if err != nil {
		return false, err
	}
	defer f.Close()
	_, err = f.Readdirnames(1)
	if err == io.EOF {
		return true, nil
	}
	return false, err
}
