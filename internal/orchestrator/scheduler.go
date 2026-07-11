package orchestrator

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"dck/internal/container"
	"dck/internal/image"
	"dck/internal/state"
)

// ScheduleReplica places a container on a node and starts it
func ScheduleReplica(serviceName string, svc *Service) error {
	nodes, err := ListNodes()
	if err != nil || len(nodes) == 0 {
		return fmt.Errorf("no available nodes")
	}

	var active []*Node
	for _, n := range nodes {
		if n.State == NodeStateActive && n.ID != clusterConf.NodeID {
			active = append(active, n)
		}
	}

	localNode, _ := GetNode()
	if localNode != nil && localNode.State == NodeStateActive {
		active = append(active, localNode)
	}

	if len(active) == 0 {
		return fmt.Errorf("no active nodes")
	}

	sort.Slice(active, func(i, j int) bool {
		return active[i].MemAvail > active[j].MemAvail
	})

	target := active[0]
	fmt.Printf("[scheduler] placing replica of %s on %s (%s:%d)\n",
		serviceName, target.Name, target.Address, target.APIPort)

	if target.ID == clusterConf.NodeID {
		return startLocalReplica(serviceName, svc)
	}

	return startRemoteReplica(serviceName, svc, target)
}

func startLocalReplica(serviceName string, svc *Service) error {
	fmt.Printf("[scheduler] starting local replica of %s\n", serviceName)

	img, err := image.Pull(svc.Image)
	if err != nil {
		return fmt.Errorf("pull image %s: %w", svc.Image, err)
	}

	var ports []container.PortMap
	for _, p := range svc.Ports {
		hp := p.Port
		if hp == 0 {
			hp = p.TargetPort
		}
		proto := p.Protocol
		if proto == "" {
			proto = "tcp"
		}
		ports = append(ports, container.PortMap{
			HostPort:      hp,
			ContainerPort: p.TargetPort,
			Protocol:      proto,
		})
	}

	var volumes []container.VolumeMount
	for _, v := range svc.Volumes {
		parts := strings.SplitN(v, ":", 2)
		if len(parts) == 2 {
			volumes = append(volumes, container.VolumeMount{
				Source: parts[0],
				Target: parts[1],
			})
		}
	}

	env := make([]string, 0, len(svc.Env))
	for k, v := range svc.Env {
		env = append(env, k+"="+v)
	}

	labels := svc.Labels
	if labels == nil {
		labels = make(map[string]string)
	}
	labels["dck.service"] = serviceName

	restart := svc.Restart
	if restart == "" {
		restart = "always"
	}

	replicaID := generateID()

	opts := container.CreateOpts{
		Name:    serviceName + "." + replicaID[:8],
		Ports:   ports,
		Volumes: volumes,
		Env:     env,
		Restart: restart,
		Detach:  true,
		Labels:  labels,
	}
	if svc.Command != "" {
		opts.Cmd = strings.Fields(svc.Command)
	}

	c := container.New(img, opts)
	if err := c.Save(); err != nil {
		return fmt.Errorf("save container: %w", err)
	}

	if err := c.Start(); err != nil {
		return fmt.Errorf("start container: %w", err)
	}

	saveReplica(serviceName, replicaID, c.ID, clusterConf.NodeID)

	fmt.Printf("[scheduler] local replica %s running (container %s)\n", replicaID[:8], c.ID[:12])
	return nil
}

