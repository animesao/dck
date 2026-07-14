package orchestrator

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"

	"dck/internal/container"
	"dck/internal/image"
	"dck/internal/state"
)

var fnLock sync.RWMutex

// functionContainers tracks function name -> container IDs for active instances
var functionContainers = make(map[string][]string)

// DeployFunction deploys a serverless function
func DeployFunction(name, imageName string, port int, opts FnOpts) (*Function, error) {
	fnLock.Lock()
	defer fnLock.Unlock()

	_ = loadFunctions()

	if _, exists := allFunctions[name]; exists {
		return nil, fmt.Errorf("function %q already exists", name)
	}

	fn := &Function{
		Name:        name,
		Image:       imageName,
		Handler:     opts.Handler,
		Port:        port,
		Env:         opts.Env,
		Timeout:     opts.Timeout,
		IdleTimeout: opts.IdleTimeout,
		Memory:      opts.Memory,
		CPUs:        opts.CPUs,
		Replicas:    opts.Replicas,
		Labels:      opts.Labels,
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
	}

	if fn.Timeout == 0 {
		fn.Timeout = 30
	}
	if fn.IdleTimeout == 0 {
		fn.IdleTimeout = 300
	}

	allFunctions[name] = fn
	saveFunctions()

	return fn, nil
}

// FnOpts contains optional function configuration
type FnOpts struct {
	Handler     string
	Env         map[string]string
	Timeout     int
	IdleTimeout int
	Memory      string
	CPUs        float64
	Replicas    int
	Labels      map[string]string
}

var allFunctions = make(map[string]*Function)

// ListFunctions returns all deployed functions
func ListFunctions() ([]*Function, error) {
	fnLock.RLock()
	defer fnLock.RUnlock()

	if err := loadFunctions(); err != nil {
		return nil, err
	}

	fns := make([]*Function, 0, len(allFunctions))
	for _, f := range allFunctions {
		fns = append(fns, f)
	}

	sort.Slice(fns, func(i, j int) bool {
		return fns[i].CreatedAt.Before(fns[j].CreatedAt)
	})

	return fns, nil
}

// GetFunction returns a function by name
func GetFunction(name string) (*Function, error) {
	fnLock.RLock()
	defer fnLock.RUnlock()

	if err := loadFunctions(); err != nil {
		return nil, err
	}

	fn, ok := allFunctions[name]
	if !ok {
		return nil, fmt.Errorf("function %q not found", name)
	}
	return fn, nil
}

// RemoveFunction removes a deployed function
func RemoveFunction(name string) error {
	fnLock.Lock()
	defer fnLock.Unlock()

	if err := loadFunctions(); err != nil {
		return err
	}

	fn, exists := allFunctions[name]
	if !exists {
		return fmt.Errorf("function %q not found", name)
	}

	scaleDownFunction(fn)

	delete(allFunctions, name)
	saveFunctions()

	return nil
}

// InvokeFunction calls a deployed function (starts container if needed)
func InvokeFunction(name string, payload []byte) ([]byte, error) {
	fn, err := GetFunction(name)
	if err != nil {
		return nil, err
	}

	fnLock.Lock()
	fn.LastUsed = time.Now()
	fnLock.Unlock()

	if fn.ActiveContainers == 0 {
		replicas := fn.Replicas
		if replicas < 1 {
			replicas = 1
		}
		if err := scaleUpFunction(fn, replicas); err != nil {
			return nil, fmt.Errorf("scale up function %s: %w", name, err)
		}
	}

	result, err := forwardToFunction(fn, payload)
	if err != nil {
		return nil, err
	}

	fnLock.Lock()
	fn.InvokeCount++
	saveFunctions()
	fnLock.Unlock()

	return result, nil
}

// StartFunctionGC starts a background goroutine for function auto-scaling
func StartFunctionGC(stop chan struct{}) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			gcFunctions()
		case <-stop:
			return
		}
	}
}

func gcFunctions() {
	fnLock.RLock()
	fns := make([]*Function, 0, len(allFunctions))
	for _, f := range allFunctions {
		fns = append(fns, f)
	}
	fnLock.RUnlock()

	for _, fn := range fns {
		if fn.ActiveContainers > fn.Replicas {
			scaleDownFunction(fn)
		}
		if fn.IdleTimeout > 0 && fn.ActiveContainers > 0 && !fn.LastUsed.IsZero() {
			if time.Since(fn.LastUsed) > time.Duration(fn.IdleTimeout)*time.Second {
				fmt.Printf("[faas] scaling down %s (idle for >%ds)\n", fn.Name, fn.IdleTimeout)
				scaleDownFunction(fn)
			}
		}
	}
}

