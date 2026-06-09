package config

type HealthcheckConfig struct {
	Cmd      string `toml:"cmd"`
	Interval int    `toml:"interval,omitempty"`
	Retries  int    `toml:"retries,omitempty"`
	Timeout  int    `toml:"timeout,omitempty"`
}

type ContainerConfig struct {
	Image       string            `toml:"image"`
	Command     string            `toml:"command,omitempty"`
	Ports       []string          `toml:"ports,omitempty"`
	Volumes     []string          `toml:"volumes,omitempty"`
	Env         map[string]string `toml:"env,omitempty"`
	EnvFile     string            `toml:"env_file,omitempty"`
	Restart     string            `toml:"restart,omitempty"`
	Hostname    string            `toml:"hostname,omitempty"`
	Memory      string            `toml:"memory,omitempty"`
	CPUs        float64           `toml:"cpus,omitempty"`
	WorkDir     string            `toml:"workdir,omitempty"`
	Healthcheck *HealthcheckConfig `toml:"healthcheck,omitempty"`
	Entrypoint  string            `toml:"entrypoint,omitempty"`
	NetworkMode string            `toml:"network_mode,omitempty"`
	Labels      map[string]string `toml:"labels,omitempty"`
	CapAdd      []string          `toml:"cap_add,omitempty"`
	CapDrop     []string          `toml:"cap_drop,omitempty"`
	User        string            `toml:"user,omitempty"`
	Readonly    bool              `toml:"readonly,omitempty"`
	NoNewPrivs  bool              `toml:"no_new_privs,omitempty"`
	Sysctls     map[string]string `toml:"sysctls,omitempty"`
	Ulimits     map[string]string `toml:"ulimits,omitempty"`
	DNS         []string          `toml:"dns,omitempty"`
}

type Config struct {
	Container map[string]ContainerConfig `toml:"container"`
}
