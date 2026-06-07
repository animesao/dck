package container

import (
	"fmt"
	"os"
	"syscall"
	"time"
)

func (c *Container) Stop() error {
	if c.Status != Running {
		return fmt.Errorf("container %s is not running", c.ID)
	}

	proc, err := os.FindProcess(c.PID)
	if err != nil {
		c.cleanupNetwork()
		c.PID = 0
		c.Status = Stopped
		c.Save()
		return nil
	}

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

	c.cleanupNetwork()
	c.PID = 0
	c.Status = Stopped
	c.Save()
	return nil
}
