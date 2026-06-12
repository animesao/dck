package container

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"
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
		// Try normal unmount first so kernel can release dentry/page cache.
		// Fall back to lazy if something still holds references.
		if err := exec.Command("umount", merged).Run(); err != nil {
			exec.Command("umount", "-l", merged).Run()
		}
	}
}

func isMounted(path string) bool {
	if runtime.GOOS != "linux" {
		return false
	}
	data, err := os.ReadFile("/proc/self/mounts")
	if err != nil {
		return false
	}
	return strings.Contains(string(data), " "+path+" ")
}

func isOverlayMounted(merged string) bool {
	if runtime.GOOS != "linux" {
		return false
	}
	data, err := os.ReadFile("/proc/self/mounts")
	if err != nil {
		return false
	}
	return strings.Contains(string(data), " "+merged+" ")
}
