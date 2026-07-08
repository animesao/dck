package container

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"

	"dck/internal/sftp"
	"dck/internal/state"
)

const sftpBasePort = 22000
const sftpPassBasePort = 32000

func allocatePort(existing map[int]bool, base int) int {
	p := base
	for existing[p] {
		p++
	}
	return p
}

func getUsedPorts() map[int]bool {
	all, _ := List(true)
	used := make(map[int]bool)
	for _, c := range all {
		if c.SFTPPort > 0 {
			used[c.SFTPPort] = true
		}
		if c.FTPPort > 0 {
			used[c.FTPPort] = true
		}
		if c.FTPPassiveStart > 0 {
			used[c.FTPPassiveStart] = true
		}
	}
	return used
}

func killPort(port int) {
	addr := fmt.Sprintf(":%d", port)
	ln, err := net.Listen("tcp", addr)
	if err == nil {
		ln.Close()
		return
	}
	exec.Command("fuser", "-k", fmt.Sprintf("%d/tcp", port)).Run()
	time.Sleep(200 * time.Millisecond)
}

func (c *Container) StartSFTPServer(binPath string) error {
	if !c.EnableSFTP {
		return nil
	}

	used := getUsedPorts()
	port := allocatePort(used, sftpBasePort)
	c.SFTPPort = port

	if c.SFTPUser == "" {
		c.SFTPUser = sftp.RandomUser()
	}
	if c.SFTPPassword == "" {
		c.SFTPPassword = sftp.RandomPass()
	}

	killPort(port)

	merged := filepath.Join(state.OverlayDir(), c.ID, "merged")
	if _, err := os.Stat(merged); os.IsNotExist(err) {
		_, _, merged = c.OverlayDirs()
	}

	args := []string{
		"sftp-serve",
		"--root", merged,
		"--port", strconv.Itoa(port),
		"--user", c.SFTPUser,
		"--password", c.SFTPPassword,
	}

	cmd := exec.Command(binPath, args...)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start SFTP server process: %w", err)
	}
	c.SFTPServerPID = cmd.Process.Pid
	c.Save()

	fmt.Printf("Connect: sftp://%s@host:%d password=%s\n", c.SFTPUser, port, c.SFTPPassword)
	fmt.Printf("  (container: %s)\n", c.Name)
	return nil
}

func (c *Container) StopSFTPServer() {
	if c.SFTPServerPID > 0 {
		if proc, err := os.FindProcess(c.SFTPServerPID); err == nil {
			proc.Kill()
		}
		c.SFTPServerPID = 0
	}
	c.SFTPPort = 0
	c.Save()
}

func (c *Container) StartFTPServer(binPath string) error {
	if !c.EnableFTP {
		return nil
	}
	used := getUsedPorts()
	port := allocatePort(used, sftpBasePort+1000)
	passStart := allocatePort(used, sftpPassBasePort)
	c.FTPPort = port
	c.FTPPassiveStart = passStart

	merged := filepath.Join(state.OverlayDir(), c.ID, "merged")
	if _, err := os.Stat(merged); os.IsNotExist(err) {
		_, _, merged = c.OverlayDirs()
	}

	cmd := exec.Command(binPath, "ftp-serve",
		"--root", merged,
		"--port", strconv.Itoa(port),
		"--password", c.SFTPPass(),
		"--passive-start", strconv.Itoa(passStart),
	)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start FTP server process: %w", err)
	}
	c.FTPServerPID = cmd.Process.Pid
	c.Save()

	fmt.Printf("FTP: ftp://dck@host:%d password=%s\n", port, c.SFTPPass())
	return nil
}

func (c *Container) StopFTPServer() {
	if c.FTPServerPID > 0 {
		if proc, err := os.FindProcess(c.FTPServerPID); err == nil {
			proc.Kill()
		}
		c.FTPServerPID = 0
	}
	c.FTPPort = 0
	c.FTPPassiveStart = 0
	c.Save()
}
