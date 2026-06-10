package container

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

const (
	cgroupRoot  = "/sys/fs/cgroup"
	dckCgroup   = "dck"
	cpuPeriod   = 100000
)

func cgroupV2Enabled() bool {
	if runtime.GOOS != "linux" {
		return false
	}
	_, err := os.Stat(filepath.Join(cgroupRoot, "cgroup.controllers"))
	return err == nil
}

func enableCgroupController(ctrl string) error {
	controllersPath := filepath.Join(cgroupRoot, "cgroup.controllers")
	data, err := os.ReadFile(controllersPath)
	if err != nil {
		return err
	}
	if !strings.Contains(string(data), ctrl) {
		return fmt.Errorf("controller %s not available on this system", ctrl)
	}

	subPath := filepath.Join(cgroupRoot, "cgroup.subtree_control")
	data, err = os.ReadFile(subPath)
	if err != nil {
		return err
	}
	if !strings.Contains(string(data), ctrl) {
		if err := os.WriteFile(subPath, []byte("+"+ctrl+"\n"), 0644); err != nil {
			return fmt.Errorf("enable %s controller: %w", ctrl, err)
		}
	}
	return nil
}

func ParseMemoryString(s string) (int64, error) {
	if s == "" {
		return 0, nil
	}
	s = strings.ToUpper(s)
	var mult int64 = 1
	switch {
	case strings.HasSuffix(s, "T"):
		mult = 1024 * 1024 * 1024 * 1024
		s = strings.TrimSuffix(s, "T")
	case strings.HasSuffix(s, "G"):
		mult = 1024 * 1024 * 1024
		s = strings.TrimSuffix(s, "G")
	case strings.HasSuffix(s, "M"):
		mult = 1024 * 1024
		s = strings.TrimSuffix(s, "M")
	case strings.HasSuffix(s, "K"):
		mult = 1024
		s = strings.TrimSuffix(s, "K")
	}
	val, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("invalid memory value: %s", s)
	}
	return val * mult, nil
}

func setupContainerCgroup(id string, pid int, memoryLimit int64, cpuCount float64) (string, error) {
	basePath := filepath.Join(cgroupRoot, dckCgroup)
	if err := os.MkdirAll(basePath, 0755); err != nil {
		return "", fmt.Errorf("cgroup base: %w", err)
	}

	cPath := filepath.Join(basePath, id)
	if err := os.MkdirAll(cPath, 0755); err != nil {
		return "", fmt.Errorf("cgroup dir: %w", err)
	}

	// Enable controllers if available (best effort — container runs either way)
	if cgroupV2Enabled() {
		if memoryLimit > 0 {
			enableCgroupController("memory")
		}
		if cpuCount > 0 {
			enableCgroupController("cpu")
		}
	}

	if memoryLimit > 0 {
		val := strconv.FormatInt(memoryLimit, 10)
		os.WriteFile(filepath.Join(cPath, "memory.max"), []byte(val), 0644)
	}

	if cpuCount > 0 {
		quota := int64(cpuCount * float64(cpuPeriod))
		val := fmt.Sprintf("%d %d", quota, cpuPeriod)
		os.WriteFile(filepath.Join(cPath, "cpu.max"), []byte(val), 0644)
	}

	pidStr := strconv.Itoa(pid)
	os.WriteFile(filepath.Join(cPath, "cgroup.procs"), []byte(pidStr), 0644)

	return cPath, nil
}

func cleanupContainerCgroup(id, cgroupPath string) {
	if cgroupPath == "" {
		return
	}
	if b, err := os.ReadFile(filepath.Join(cgroupPath, "cgroup.procs")); err == nil && len(b) > 0 {
		parentProcs := filepath.Join(filepath.Dir(cgroupPath), "cgroup.procs")
		os.WriteFile(parentProcs, b, 0644)
	}
	os.RemoveAll(cgroupPath)
}
