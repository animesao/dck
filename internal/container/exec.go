package container

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
)

func (c *Container) Exec(cmd []string) error {
	return c.ExecOpts(cmd, true, false)
}

func (c *Container) ExecOpts(cmd []string, interactive, tty bool) error {
	if c.Status != Running {
		return fmt.Errorf("container %s is not running", c.ID)
	}

	upper, _, merged := c.OverlayDirs()
	_ = upper

	args := []string{
		"-t", strconv.Itoa(c.PID),
		"-m", "-p", "-i", "-n",
		"--",
	}
	args = append(args, "chroot", merged)
	args = append(args, cmd...)

	ecmd := exec.Command("nsenter", args...)

	if interactive {
		ecmd.Stdin = os.Stdin
		ecmd.Stdout = os.Stdout
		ecmd.Stderr = os.Stderr
	} else {
		ecmd.Stdin = nil
		ecmd.Stdout = os.Stdout
		ecmd.Stderr = os.Stderr
	}

	_ = tty

	return ecmd.Run()
}