func startRemoteReplica(serviceName string, svc *Service, node *Node) error {
	replicaID := generateID()

	reqBody, _ := json.Marshal(map[string]interface{}{
		"service_name": serviceName,
		"replica_id":   replicaID,
		"image":        svc.Image,
		"ports":        svc.Ports,
		"env":          svc.Env,
		"volumes":      svc.Volumes,
		"command":      svc.Command,
		"restart":      svc.Restart,
	})

	url := fmt.Sprintf("http://%s:%d/cluster/replicas", node.Address, node.APIPort)
	resp, err := http.Post(url, "application/json", bytes.NewReader(reqBody))
	if err != nil {
		return fmt.Errorf("schedule on %s: %w", node.Name, err)
	}
	defer resp.Body.Close()

	var result struct {
		ContainerID string `json:"container_id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("decode response from %s: %w", node.Name, err)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("schedule on %s: status %d", node.Name, resp.StatusCode)
	}

	saveReplica(serviceName, replicaID, result.ContainerID, node.ID)

	fmt.Printf("[scheduler] remote replica %s on %s (container %s)\n",
		replicaID[:8], node.Name, result.ContainerID[:12])
	return nil
}

// RemoveRemoteReplica stops a container on a remote node
func RemoveRemoteReplica(nodeID, containerID string) error {
	clusterLock.RLock()
	node, ok := clusterConf.Nodes[nodeID]
	clusterLock.RUnlock()
	if !ok {
		return fmt.Errorf("node %s not found", nodeID)
	}

	if nodeID == clusterConf.NodeID {
		c, err := container.Load(containerID)
		if err != nil {
			return fmt.Errorf("load local container %s: %w", containerID, err)
		}
		if err := c.Remove(true); err != nil {
			return fmt.Errorf("remove local container %s: %w", containerID, err)
		}
		fmt.Printf("[scheduler] stopped local container %s\n", containerID[:12])
		return nil
	}

	req, _ := http.NewRequest("DELETE",
		fmt.Sprintf("http://%s:%d/cluster/replicas/%s", node.Address, node.APIPort, containerID),
		nil)

	resp, err := httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("remove on %s: %w", node.Name, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusNotFound {
		return fmt.Errorf("remove on %s: status %d", node.Name, resp.StatusCode)
	}

	fmt.Printf("[scheduler] removed remote container %s on %s\n", containerID[:12], node.Name)
	return nil
}

// AutoHealServices checks service replicas and replaces failed ones
func AutoHealServices() {
	clusterLock.RLock()
	services := make(map[string]*Service)
	for k, v := range clusterConf.Services {
		services[k] = v
	}
	clusterLock.RUnlock()

	for name, svc := range services {
		replicas, _ := GetServiceReplicas(name)
		running := 0

		for _, r := range replicas {
			if r.Status == "running" {
				running++
			}
		}

		if running < svc.Replicas {
			needed := svc.Replicas - running
			fmt.Printf("[heal] service %s: running=%d desired=%d, scheduling %d new replicas\n",
				name, running, svc.Replicas, needed)

			for i := 0; i < needed; i++ {
				if err := ScheduleReplica(name, svc); err != nil {
					fmt.Fprintf(os.Stderr, "[heal] schedule error for %s: %v\n", name, err)
				}
				time.Sleep(500 * time.Millisecond)
			}
		}
	}
}

// StartAutoHealer runs the auto-heal loop
func StartAutoHealer(stop chan struct{}) {
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			AutoHealServices()
		case <-stop:
			return
		}
	}
}

// RollingUpdateService performs a rolling update of a service
func RollingUpdateService(name, newImage string, opts ServiceOpts) error {
	svc, err := GetService(name)
	if err != nil {
		return err
	}

	parallelism := 1
	if svc.UpdateConfig != nil && svc.UpdateConfig.Parallelism > 0 {
		parallelism = svc.UpdateConfig.Parallelism
	}

	delaySec := 0
	if svc.UpdateConfig != nil && svc.UpdateConfig.Delay > 0 {
		delaySec = svc.UpdateConfig.Delay
	}

	order := "stop-first"
	if svc.UpdateConfig != nil && svc.UpdateConfig.Order != "" {
		order = svc.UpdateConfig.Order
	}

	replicas, _ := GetServiceReplicas(name)
	fmt.Printf("[rolling] updating %s: %s -> %s (parallel=%d, order=%s)\n",
		name, svc.Image, newImage, parallelism, order)

	batch := 0

	for i := 0; i < len(replicas); i += parallelism {
		end := i + parallelism
		if end > len(replicas) {
			end = len(replicas)
		}
		batch++

		batchReps := replicas[i:end]
		fmt.Printf("[rolling] batch %d: updating %d replicas\n", batch, len(batchReps))

		for _, r := range batchReps {
			if order == "start-first" {
				fmt.Printf("[rolling] starting new replica of %s (image: %s)\n", name, newImage)
				oldSvc := *svc
				oldSvc.Image = newImage
				ScheduleReplica(name, &oldSvc)
				RemoveRemoteReplica(r.NodeID, r.ContainerID)
			} else {
				fmt.Printf("[rolling] stopping replica %s\n", r.ID)
				RemoveRemoteReplica(r.NodeID, r.ContainerID)
				oldSvc := *svc
				oldSvc.Image = newImage
				ScheduleReplica(name, &oldSvc)
			}
		}

		if delaySec > 0 && batch < (len(replicas)+parallelism-1)/parallelism {
			fmt.Printf("[rolling] waiting %ds before next batch...\n", delaySec)
			time.Sleep(time.Duration(delaySec) * time.Second)
		}
	}

	svc.Image = newImage
	svc.UpdatedAt = time.Now()

	serviceLock.Lock()
	clusterConf.Services[name] = svc
	saveServices()
	serviceLock.Unlock()

	fmt.Printf("[rolling] update complete: %s now using %s\n", name, newImage)
	return nil
}

// --- replica persistence ---

func saveReplica(serviceName, replicaID, containerID, nodeID string) {
	dir := filepath.Join(state.DataDir(), ServiceStateDir, serviceName)
	os.MkdirAll(dir, 0755)

	r := ServiceReplica{
		ID:           replicaID,
		ServiceName:  serviceName,
		NodeID:       nodeID,
		ContainerID:  containerID,
		Status:       "running",
		CreatedAt:    time.Now(),
	}

	data, _ := json.MarshalIndent(r, "", "  ")
	os.WriteFile(filepath.Join(dir, replicaID+".json"), data, 0644)
}

var httpClient = &http.Client{
	Timeout: 30 * time.Second,
}
