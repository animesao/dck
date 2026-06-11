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

	proc, err := os.FindProcess(targetPID)
	if err != nil {
		c.killConsoleServe()
		c.cancelHealthcheck()
		c.cleanupNetwork()
		_, _, merged := c.OverlayDirs()
		unmountOverlay(merged)
		cleanupContainerCgroup(c.ID, c.CgroupPath)
		c.PID = 0
		c.Status = Stopped
		c.Save()
		return nil
	}

	c.StoppedByUser = true
	c.Save()

	proc.Signal(syscall.SIGTERM)

	done := make(chan bool, 1)
	go func() {
		proc.Wait()
		done <- true
	}()

	select {
	case <-done:
	case <-time.After(10 * time.Second):
		proc.Kill()
		<-done
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
		if proc, err := os.FindProcess(c.ConsoleServePID); err == nil {
			proc.Kill()
		}
		c.ConsoleServePID = 0
	}
}

func (c *Container) cancelHealthcheck() {
	if c.cancelHealth != nil {
		c.cancelHealth()
		c.cancelHealth = nil
	}
}
