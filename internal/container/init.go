package container

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"

	"dck/internal/state"
)

func resolveShebang(cmdPath string) string {
	f, err := os.Open(cmdPath)
	if err != nil {
		return cmdPath
	}
	defer f.Close()

	br := bufio.NewReader(f)
	line, _, err := br.ReadLine()
	if err != nil {
		return cmdPath
	}

	lineStr := strings.TrimSpace(string(line))
	if !strings.HasPrefix(lineStr, "#!") {
		return cmdPath
	}

	parts := strings.Fields(lineStr[2:])
	if len(parts) == 0 {
		return cmdPath
	}

	interpreter := parts[0]
	if interpreter != "" && interpreter != "/usr/bin/env" {
		if _, err := os.Stat(interpreter); os.IsNotExist(err) {
			if resolved, err := exec.LookPath(filepath.Base(interpreter)); err == nil {
				return resolved
			}
		}
	}
	return interpreter
}

func InitContainer(id string) error {
	if runtime.GOOS != "linux" {
		return fmt.Errorf("container init only supported on Linux")
	}

	c, err := Load(id)
	if err != nil {
		return err
	}

	_, _, merged := c.OverlayDirs()

	if err := syscall.Sethostname([]byte(c.Hostname)); err != nil {
		return fmt.Errorf("sethostname: %w", err)
	}

	if err := syscall.Chroot(merged); err != nil {
		return fmt.Errorf("chroot: %w", err)
	}
	if err := syscall.Chdir("/"); err != nil {
		return fmt.Errorf("chdir: %w", err)
	}

	os.MkdirAll("/proc", 0755)
	os.MkdirAll("/dev", 0755)
	os.MkdirAll("/sys", 0755)
	os.MkdirAll("/dev/pts", 0755)

	syscall.Mount("proc", "/proc", "proc", 0, "")
	syscall.Mount("devtmpfs", "/dev", "devtmpfs", 0, "")
	syscall.Mount("sysfs", "/sys", "sysfs", 0, "")
	syscall.Mount("devpts", "/dev/pts", "devpts", 0, "")

	exec.Command("ip", "link", "set", "lo", "up").Run()

	cfgData, err := os.ReadFile(state.ImageDir(c.ImageName, c.ImageTag) + "/config.json")
	if err == nil {
		var cfg struct {
			Config struct {
				Env        []string `json:"Env"`
				WorkingDir string   `json:"WorkingDir"`
			} `json:"config"`
		}
		if json.Unmarshal(cfgData, &cfg) == nil {
			c.Env = append(cfg.Config.Env, c.Env...)
			if cfg.Config.WorkingDir != "" {
				os.MkdirAll(cfg.Config.WorkingDir, 0755)
				syscall.Chdir(cfg.Config.WorkingDir)
			}
		}
	}

	env := append(c.Env,
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
		"HOME=/root",
		"TERM=xterm",
	)

	cmdPath := c.Cmd[0]
	cmdArgs := c.Cmd

	if _, err := os.Stat(cmdPath); os.IsNotExist(err) {
		os.Setenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
		if resolved, err := exec.LookPath(cmdPath); err == nil {
			cmdPath = resolved
			cmdArgs = []string{cmdPath}
		}
	}

	// If file exists but shebang interpreter is missing (e.g. /bin/bash in usrmerge images),
	// resolve interpreter via PATH
	if _, err := os.Stat(cmdPath); err == nil {
		if interpreter := resolveShebang(cmdPath); interpreter != cmdPath && interpreter != "" {
			cmdArgs = append([]string{interpreter, cmdPath}, cmdArgs[1:]...)
			cmdPath = interpreter
		}
	}

	return syscall.Exec(cmdPath, cmdArgs, env)
}
