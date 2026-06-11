package container

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
)

func (c *Container) Top() error {
	if c.Status != Running {
		return fmt.Errorf("container %s is not running", c.ID)
	}

	args := []string{
		"-t", strconv.Itoa(c.PID),
		"-p",
		"--",
		"ps", "aux",
	}

	cmd := exec.Command("nsenter", args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return cmd.Run()
}
