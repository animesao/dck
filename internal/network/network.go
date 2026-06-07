package network

import (
	"encoding/json"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"

	"dck/internal/state"
)

func EnsureSysctl() {
	exec.Command("sysctl", "-w", "net.ipv4.ip_forward=1").Run()

	os.MkdirAll("/etc/sysctl.d", 0755)
	confPath := "/etc/sysctl.d/99-dck.conf"
	data, err := os.ReadFile(confPath)
	if err != nil || !strings.Contains(string(data), "net.ipv4.ip_forward=1") {
		f, err := os.OpenFile(confPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err == nil {
			f.WriteString("# dck: enable IP forwarding for container networking\nnet.ipv4.ip_forward=1\n")
			f.Close()
		}
	}
}

func EnsureUFW() {
	if _, err := exec.Command("ufw", "status").Output(); err != nil {
		return
	}
	exec.Command("ufw", "route", "allow", "in", "on", BridgeName).Run()
	exec.Command("ufw", "route", "allow", "out", "on", BridgeName).Run()
}

func EnsureNetBase() {
	EnsureSysctl()
	EnsureUFW()
	EnsureBridge()
}

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
	if err := exec.Command("ip", "link", "show", BridgeName).Run(); err != nil {
		exec.Command("ip", "link", "add", BridgeName, "type", "bridge").Run()
		exec.Command("ip", "addr", "add", fmt.Sprintf("%s/24", BridgeIP), "dev", BridgeName).Run()
	}
	exec.Command("ip", "link", "set", BridgeName, "up").Run()

	if err := exec.Command("iptables", "-t", "nat", "-C", "POSTROUTING",
		"-s", BridgeCIDR, "!", "-o", BridgeName, "-j", "MASQUERADE").Run(); err != nil {
		exec.Command("iptables", "-t", "nat", "-A", "POSTROUTING",
			"-s", BridgeCIDR, "!", "-o", BridgeName, "-j", "MASQUERADE").Run()
	}

	if err := exec.Command("iptables", "-C", "FORWARD", "-i", BridgeName, "-j", "ACCEPT").Run(); err != nil {
		exec.Command("iptables", "-A", "FORWARD", "-i", BridgeName, "-j", "ACCEPT").Run()
	}
	if err := exec.Command("iptables", "-C", "FORWARD", "-o", BridgeName, "-j", "ACCEPT").Run(); err != nil {
		exec.Command("iptables", "-A", "FORWARD", "-o", BridgeName, "-j", "ACCEPT").Run()
	}
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

func removeExistingDNAT(chain string, hostPort int, protocol string) {
	out, err := exec.Command("iptables-save", "-t", "nat").Output()
	if err != nil {
		return
	}
	for _, line := range strings.Split(string(out), "\n") {
		if !strings.HasPrefix(line, "-A "+chain) {
			continue
		}
		if !strings.Contains(line, fmt.Sprintf("--dport %d", hostPort)) {
			continue
		}
		if !strings.Contains(line, "-j DNAT") {
			continue
		}
		del := strings.Replace(line, "-A", "-D", 1)
		exec.Command("iptables", append([]string{"-t", "nat"}, strings.Fields(del)...)...).Run()
	}
}

func ufwAllowPort(hostPort int, protocol string) {
	if _, err := exec.Command("ufw", "status").Output(); err != nil {
		return
	}
	exec.Command("ufw", "allow", fmt.Sprintf("%d/%s", hostPort, protocol)).Run()
}

func ufwDenyPort(hostPort int, protocol string) {
	if _, err := exec.Command("ufw", "status").Output(); err != nil {
		return
	}
	exec.Command("ufw", "delete", "allow", fmt.Sprintf("%d/%s", hostPort, protocol)).Run()
}

func AddPortForwarding(containerIP string, hostPort, containerPort int, protocol string) error {
	removeExistingDNAT("PREROUTING", hostPort, protocol)
	removeExistingDNAT("OUTPUT", hostPort, protocol)

	dnat := []string{
		"-t", "nat", "-A", "PREROUTING",
		"-p", protocol, "--dport", fmt.Sprintf("%d", hostPort),
		"-j", "DNAT", "--to-destination", fmt.Sprintf("%s:%d", containerIP, containerPort),
	}
	if err := exec.Command("iptables", dnat...).Run(); err != nil {
		return fmt.Errorf("DNAT: %w", err)
	}

	output := []string{
		"-t", "nat", "-A", "OUTPUT",
		"-p", protocol, "--dport", fmt.Sprintf("%d", hostPort),
		"-m", "addrtype", "--dst-type", "LOCAL",
		"-j", "DNAT", "--to-destination", fmt.Sprintf("%s:%d", containerIP, containerPort),
	}
	if err := exec.Command("iptables", output...).Run(); err != nil {
		rollback := append([]string{"-t", "nat", "-D"}, dnat[3:]...)
		exec.Command("iptables", rollback...).Run()
		return fmt.Errorf("OUTPUT DNAT: %w", err)
	}

	fwd := []string{
		"-A", "FORWARD",
		"-p", protocol, "-d", containerIP, "--dport", fmt.Sprintf("%d", containerPort),
		"-j", "ACCEPT",
	}
	if err := exec.Command("iptables", fwd...).Run(); err != nil {
		rollback := append([]string{"-t", "nat", "-D"}, dnat[3:]...)
		exec.Command("iptables", rollback...).Run()
		rollback2 := append([]string{"-t", "nat", "-D"}, output[3:]...)
		exec.Command("iptables", rollback2...).Run()
		return fmt.Errorf("FORWARD: %w", err)
	}

	ufwAllowPort(hostPort, protocol)

	return nil
}

func RemovePortForwarding(containerIP string, hostPort, containerPort int, protocol string) {
	exec.Command("iptables", "-t", "nat", "-D", "PREROUTING",
		"-p", protocol, "--dport", fmt.Sprintf("%d", hostPort),
		"-j", "DNAT", "--to-destination", fmt.Sprintf("%s:%d", containerIP, containerPort)).Run()

	exec.Command("iptables", "-t", "nat", "-D", "OUTPUT",
		"-p", protocol, "--dport", fmt.Sprintf("%d", hostPort),
		"-m", "addrtype", "--dst-type", "LOCAL",
		"-j", "DNAT", "--to-destination", fmt.Sprintf("%s:%d", containerIP, containerPort)).Run()

	exec.Command("iptables", "-D", "FORWARD",
		"-p", protocol, "-d", containerIP, "--dport", fmt.Sprintf("%d", containerPort),
		"-j", "ACCEPT").Run()

	ufwDenyPort(hostPort, protocol)
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
