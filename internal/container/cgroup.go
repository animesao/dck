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
	if !cgroupV2Enabled() {
		return "", nil
	}

	basePath := filepath.Join(cgroupRoot, dckCgroup)
	if err := os.MkdirAll(basePath, 0755); err != nil {
		return "", fmt.Errorf("cgroup base: %w", err)
	}

	if memoryLimit > 0 {
		if err := enableCgroupController("memory"); err != nil {
			return "", fmt.Errorf("memory controller: %w", err)
		}
	}
	if cpuCount > 0 {
		if err := enableCgroupController("cpu"); err != nil {
			return "", fmt.Errorf("cpu controller: %w", err)
		}
	}

	cPath := filepath.Join(basePath, id)
	if err := os.MkdirAll(cPath, 0755); err != nil {
		return "", fmt.Errorf("cgroup dir: %w", err)
	}

	if memoryLimit > 0 {
		val := strconv.FormatInt(memoryLimit, 10)
		if err := os.WriteFile(filepath.Join(cPath, "memory.max"), []byte(val), 0644); err != nil {
			os.RemoveAll(cPath)
			return "", fmt.Errorf("memory.max: %w", err)
		}
	}

	if cpuCount > 0 {
		quota := int64(cpuCount * float64(cpuPeriod))
		val := fmt.Sprintf("%d %d", quota, cpuPeriod)
		if err := os.WriteFile(filepath.Join(cPath, "cpu.max"), []byte(val), 0644); err != nil {
			os.RemoveAll(cPath)
			return "", fmt.Errorf("cpu.max: %w", err)
		}
	}

	pidStr := strconv.Itoa(pid)
	if err := os.WriteFile(filepath.Join(cPath, "cgroup.procs"), []byte(pidStr), 0644); err != nil {
		os.RemoveAll(cPath)
		return "", fmt.Errorf("cgroup.procs: %w", err)
	}

	return cPath, nil
}

func cleanupContainerCgroup(id, cgroupPath string) {
	if !cgroupV2Enabled() || cgroupPath == "" {
		return
	}
	procsFile := filepath.Join(cgroupPath, "cgroup.procs")
	procs, err := os.ReadFile(procsFile)
	if err == nil && len(procs) > 0 {
		parentProcs := filepath.Join(filepath.Dir(cgroupPath), "cgroup.procs")
		os.WriteFile(parentProcs, procs, 0644)
	}
	os.RemoveAll(cgroupPath)
}
