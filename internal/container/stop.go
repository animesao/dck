package container

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"

	"dck/internal/state"
)

func findUnsharePID(childPID int) int {
	out, err := exec.Command("ps", "-o", "ppid=", "-p", strconv.Itoa(childPID)).Output()
	if err != nil {
		return 0
	}
	ppid, err := strconv.Atoi(strings.TrimSpace(string(out)))
	if err != nil || ppid == 0 {
		return 0
	}
	out2, err := exec.Command("ps", "-o", "comm=", "-p", strconv.Itoa(ppid)).Output()
	if err != nil {
		return 0
	}
	if strings.TrimSpace(string(out2)) == "unshare" {
		return ppid
	}
	return 0
}

func (c *Container) Stop() error {
	if c.Status != Running {
		return fmt.Errorf("container %s is not running", c.ID)
	}

	c.mu.Lock()
	if c.cleanupStarted {
		c.mu.Unlock()
		return nil
	}
	c.cleanupStarted = true
	c.mu.Unlock()

	unsharePID := findUnsharePID(c.PID)
	targetPID := c.PID
	if unsharePID != 0 {
		targetPID = unsharePID
	}

	c.StoppedByUser = true
	c.Save()

	// Kill the target (unshare parent). If unshare was started by a
	// previous dck run -d process, --kill-child won't fire on SIGKILL
	// so we must also SIGKILL the container init directly.
	//
	// If target is the container init itself (unshare already dead),
	// SIGKILL is the only signal that works cross-namespace for PID 1.
	//
	// We can't use proc.Wait() — process was reparented to init, so
	// Wait() would return ECHILD. Poll with kill(pid, 0) instead.
	syscall.Kill(targetPID, syscall.SIGKILL)
	waitForExit(targetPID, 5*time.Second)

	// Kill the container init directly (survives if unshare was killed)
	if unsharePID != 0 && c.PID > 0 {
		syscall.Kill(c.PID, syscall.SIGKILL)
		waitForExit(c.PID, 3*time.Second)
	}

	c.killConsoleServe()
	c.cancelHealthcheck()
	c.cleanupNetwork()
	os.Remove(state.ConsolePath(c.ID))
	_, _, merged := c.OverlayDirs()
	unmountOverlay(merged)
	cleanupContainerCgroup(c.ID, c.CgroupPath)
	c.PID = 0
	c.Status = Stopped
	c.Save()
	return nil
}

func (c *Container) killConsoleServe() {
	if c.ConsoleServePID > 0 {
		syscall.Kill(c.ConsoleServePID, syscall.SIGKILL)
		c.ConsoleServePID = 0
	}
}

func (c *Container) cancelHealthcheck() {
	if c.cancelHealth != nil {
		c.cancelHealth()
		c.cancelHealth = nil
	}
}

func isAlive(pid int) bool {
	return syscall.Kill(pid, 0) == nil
}

func waitForExit(pid int, timeout time.Duration) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if !isAlive(pid) {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
}