func scaleUpFunction(fn *Function, count int) error {
	fmt.Printf("[faas] scaling up %s: +%d\n", fn.Name, count)

	img, err := image.Pull(fn.Image)
	if err != nil {
		return fmt.Errorf("pull image %s: %w", fn.Image, err)
	}

	created := 0
	for i := 0; i < count; i++ {
		replicaID := generateID()
		cName := fmt.Sprintf("fn_%s_%s", fn.Name, replicaID[:8])

		port := fn.Port
		if port == 0 {
			port = 8080
		}

		opts := container.CreateOpts{
			Name:   cName,
			Detach: true,
			Labels: map[string]string{
				"dck.function": fn.Name,
			},
			Ports: []container.PortMap{
				{HostPort: 0, ContainerPort: port, Protocol: "tcp"},
			},
		}

		for k, v := range fn.Env {
			opts.Env = append(opts.Env, k+"="+v)
		}
		if fn.Memory != "" {
			var mem int64
			fmt.Sscanf(fn.Memory, "%d", &mem)
			opts.MemoryLimit = mem * 1024 * 1024
		}
		if fn.CPUs > 0 {
			opts.CPUCount = fn.CPUs
		}
		if fn.Handler != "" {
			opts.Cmd = []string{fn.Handler}
		}

		c := container.New(img, opts)
		if err := c.Save(); err != nil {
			return fmt.Errorf("save container: %w", err)
		}
		if err := c.Start(); err != nil {
			return fmt.Errorf("start container: %w", err)
		}

		fn.ActiveContainers++
		functionContainers[fn.Name] = append(functionContainers[fn.Name], c.ID)
		created++
	}

	fmt.Printf("[faas] scaled up %s: %d containers running\n", fn.Name, created)
	return nil
}

func scaleDownFunction(fn *Function) {
	containers := functionContainers[fn.Name]
	for _, cid := range containers {
		c, err := container.Load(cid)
		if err == nil {
			if err := c.Remove(true); err != nil {
				fmt.Fprintf(os.Stderr, "[faas] error removing container %s: %v\n", cid[:12], err)
			}
		}
	}
	delete(functionContainers, fn.Name)
	fn.ActiveContainers = 0

	fmt.Printf("[faas] scaled down %s\n", fn.Name)
}

func forwardToFunction(fn *Function, payload []byte) ([]byte, error) {
	containers := functionContainers[fn.Name]
	if len(containers) == 0 {
		return nil, fmt.Errorf("no active containers for function %s", fn.Name)
	}

	c, err := container.Load(containers[0])
	if err != nil {
		return nil, fmt.Errorf("load container: %w", err)
	}

	port := fn.Port
	if port == 0 {
		port = 8080
	}

	targetURL := fmt.Sprintf("http://%s:%d", c.IP, port)
	if c.IP == "" {
		targetURL = fmt.Sprintf("http://127.0.0.1:%d", port)
	}

	req, err := http.NewRequest("POST", targetURL, bytes.NewReader(payload))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("forward request to %s: %w", targetURL, err)
	}
	defer resp.Body.Close()

	result, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	return result, nil
}

// --- internal I/O ---

func loadFunctions() error {
	dir := filepath.Join(state.DataDir(), FunctionStateDir)
	os.MkdirAll(dir, 0755)
	path := filepath.Join(dir, "functions.json")

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}

	var fns map[string]*Function
	if err := json.Unmarshal(data, &fns); err != nil {
		return err
	}

	for k, v := range fns {
		allFunctions[k] = v
	}

	return nil
}

func saveFunctions() error {
	dir := filepath.Join(state.DataDir(), FunctionStateDir)
	os.MkdirAll(dir, 0755)

	data, err := json.MarshalIndent(allFunctions, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(filepath.Join(dir, "functions.json"), data, 0644)
}

// CleanIdleFunctions stops functions that have been idle too long
func CleanIdleFunctions() {
	fnLock.RLock()
	fns := make([]*Function, 0, len(allFunctions))
	for _, f := range allFunctions {
		fns = append(fns, f)
	}
	fnLock.RUnlock()

	for _, fn := range fns {
		if fn.IdleTimeout > 0 && fn.ActiveContainers > 0 && !fn.LastUsed.IsZero() {
			if time.Since(fn.LastUsed) > time.Duration(fn.IdleTimeout)*time.Second {
				fmt.Printf("[faas] auto-scaling down %s (idle)\n", fn.Name)
				scaleDownFunction(fn)
			}
		}
		if fn.ActiveContainers > fn.Replicas {
			scaleDownFunction(fn)
		}
	}
}
