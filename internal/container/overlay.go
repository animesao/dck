package container

import (
	"os"
	"runtime"
	"strings"

	"dck/internal/overlayutil"
)

func mountOverlay(lower, upper, work, merged string) error {
	if runtime.GOOS != "linux" {
		return nil
	}

	if IsRootless() {
		return MountRootlessOverlay(lower, upper, work, merged)
	}

	if err := overlayutil.MountOverlay(lower, upper, work, merged); err != nil {
		return err
	}

	return nil
}

func unmountOverlay(merged string) {
	overlayutil.UnmountOverlay(merged)
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
