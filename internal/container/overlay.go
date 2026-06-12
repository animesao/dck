package container

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"
)

func ensureOverlayModule() {
	exec.Command("modprobe", "overlay").Run()
}

func prepareWorkdir(work string) error {
	os.RemoveAll(work)
	return os.MkdirAll(work, 0755)
}

func tryMountOverlay(lower, upper, work, merged string, extraOpts string) error {
	opts := fmt.Sprintf("lowerdir=%s,upperdir=%s,workdir=%s", lower, upper, work)
	if extraOpts != "" {
		opts = opts + "," + extraOpts
	}
	var stderr bytes.Buffer
	cmd := exec.Command("mount", "-t", "overlay", "overlay",
		"-o", opts, merged)
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("mount overlay: %w (stderr: %s)", err, strings.TrimSpace(stderr.String()))
	}
	return nil
}

func mountOverlay(lower, upper, work, merged string) error {
	if runtime.GOOS != "linux" {
		return nil
	}

	ensureOverlayModule()

	if err := prepareWorkdir(work); err != nil {
		return fmt.Errorf("prepare workdir: %w", err)
	}

	err := tryMountOverlay(lower, upper, work, merged, "")
	if err != nil {
		// Try with common compatibility options
		err = tryMountOverlay(lower, upper, work, merged, "redirect_dir=off,userxattr")
	}
	return err
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
