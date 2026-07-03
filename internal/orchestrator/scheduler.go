package orchestrator

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"time"
)

// ScheduleReplica places a container on a node and starts it
func ScheduleReplica(serviceName string, svc *Service) error {
	nodes, err := ListNodes()
	if err != nil || len(nodes) == 0 {
		return fmt.Errorf("no available nodes")
	}

	// Filter active nodes
	var active []*Node
	for _, n := range nodes {
		if n.State == NodeStateActive && n.ID != clusterConf.NodeID {
			active = append(active, n)
		}
	}

	// Check if local node can run it
	localNode, _ := GetNode()
	if localNode != nil && localNode.State == NodeStateActive {
		active = append(active, localNode)
	}

	if len(active) == 0 {
		return fmt.Errorf("no active nodes")
	}

	// Sort by available memory descending
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
	// In practice, this creates a container via the internal API
	return nil
}

func startRemoteReplica(serviceName string, svc *Service, node *Node) error {
	reqBody, _ := json.Marshal(map[string]interface{}{
		"service": serviceName,
		"image":   svc.Image,
		"ports":   svc.Ports,
		"env":     svc.Env,
		"volumes": svc.Volumes,
		"command": svc.Command,
		"restart": svc.Restart,
	})

	url := fmt.Sprintf("http://%s:%d/services/%s/replicas",
		node.Address, node.APIPort, serviceName)

	resp, err := http.Post(url, "application/json", bytes.NewReader(reqBody))
	if err != nil {
		return fmt.Errorf("schedule on %s: %w", node.Name, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("schedule on %s: status %d", node.Name, resp.StatusCode)
	}

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
		fmt.Printf("[scheduler] stopping local container %s\n", containerID)
		return nil
	}

	req, _ := http.NewRequest("DELETE",
		fmt.Sprintf("http://%s:%d/containers/%s", node.Address, node.APIPort, containerID),
		nil)

	resp, err := httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("remove on %s: %w", node.Name, err)
	}
	resp.Body.Close()
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
		failed := 0

		for _, r := range replicas {
			if r.Status == "running" {
				running++
			} else if r.Status == "failed" {
				failed++
			}
		}

		if running < svc.Replicas {
			needed := svc.Replicas - running
			fmt.Printf("[heal] service %s: running=%d desired=%d, scheduling %d new replicas\n",
				name, running, svc.Replicas, needed)

			for i := 0; i < needed; i++ {
				if err := ScheduleReplica(name, svc); err != nil {
					fmt.Fprintf(nil, "[heal] schedule error for %s: %v\n", name, err)
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
				// Start new container first, then stop old
				fmt.Printf("[rolling] starting new replica of %s (image: %s)\n", name, newImage)
				ScheduleReplica(name, svc)
				RemoveRemoteReplica(r.NodeID, r.ContainerID)
			} else {
				// Stop old first, then start new
				fmt.Printf("[rolling] stopping replica %s\n", r.ID)
				RemoveRemoteReplica(r.NodeID, r.ContainerID)
				ScheduleReplica(name, svc)
			}
		}

		if delaySec > 0 && batch < (len(replicas)+parallelism-1)/parallelism {
			fmt.Printf("[rolling] waiting %ds before next batch...\n", delaySec)
			time.Sleep(time.Duration(delaySec) * time.Second)
		}
	}

	// Update service definition
	svc.Image = newImage
	svc.UpdatedAt = time.Now()

	serviceLock.Lock()
	clusterConf.Services[name] = svc
	saveServices()
	serviceLock.Unlock()

	fmt.Printf("[rolling] update complete: %s now using %s\n", name, newImage)
	return nil
}

// httpClient reusable HTTP client for intra-cluster communication
var httpClient = &http.Client{
	Timeout: 10 * time.Second,
}
