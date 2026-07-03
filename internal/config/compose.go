package config

import (
	"fmt"
	"os"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

type composeFile struct {
	Version  string                     `yaml:"version"`
	Services map[string]composeService  `yaml:"services"`
	Volumes  map[string]composeVolume   `yaml:"volumes"`
	Networks map[string]composeNetwork  `yaml:"networks"`
}

type composeService struct {
	Image       string                 `yaml:"image"`
	ContainerName string               `yaml:"container_name"`
	Ports       []string               `yaml:"ports"`
	Environment interface{}            `yaml:"environment"` // []string or map[string]string
	EnvFile     interface{}            `yaml:"env_file"`    // string or []string
	Volumes     []interface{}          `yaml:"volumes"`     // []string or []composeVolumeMount
	DependsOn   interface{}            `yaml:"depends_on"`  // []string or map
	Restart     string                 `yaml:"restart"`
	Command     interface{}            `yaml:"command"`     // string or []string
	Entrypoint  interface{}            `yaml:"entrypoint"`  // string or []string
	WorkingDir  string                 `yaml:"working_dir"`
	User        string                 `yaml:"user"`
	DNS         interface{}            `yaml:"dns"`         // string or []string
	CapAdd      []string               `yaml:"cap_add"`
	CapDrop     []string               `yaml:"cap_drop"`
	Labels      map[string]string      `yaml:"labels"`
	Healthcheck *composeHealthcheck    `yaml:"healthcheck"`
	Networks    interface{}            `yaml:"networks"`    // []string or map
	NetworkMode string                 `yaml:"network_mode"`
	ReadOnly    bool                   `yaml:"read_only"`
	StdinOpen   bool                   `yaml:"stdin_open"`
	TTY         bool                   `yaml:"tty"`
	StopSignal  string                 `yaml:"stop_signal"`
	StopGracePeriod string             `yaml:"stop_grace_period"`
	Sysctls     map[string]string      `yaml:"sysctls"`
	Ulimits     map[string]composeUlimit `yaml:"ulimits"`
	Memory      string                 `yaml:"memory"`   // or mem_limit
	MemLimit    string                 `yaml:"mem_limit"`
	CPUs        float64                `yaml:"cpus"`
	CPUSet      string                 `yaml:"cpuset"`
	Privileged  bool                   `yaml:"privileged"`
	Hostname    string                 `yaml:"hostname"`

	// Less common but useful
	Expose      []string               `yaml:"expose"`
	ExtraHosts  []string               `yaml:"extra_hosts"`
	Secrets     []string               `yaml:"secrets"`
	Configs     []string               `yaml:"configs"`

	// Build (skip for now - we just use image)
	Build       interface{}            `yaml:"build"`
}

type composeVolume struct {
	Driver     string                 `yaml:"driver"`
	DriverOpts map[string]string      `yaml:"driver_opts"`
}

type composeNetwork struct {
	Driver     string                 `yaml:"driver"`
	DriverOpts map[string]string      `yaml:"driver_opts"`
}

type composeHealthcheck struct {
	Test     interface{} `yaml:"test"`     // string or []string
	Interval string      `yaml:"interval"`
	Timeout  string      `yaml:"timeout"`
	Retries  int         `yaml:"retries"`
}

type composeUlimit struct {
	Soft int `yaml:"soft"`
	Hard int `yaml:"hard"`
}

type composeVolumeMount struct {
	Type     string `yaml:"type"`
	Source   string `yaml:"source"`
	Target   string `yaml:"target"`
	ReadOnly bool   `yaml:"read_only"`
}

// LoadCompose loads a docker-compose.yaml file and returns a Config.
func LoadCompose(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read compose file: %w", err)
	}

	var cf composeFile
	if err := yaml.Unmarshal(data, &cf); err != nil {
		return nil, fmt.Errorf("parse compose YAML: %w", err)
	}

	cfg := &Config{
		Container: make(map[string]ContainerConfig),
	}

	for name, svc := range cf.Services {
		cc := ContainerConfig{
			Image:       svc.Image,
			Restart:     svc.Restart,
			Hostname:    svc.Hostname,
			WorkDir:     svc.WorkingDir,
			User:        svc.User,
			NetworkMode: svc.NetworkMode,
			Readonly:    svc.ReadOnly,
			NoNewPrivs:  false,
			Labels:      svc.Labels,
			CapAdd:      svc.CapAdd,
			CapDrop:     svc.CapDrop,
			Sysctls:     svc.Sysctls,
			DNS:         toStringSlice(svc.DNS),
		}

		// Container name (use service name if not specified)
		if svc.ContainerName != "" {
			cc.Hostname = svc.ContainerName
		}

		// Memory
		mem := svc.Memory
		if mem == "" {
			mem = svc.MemLimit
		}
		cc.Memory = mem

		// CPUs
		cc.CPUs = svc.CPUs

		// Ports (already []string in compose yaml, or may be int-int format)
		for _, p := range svc.Ports {
			cc.Ports = append(cc.Ports, normalizePort(p))
		}

		// Environment - can be []string or map[string]string
		cc.Env = parseComposeEnv(svc.Environment)

		// Env file - can be string or []string
		cc.EnvFile = parseComposeEnvFile(svc.EnvFile)

		// Command - can be string or []string
		cc.Command = parseComposeCommand(svc.Command)

		// Entrypoint
		if ep := parseComposeCommand(svc.Entrypoint); ep != "" {
			cc.Entrypoint = ep
		}

		// Volumes - can be []string or []map
		for _, v := range svc.Volumes {
			switch vol := v.(type) {
			case string:
				cc.Volumes = append(cc.Volumes, vol)
			case map[string]interface{}:
				src, _ := vol["source"].(string)
				tgt, _ := vol["target"].(string)
				if src == "" {
					src, _ = vol["src"].(string)
				}
				if src != "" && tgt != "" {
					mount := src + ":" + tgt
					if ro, ok := vol["read_only"].(bool); ok && ro {
						mount += ":ro"
					}
					cc.Volumes = append(cc.Volumes, mount)
				}
			}
		}

		// Healthcheck
		if svc.Healthcheck != nil {
			cc.Healthcheck = parseComposeHealthcheck(svc.Healthcheck)
		}

		// Ulimits
		if len(svc.Ulimits) > 0 {
			cc.Ulimits = make(map[string]string)
			for name, ul := range svc.Ulimits {
				cc.Ulimits[name] = fmt.Sprintf("%d:%d", ul.Soft, ul.Hard)
			}
		}

		// Restart policy - normalize Docker compose values
		cc.Restart = normalizeRestart(cc.Restart)

		// Use service name as container name for config key
		cfg.Container[name] = cc
	}

	return cfg, nil
}

