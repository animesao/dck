package orchestrator

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"

	"dck/internal/state"
)

var fnLock sync.RWMutex

// DeployFunction deploys a serverless function
func DeployFunction(name, image string, port int, opts FnOpts) (*Function, error) {
	fnLock.Lock()
	defer fnLock.Unlock()

	_ = loadFunctions()

	fn := &Function{
		Name:        name,
		Image:       image,
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

	if _, exists := allFunctions[name]; !exists {
		return fmt.Errorf("function %q not found", name)
	}

	// Scale down all active containers
	fn := allFunctions[name]
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

	// Ensure at least one warm container is running
	if fn.ActiveContainers == 0 {
		if err := scaleUpFunction(fn, 1); err != nil {
			return nil, fmt.Errorf("scale up function %s: %w", name, err)
		}
	}

	// Forward request to the function container
	result, err := forwardToFunction(fn, payload)
	if err != nil {
		return nil, err
	}

	fn.InvokeCount++

	// Idle scale-down is handled by the garbage collector goroutine
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
	}
}

func scaleUpFunction(fn *Function, count int) error {
	fmt.Printf("[faas] scaling up %s: +%d\n", fn.Name, count)
	fn.ActiveContainers += count
	// In full implementation:
	// 1. Pull image
	// 2. Create and start container
	// 3. Register DNS record
	return nil
}

func scaleDownFunction(fn *Function) {
	fmt.Printf("[faas] scaling down %s: active=%d\n", fn.Name, fn.ActiveContainers)
	// In full implementation:
	// 1. Stop and remove idle containers
	// 2. Remove DNS records
	fn.ActiveContainers = 0
}

func forwardToFunction(fn *Function, payload []byte) ([]byte, error) {
	// In full implementation: HTTP proxy to function container
	return payload, nil // echo for now
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
		if fn.ActiveContainers > fn.Replicas {
			fmt.Printf("[faas] auto-scaling down %s (idle)\n", fn.Name)
			scaleDownFunction(fn)
		}
	}
}
