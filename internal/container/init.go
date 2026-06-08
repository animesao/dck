package container

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"syscall"
	"time"

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

	cfgData, _ := os.ReadFile(state.ImageDir(c.ImageName, c.ImageTag) + "/config.json")

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

	for i := 0; i < 200; i++ {
		out, _ := exec.Command("ip", "addr", "show", "eth0").Output()
		if len(out) > 0 {
			s := string(out)
			if !strings.Contains(s, "NO-CARRIER") && strings.Contains(s, "inet ") {
				exec.Command("ip", "link", "set", "eth0", "up").Run()
				break
			}
		}
		time.Sleep(100 * time.Millisecond)
	}

	ensureUsrMerge()

	os.WriteFile("/etc/resolv.conf", []byte("nameserver 8.8.8.8\nnameserver 8.8.4.4\n"), 0644)

	var cfg struct {
		Config struct {
			Env        []string `json:"Env"`
			WorkingDir string   `json:"WorkingDir"`
		} `json:"config"`
	}
	json.Unmarshal(cfgData, &cfg)

	c.Env = append(cfg.Config.Env, c.Env...)

	if cfg.Config.WorkingDir != "" {
		os.MkdirAll(cfg.Config.WorkingDir, 0755)
		syscall.Chdir(cfg.Config.WorkingDir)
	}

	defaultPath := "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
	hasPath := false
	for _, e := range c.Env {
		if len(e) >= 5 && e[:5] == "PATH=" {
			hasPath = true
			break
		}
	}
	if !hasPath {
		c.Env = append(c.Env, "PATH="+defaultPath)
	}
	hasHome := false
	for _, e := range c.Env {
		if len(e) >= 5 && e[:5] == "HOME=" {
			hasHome = true
			break
		}
	}
	if !hasHome {
		c.Env = append(c.Env, "HOME=/root")
	}
	hasTerm := false
	for _, e := range c.Env {
		if len(e) >= 5 && e[:5] == "TERM=" {
			hasTerm = true
			break
		}
	}
	if !hasTerm {
		c.Env = append(c.Env, "TERM=xterm")
	}

	cmdPath := c.Cmd[0]
	cmdArgs := c.Cmd

	if _, err := os.Stat(cmdPath); os.IsNotExist(err) {
		os.Setenv("PATH", defaultPath)
		if resolved, err := exec.LookPath(cmdPath); err == nil {
			cmdPath = resolved
			cmdArgs = []string{cmdPath}
		}
	}

	return syscall.Exec(cmdPath, cmdArgs, c.Env)
}
