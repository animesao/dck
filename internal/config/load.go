package config

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/BurntSushi/toml"
)

func Load(path string) (*Config, string, error) {
	if path != "" {
		cfg, err := loadFile(path)
		return cfg, path, err
	}

	home, err := os.UserHomeDir()
	if err != nil {
		home = "/root"
	}
	candidates := []string{
		"dck.toml",
		filepath.Join(home, ".dck", "dck.toml"),
	}

	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			cfg, err := loadFile(p)
			return cfg, p, err
		}
	}

	return nil, "", fmt.Errorf("dck.toml not found (looked in current directory and ~/.dck/)")
}

func loadFile(path string) (*Config, error) {
	var cfg Config
	if _, err := toml.DecodeFile(path, &cfg); err != nil {
		return nil, fmt.Errorf("error parsing %s: %w", path, err)
	}
	return &cfg, nil
}
