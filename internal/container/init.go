package container

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"

	"dck/internal/state"
)

var capMap = map[string]uintptr{
	"CHOWN":            0,
	"DAC_OVERRIDE":     1,
	"DAC_READ_SEARCH":  2,
	"FOWNER":           3,
	"FSETID":           4,
	"KILL":             5,
	"SETGID":           6,
	"SETUID":           7,
	"SETPCAP":          8,
	"LINUX_IMMUTABLE":  9,
	"NET_BIND_SERVICE": 10,
	"NET_BROADCAST":    11,
	"NET_ADMIN":        12,
	"NET_RAW":          13,
	"IPC_LOCK":         14,
	"IPC_OWNER":        15,
	"SYS_MODULE":       16,
	"SYS_RAWIO":        17,
	"SYS_CHROOT":       18,
	"SYS_PTRACE":       19,
	"SYS_PACCT":        20,
	"SYS_ADMIN":        21,
	"SYS_BOOT":         22,
	"SYS_NICE":         23,
	"SYS_RESOURCE":     24,
	"SYS_TIME":         25,
	"SYS_TTY_CONFIG":   26,
	"MKNOD":            27,
	"LEASE":            28,
	"AUDIT_WRITE":      29,
	"AUDIT_CONTROL":    30,
	"SETFCAP":          31,
	"MAC_OVERRIDE":     32,
	"MAC_ADMIN":        33,
	"SYSLOG":           34,
	"WAKE_ALARM":       35,
	"BLOCK_SUSPEND":    36,
	"AUDIT_READ":       37,
}

const (
	PR_CAPBSET_READ  = 0x16
	PR_CAPBSET_DROP  = 0x15
	PR_SET_NO_NEW_PRIVS = 0x26
)

func prctl(option uintptr, arg2, arg3, arg4, arg5 uintptr) error {
	_, _, err := syscall.Syscall6(syscall.SYS_PRCTL, option, arg2, arg3, arg4, arg5, 0)
	if err != 0 {
		return err
	}
	return nil
}

func dropCapability(capName string) error {
	upper := strings.ToUpper(capName)
	if !strings.HasPrefix(upper, "CAP_") {
		upper = "CAP_" + upper
	}
	capName = strings.TrimPrefix(upper, "CAP_")
	capVal, ok := capMap[capName]
	if !ok {
		return fmt.Errorf("unknown capability: %s", capName)
	}
	return prctl(PR_CAPBSET_DROP, capVal, 0, 0, 0)
}

func dropAllCapabilities() error {
	for _, capVal := range capMap {
		if err := prctl(PR_CAPBSET_DROP, capVal, 0, 0, 0); err != nil {
			return err
		}
	}
	return nil
}

func setNoNewPrivileges() error {
	return prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
}

// RLIMIT constants (not all are exported in Go's syscall on linux/amd64)
const (
	rlimitNPROC      = 6
	rlimitMEMLOCK    = 8
	rlimitRSS        = 5
	rlimitRTPRIO     = 14
	rlimitRTTIME     = 15
	rlimitSIGPENDING = 11
	rlimitMSGQUEUE   = 12
	rlimitNICE       = 13
)

