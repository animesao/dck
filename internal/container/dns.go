package container

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"dck/internal/state"
)

type DNSRegistry struct {
	mu   sync.RWMutex
	path string
}

var dnsRegistry = &DNSRegistry{path: filepath.Join(state.DataDir(), "dns-registry.json")}

type dnsEntry struct {
	Name string `json:"name"`
	IP   string `json:"ip"`
}

func RegisterDNSName(name, ip string) {
	dnsRegistry.mu.Lock()
	defer dnsRegistry.mu.Unlock()

	entries := dnsRegistry.read()
	found := false
	for i, e := range entries {
		if e.Name == name {
			entries[i].IP = ip
			found = true
			break
		}
	}
	if !found {
		entries = append(entries, dnsEntry{Name: name, IP: ip})
	}
	dnsRegistry.write(entries)
}

func UnregisterDNSName(name string) {
	dnsRegistry.mu.Lock()
	defer dnsRegistry.mu.Unlock()

	entries := dnsRegistry.read()
	var keep []dnsEntry
	for _, e := range entries {
		if e.Name != name {
			keep = append(keep, e)
		}
	}
	dnsRegistry.write(keep)
}

func ResolveDNSName(name string) string {
	dnsRegistry.mu.RLock()
	defer dnsRegistry.mu.RUnlock()

	for _, e := range dnsRegistry.read() {
		if e.Name == name {
			return e.IP
		}
	}
	return ""
}

func ListDNSNames() []dnsEntry {
	dnsRegistry.mu.RLock()
	defer dnsRegistry.mu.RUnlock()
	return dnsRegistry.read()
}

func (r *DNSRegistry) read() []dnsEntry {
	data, err := os.ReadFile(r.path)
	if err != nil {
		return nil
	}
	var entries []dnsEntry
	if err := json.Unmarshal(data, &entries); err != nil {
		return nil
	}
	return entries
}

func (r *DNSRegistry) write(entries []dnsEntry) {
	data, err := json.Marshal(entries)
	if err != nil {
		return
	}
	os.MkdirAll(filepath.Dir(r.path), 0755)
	os.WriteFile(r.path, data, 0644)
}

// EnsureContainerHosts writes container name -> IP mappings to the container's
// /etc/hosts so containers can resolve each other by name.
func EnsureContainerHosts(mergedDir, containerName, containerIP string, dns []string) {
	if mergedDir == "" {
		return
	}

	// Register this container's name
	if containerName != "" && containerIP != "" {
		RegisterDNSName(containerName, containerIP)
	}

	if len(dns) > 0 {
		resolvContent := ""
		for _, s := range dns {
			resolvContent += fmt.Sprintf("nameserver %s\n", s)
		}
		resolvPath := filepath.Join(mergedDir, "etc", "resolv.conf")
		os.MkdirAll(filepath.Dir(resolvPath), 0755)
		os.WriteFile(resolvPath, []byte(resolvContent), 0644)
	}

	// Inject known container names into /etc/hosts
	hostsPath := filepath.Join(mergedDir, "etc", "hosts")
	hostsData, _ := os.ReadFile(hostsPath)
	hostsContent := string(hostsData)

	if !strings.Contains(hostsContent, "# dck-managed") {
		entries := ListDNSNames()
		var sb strings.Builder
		sb.WriteString(hostsContent)
		sb.WriteString("\n# dck-managed names\n")
		for _, e := range entries {
			if e.Name != containerName {
				sb.WriteString(fmt.Sprintf("%s\t%s\n", e.IP, e.Name))
			}
		}
		os.WriteFile(hostsPath, []byte(sb.String()), 0644)
	}
}
