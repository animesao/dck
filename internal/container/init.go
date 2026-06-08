package container

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"syscall"

	"dck/internal/state"
)

func ensureUsrMerge() {
	for _, dir := range []struct{ link, target string }{
		{"/bin", "/usr/bin"},
		{"/sbin", "/usr/sbin"},
		{"/lib", "/usr/lib"},
		{"/lib64", "/usr/lib64"},
	} {
		if _, err := os.Stat(dir.link); os.IsNotExist(err) {
			if _, err := os.Stat(dir.target); err == nil {
				os.Symlink(dir.target, dir.link)
			}
		}
	}
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

	ensureUsrMerge()

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

	return syscall.Exec(cmdPath, cmdArgs, env)
}
