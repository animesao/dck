package network

import (
	"encoding/json"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"sync"

	"dck/internal/state"
)

const (
	BridgeName = "dck0"
	BridgeCIDR = "10.0.2.0/24"
	BridgeIP   = "10.0.2.1"
)

type ipPool struct {
	Allocated map[string]bool `json:"allocated"`
	mu        sync.Mutex
}

var globalPool *ipPool

func loadPool() *ipPool {
	if globalPool != nil {
		return globalPool
	}
	path := filepath.Join(state.DataDir(), "networks", "ips.json")
	p := &ipPool{Allocated: make(map[string]bool)}
	if data, err := os.ReadFile(path); err == nil {
		json.Unmarshal(data, p)
	}
	globalPool = p
	return p
}

func savePool(p *ipPool) {
	path := filepath.Join(state.DataDir(), "networks", "ips.json")
	os.MkdirAll(filepath.Dir(path), 0755)
	data, _ := json.Marshal(p)
	os.WriteFile(path, data, 0644)
}

func AllocateIP() (string, error) {
	p := loadPool()
	p.mu.Lock()
	defer p.mu.Unlock()

	_, cidr, _ := net.ParseCIDR(BridgeCIDR)
	ones, bits := cidr.Mask.Size()
	totalHosts := (1 << uint(bits-ones))

	for i := 2; i < totalHosts-1; i++ {
		ip := make(net.IP, len(cidr.IP))
		copy(ip, cidr.IP)
		ip[len(ip)-1] = byte(i)
		ipStr := ip.String()
		if !p.Allocated[ipStr] {
			p.Allocated[ipStr] = true
			savePool(p)
			return ipStr, nil
		}
	}
	return "", fmt.Errorf("no available IP addresses in %s", BridgeCIDR)
}

func ReleaseIP(ip string) {
	p := loadPool()
	p.mu.Lock()
	defer p.mu.Unlock()
	delete(p.Allocated, ip)
	savePool(p)
}

func EnsureBridge() error {
	exec.Command("ip", "link", "add", BridgeName, "type", "bridge").Run()
	exec.Command("ip", "addr", "add", fmt.Sprintf("%s/24", BridgeIP), "dev", BridgeName).Run()
	exec.Command("ip", "link", "set", BridgeName, "up").Run()

	if err := exec.Command("iptables", "-t", "nat", "-C", "POSTROUTING",
		"-s", BridgeCIDR, "!", "-o", BridgeName, "-j", "MASQUERADE").Run(); err != nil {
		exec.Command("iptables", "-t", "nat", "-A", "POSTROUTING",
			"-s", BridgeCIDR, "!", "-o", BridgeName, "-j", "MASQUERADE").Run()
	}

	exec.Command("iptables", "-A", "FORWARD", "-i", BridgeName, "-j", "ACCEPT").Run()
	exec.Command("iptables", "-A", "FORWARD", "-o", BridgeName, "-j", "ACCEPT").Run()
	return nil
}

func SetupVeth(containerID string, pid int, containerIP string) error {
	hostIf := fmt.Sprintf("ve%s", containerID[:8])
	contIf := fmt.Sprintf("vc%s", containerID[:8])

	exec.Command("ip", "link", "add", hostIf, "type", "veth", "peer", "name", contIf).Run()

	exec.Command("ip", "link", "set", contIf, "netns", fmt.Sprintf("%d", pid)).Run()
	exec.Command("ip", "link", "set", hostIf, "master", BridgeName).Run()
	exec.Command("ip", "link", "set", hostIf, "up").Run()

	runInNetns(pid, "ip", "link", "set", "lo", "up")
	runInNetns(pid, "ip", "link", "set", contIf, "name", "eth0")
	runInNetns(pid, "ip", "addr", "add", fmt.Sprintf("%s/24", containerIP), "dev", "eth0")
	runInNetns(pid, "ip", "link", "set", "eth0", "up")
	runInNetns(pid, "ip", "route", "add", "default", "via", BridgeIP)

	return nil
}

func runInNetns(pid int, args ...string) error {
	base := []string{"-t", fmt.Sprintf("%d", pid), "-n", "--"}
	return exec.Command("nsenter", append(base, args...)...).Run()
}

type PortRule struct {
	HostPort      int    `json:"host_port"`
	ContainerPort int    `json:"container_port"`
	Protocol      string `json:"protocol"`
	ContainerIP   string `json:"container_ip"`
}

func AddPortForwarding(containerIP string, hostPort, containerPort int, protocol string) error {
	dnat := []string{
		"-t", "nat", "-A", "PREROUTING",
		"-p", protocol, "--dport", fmt.Sprintf("%d", hostPort),
		"-j", "DNAT", "--to-destination", fmt.Sprintf("%s:%d", containerIP, containerPort),
	}
	if err := exec.Command("iptables", dnat...).Run(); err != nil {
		return fmt.Errorf("DNAT: %w", err)
	}

	fwd := []string{
		"-A", "FORWARD",
		"-p", protocol, "-d", containerIP, "--dport", fmt.Sprintf("%d", containerPort),
		"-j", "ACCEPT",
	}
	if err := exec.Command("iptables", fwd...).Run(); err != nil {
		exec.Command("iptables", "-t", "nat", "-D", dnat[3:]...).Run()
		return fmt.Errorf("FORWARD: %w", err)
	}

	return nil
}

func RemovePortForwarding(containerIP string, hostPort, containerPort int, protocol string) {
	exec.Command("iptables", "-t", "nat", "-D", "PREROUTING",
		"-p", protocol, "--dport", fmt.Sprintf("%d", hostPort),
		"-j", "DNAT", "--to-destination", fmt.Sprintf("%s:%d", containerIP, containerPort)).Run()

	exec.Command("iptables", "-D", "FORWARD",
		"-p", protocol, "-d", containerIP, "--dport", fmt.Sprintf("%d", containerPort),
		"-j", "ACCEPT").Run()
}

func RemoveVeth(containerID string) {
	hostIf := fmt.Sprintf("ve%s", containerID[:8])
	exec.Command("ip", "link", "delete", hostIf).Run()
}

func CleanupContainerNetwork(containerID, containerIP string, ports []PortRule) {
	for _, p := range ports {
		RemovePortForwarding(containerIP, p.HostPort, p.ContainerPort, p.Protocol)
	}
	ReleaseIP(containerIP)
	RemoveVeth(containerID)
}
