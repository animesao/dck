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

func (c *Container) ensureSSHKeypair() error {
	if c.SSHPublicKey != "" && c.SSHPrivateKeyPath != "" {
		if _, err := os.Stat(c.SSHPrivateKeyPath); err == nil {
			return nil
		}
	}

	privPEM, pubSSH, err := sftp.GenerateClientKey()
	if err != nil {
		return fmt.Errorf("generate SSH keypair: %w", err)
	}

	keyDir := filepath.Join(state.DataDir(), "keys")
	os.MkdirAll(keyDir, 0700)

	privPath := filepath.Join(keyDir, c.ID[:16]+"_rsa")
	if err := os.WriteFile(privPath, []byte(privPEM), 0600); err != nil {
		return fmt.Errorf("write private key: %w", err)
	}

	c.SSHPublicKey = pubSSH
	c.SSHPrivateKeyPath = privPath
	c.Save()
	return nil
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
	if !c.EnableSFTP && !c.EnableSSH {
		return nil
	}

	if err := c.ensureSSHKeypair(); err != nil {
		return fmt.Errorf("SSH keypair: %w", err)
	}

	used := getUsedPorts()
	port := allocatePort(used, sftpBasePort)
	c.SFTPPort = port

	killPort(port)

	merged := filepath.Join(state.OverlayDir(), c.ID, "merged")
	if _, err := os.Stat(merged); os.IsNotExist(err) {
		_, _, merged = c.OverlayDirs()
	}

	args := []string{
		"sftp-serve",
		"--root", merged,
		"--port", strconv.Itoa(port),
		"--password", c.ID[:16],
		"--pubkey", c.SSHPublicKey,
	}
	if c.PID > 0 {
		args = append(args, "--pid", strconv.Itoa(c.PID))
	}

	cmd := exec.Command(binPath, args...)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start SSH/SFTP server process: %w", err)
	}
	c.SFTPServerPID = cmd.Process.Pid
	c.Save()

	fmt.Printf("SSH: ssh://dck@host:%d (key: %s)\n", port, c.SSHPrivateKeyPath)
	fmt.Printf("SFTP: sftp://dck@host:%d password=%s\n", port, c.ID[:16])
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
	c.SSHServerPID = 0
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
		"--password", c.ID[:16],
		"--passive-start", strconv.Itoa(passStart),
	)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start FTP server process: %w", err)
	}
	c.FTPServerPID = cmd.Process.Pid
	c.Save()

	fmt.Printf("FTP: ftp://dck@host:%d password=%s\n", port, c.ID[:16])
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