// LoadConfigOrCompose auto-detects the config file format and loads it.
func LoadConfigOrCompose(path string) (*Config, string, error) {
	if path != "" {
		cfg, p, err := tryLoad(path)
		return cfg, p, err
	}

	// Try auto-detect in order
	candidates := []string{
		"dck.toml",
		"compose.yaml",
		"compose.yml",
		"docker-compose.yaml",
		"docker-compose.yml",
	}

	home, _ := os.UserHomeDir()
	if home != "" {
		candidates = append(candidates, home+"/.dck/dck.toml")
	}

	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			cfg, _, err := tryLoad(p)
			if err != nil {
				return nil, p, err
			}
			return cfg, p, nil
		}
	}

	return nil, "", fmt.Errorf("no config file found (looked for dck.toml, compose.yaml, compose.yml)")
}

func tryLoad(path string) (*Config, string, error) {
	switch {
	case strings.HasSuffix(path, ".toml"):
		cfg, err := loadFile(path)
		return cfg, path, err
	case strings.HasSuffix(path, ".yaml"), strings.HasSuffix(path, ".yml"):
		cfg, err := LoadCompose(path)
		return cfg, path, err
	default:
		// Try both, prefer toml
		cfg, err := loadFile(path)
		if err == nil {
			return cfg, path, nil
		}
		cfg2, err2 := LoadCompose(path)
		if err2 == nil {
			return cfg2, path, nil
		}
		return nil, path, fmt.Errorf("cannot parse %s as TOML or YAML", path)
	}
}

// Helpers

func parseComposeEnv(env interface{}) map[string]string {
	result := make(map[string]string)
	if env == nil {
		return result
	}

	switch e := env.(type) {
	case []interface{}:
		for _, item := range e {
			if s, ok := item.(string); ok {
				if parts := strings.SplitN(s, "=", 2); len(parts) == 2 {
					result[parts[0]] = parts[1]
				}
			}
		}
	case map[string]interface{}:
		for k, v := range e {
			result[k] = fmt.Sprintf("%v", v)
		}
	case map[string]string:
		for k, v := range e {
			result[k] = v
		}
	}

	return result
}

func parseComposeEnvFile(ef interface{}) string {
	if ef == nil {
		return ""
	}
	switch e := ef.(type) {
	case string:
		return e
	case []interface{}:
		if len(e) > 0 {
			if s, ok := e[0].(string); ok {
				return s
			}
		}
	case []string:
		if len(e) > 0 {
			return e[0]
		}
	}
	return ""
}

func parseComposeCommand(cmd interface{}) string {
	if cmd == nil {
		return ""
	}
	switch c := cmd.(type) {
	case string:
		return c
	case []interface{}:
		parts := make([]string, len(c))
		for i, v := range c {
			parts[i] = fmt.Sprintf("%v", v)
		}
		return strings.Join(parts, " ")
	case []string:
		return strings.Join(c, " ")
	}
	return ""
}

func parseComposeHealthcheck(hc *composeHealthcheck) *HealthcheckConfig {
	cfg := &HealthcheckConfig{
		Interval: parseDurationToSeconds(hc.Interval),
		Timeout:  parseDurationToSeconds(hc.Timeout),
		Retries:  hc.Retries,
	}

	switch test := hc.Test.(type) {
	case string:
		cfg.Cmd = test
	case []interface{}:
		parts := make([]string, len(test))
		for i, v := range test {
			parts[i] = fmt.Sprintf("%v", v)
		}
		cfg.Cmd = strings.Join(parts, " ")
	case []string:
		cfg.Cmd = strings.Join(test, " ")
	}

	return cfg
}

func parseDurationToSeconds(d string) int {
	if d == "" {
		return 0
	}
	dur, err := time.ParseDuration(d)
	if err != nil {
		return 0
	}
	return int(dur.Seconds())
}

func normalizePort(p string) string {
	// Already in "host:container" or "host:container/protocol" format
	if strings.Contains(p, ":") {
		return p
	}
	// Could be just "80" or "80/tcp" - treat as container port
	return p
}

func normalizeRestart(r string) string {
	switch r {
	case "no":
		return "no"
	case "always":
		return "always"
	case "on-failure":
		return "on-failure"
	case "unless-stopped":
		return "unless-stopped"
	case "":
		return "always"
	default:
		return r
	}
}

func toStringSlice(v interface{}) []string {
	if v == nil {
		return nil
	}
	switch val := v.(type) {
	case string:
		return []string{val}
	case []interface{}:
		result := make([]string, len(val))
		for i, item := range val {
			result[i] = fmt.Sprintf("%v", item)
		}
		return result
	case []string:
		return val
	}
	return nil
}
