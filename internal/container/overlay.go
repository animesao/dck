package container

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
)

func mountOverlay(lower, upper, work, merged string) error {
	if runtime.GOOS != "linux" {
		return nil
	}

	if err := exec.Command("mount", "-t", "overlay", "overlay",
		"-o", fmt.Sprintf("lowerdir=%s,upperdir=%s,workdir=%s", lower, upper, work),
		merged,
	).Run(); err != nil {
		return fmt.Errorf("mount overlay: %w", err)
	}
	return nil
}

func unmountOverlay(merged string) {
	if runtime.GOOS != "linux" {
		return
	}
	if _, err := os.Stat(merged); err == nil {
		exec.Command("umount", "-l", merged).Run()
		os.RemoveAll(merged)
	}
}
