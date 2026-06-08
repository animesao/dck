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
	Restart     string            `toml:"restart,omitempty"`
	Hostname    string            `toml:"hostname,omitempty"`
	Healthcheck *HealthcheckConfig `toml:"healthcheck,omitempty"`
}

type Config struct {
	Container map[string]ContainerConfig `toml:"container"`
}