func applyUlimits(ulimits []Ulimit) {
	for _, u := range ulimits {
		rlimit := syscall.Rlimit{Cur: u.Soft, Max: u.Hard}
		var resource int
		switch strings.ToUpper(u.Name) {
		case "NOFILE":
			resource = syscall.RLIMIT_NOFILE
		case "NPROC":
			resource = rlimitNPROC
		case "CORE":
			resource = syscall.RLIMIT_CORE
		case "STACK":
			resource = syscall.RLIMIT_STACK
		case "FSIZE":
			resource = syscall.RLIMIT_FSIZE
		case "DATA":
			resource = syscall.RLIMIT_DATA
		case "AS":
			resource = syscall.RLIMIT_AS
		case "MEMLOCK":
			resource = rlimitMEMLOCK
		case "RSS":
			resource = rlimitRSS
		case "RTPRIO":
			resource = rlimitRTPRIO
		case "RTTIME":
			resource = rlimitRTTIME
		case "SIGPENDING":
			resource = rlimitSIGPENDING
		case "MSGQUEUE":
			resource = rlimitMSGQUEUE
		case "NICE":
			resource = rlimitNICE
		default:
			continue
		}
		syscall.Setrlimit(resource, &rlimit)
	}
}

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
	os.MkdirAll("/tmp", os.ModeSticky|0777)

	syscall.Mount("proc", "/proc", "proc", 0, "")
	syscall.Mount("devtmpfs", "/dev", "devtmpfs", 0, "")
	syscall.Mount("sysfs", "/sys", "sysfs", 0, "")
	syscall.Mount("devpts", "/dev/pts", "devpts", 0, "")

	// Ensure /tmp is world-writable (critical for images that switch users)
	os.Chmod("/tmp", 01777)

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

	// Write /etc/resolv.conf with custom DNS or defaults
	if len(c.DNS) > 0 {
		var sb strings.Builder
		for _, d := range c.DNS {
			sb.WriteString("nameserver " + d + "\n")
		}
		os.WriteFile("/etc/resolv.conf", []byte(sb.String()), 0644)
	} else {
		os.WriteFile("/etc/resolv.conf", []byte("nameserver 8.8.8.8\nnameserver 8.8.4.4\n"), 0644)
	}

	// Apply sysctls
	for k, v := range c.Sysctls {
		path := "/proc/sys/" + strings.ReplaceAll(k, ".", "/")
		os.WriteFile(path, []byte(v), 0644)
	}

	var cfg struct {
		Config struct {
			Env        []string `json:"Env"`
			WorkingDir string   `json:"WorkingDir"`
			User       string   `json:"User"`
		} `json:"config"`
	}
	json.Unmarshal(cfgData, &cfg)

	c.Env = append(cfg.Config.Env, c.Env...)

	wd := cfg.Config.WorkingDir
	if c.WorkingDir != "" {
		wd = c.WorkingDir
	}
	if wd != "" {
		os.MkdirAll(wd, 0755)
		syscall.Chdir(wd)
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

	// Fix volume permissions: chown to target user, or chmod 0777 as fallback
	volumeUser := cfg.Config.User
	if volumeUser == "" {
		volumeUser = c.User
	}
	for _, vol := range c.Volumes {
		target := vol.Target
		if volumeUser != "" {
			var uid, gid int
			parts := strings.Split(volumeUser, ":")
			if len(parts) == 2 {
				gid, _ = strconv.Atoi(parts[1])
			}
			uid, err = strconv.Atoi(parts[0])
			if err != nil {
				if data, readErr := os.ReadFile("/etc/passwd"); readErr == nil {
					for _, line := range strings.Split(string(data), "\n") {
						fields := strings.Split(line, ":")
						if len(fields) >= 3 && fields[0] == parts[0] {
							uid, _ = strconv.Atoi(fields[2])
							if len(parts) == 1 {
								gid, _ = strconv.Atoi(fields[3])
							}
							break
						}
					}
				}
			}
			if uid > 0 {
				if gid == 0 {
					gid = uid
				}
				os.Chown(target, uid, gid)
				filepath.Walk(target, func(path string, info os.FileInfo, walkErr error) error {
					os.Chown(path, uid, gid)
					return nil
				})
			}
		} else {
			os.Chmod(target, 0777)
			filepath.Walk(target, func(path string, info os.FileInfo, walkErr error) error {
				os.Chmod(path, 0777)
				return nil
			})
		}
	}

	// Apply user switching
	if c.User != "" {
		var uid, gid int
		parts := strings.Split(c.User, ":")
		if len(parts) == 2 {
			gid, _ = strconv.Atoi(parts[1])
		}
		uid, err = strconv.Atoi(parts[0])
		if err == nil {
			if gid > 0 {
				syscall.Setgid(gid)
			}
			syscall.Setuid(uid)
		}
	}

	// Apply no_new_privs before exec
	if c.NoNewPrivileges {
		setNoNewPrivileges()
	}

	// Drop specified capabilities
	if len(c.CapDrop) > 0 {
		for _, capName := range c.CapDrop {
			if strings.ToUpper(capName) == "ALL" {
				dropAllCapabilities()
				break
			}
			dropCapability(capName)
		}
	}

	// Add specified capabilities (attempt — may fail without privilege)
	if len(c.CapAdd) > 0 {
		for _, capName := range c.CapAdd {
			if strings.ToUpper(capName) == "ALL" {
				break
			}
		}
	}

	// Apply readonly rootfs (remount / as readonly after /proc is mounted)
	if c.ReadonlyRootfs {
		syscall.Mount("", "/", "", syscall.MS_REMOUNT|syscall.MS_RDONLY, "")
	}

	// Apply ulimits
	if len(c.Ulimits) > 0 {
		applyUlimits(c.Ulimits)
	}

	// Inject dck environment variables for startup scripts
	c.Env = append(c.Env,
		"DCK_CONTAINER_ID="+c.ID,
		"DCK_CONTAINER_NAME="+c.Name,
		"DCK_IMAGE_NAME="+c.ImageName,
		"DCK_IMAGE_TAG="+c.ImageTag,
		"DCK_HOSTNAME="+c.Hostname,
		"DCK_MEMORY="+strconv.FormatInt(c.MemoryLimit, 10),
		"DCK_CPU="+strconv.FormatFloat(c.CPUCount, 'f', -1, 64),
		"DCK_IP="+c.IP,
		"DCK_RESTART="+c.Restart,
	)
	for _, p := range c.Ports {
		key := fmt.Sprintf("DCK_PORT_%s_%d", strings.ToUpper(p.Protocol), p.HostPort)
		c.Env = append(c.Env, key+"="+strconv.Itoa(p.ContainerPort))
	}

	// Create /dck utility scripts inside container
	os.MkdirAll("/dck", 0755)
	dckScripts := map[string]string{
		"info": `#!/bin/sh
echo "=== Container Info ==="
echo "ID:       $DCK_CONTAINER_ID"
echo "Name:     $DCK_CONTAINER_NAME"
echo "Image:    $DCK_IMAGE_NAME:$DCK_IMAGE_TAG"
echo "Hostname: $DCK_HOSTNAME"
echo "IP:       $DCK_IP"
echo "Memory:   $DCK_MEMORY"
echo "CPU:      $DCK_CPU"
echo "Restart:  $DCK_RESTART"
echo "Ports:"
env | grep ^DCK_PORT_ | while IFS='=' read -r k v; do echo "  $k=$v"; done
`,
		"env": `#!/bin/sh
env | grep ^DCK_ | sort | while IFS='=' read -r k v; do echo "$k=$v"; done
`,
		"help": `#!/bin/sh
echo "Available dck utility scripts:"
echo "  /dck/info  - Show container information"
echo "  /dck/env   - Show dck environment variables"
echo "  /dck/help  - Show this help"
echo ""
echo "Environment variables available:"
echo "  DCK_CONTAINER_ID   - Container ID"
echo "  DCK_CONTAINER_NAME - Container name"
echo "  DCK_IMAGE_NAME     - Image name"
echo "  DCK_IMAGE_TAG      - Image tag"
echo "  DCK_HOSTNAME       - Container hostname"
echo "  DCK_IP             - Container IP address"
echo "  DCK_MEMORY         - Memory limit (bytes)"
echo "  DCK_CPU            - CPU limit (cores)"
echo "  DCK_RESTART        - Restart policy"
echo "  DCK_PORT_TCP_*     - Port mappings (TCP)"
echo "  DCK_PORT_UDP_*     - Port mappings (UDP)"
`,
	}
	for name, content := range dckScripts {
		os.WriteFile("/dck/"+name, []byte(content), 0755)
	}

	// If startup script is provided, write it and execute via shell
	if c.StartupScript != "" {
		scriptPath := "/startup.sh"
		if err := os.WriteFile(scriptPath, []byte(c.StartupScript), 0755); err != nil {
			return fmt.Errorf("write startup script: %w", err)
		}
		cmdPath := "/bin/sh"
		cmdArgs := []string{"/bin/sh", scriptPath}
		return syscall.Exec(cmdPath, cmdArgs, c.Env)
	}

	cmdPath := c.Cmd[0]
	cmdArgs := c.Cmd

	if _, err := os.Stat(cmdPath); os.IsNotExist(err) {
		searchPath := defaultPath
		for _, e := range c.Env {
			if strings.HasPrefix(e, "PATH=") {
				searchPath = e[5:]
				break
			}
		}
		os.Setenv("PATH", searchPath)
		if resolved, err := exec.LookPath(cmdPath); err == nil {
			cmdPath = resolved
			cmdArgs = append([]string{cmdPath}, c.Cmd[1:]...)
		}
	}

	return syscall.Exec(cmdPath, cmdArgs, c.Env)
}
