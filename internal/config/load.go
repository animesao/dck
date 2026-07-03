package config

import (
	"fmt"

	"github.com/BurntSushi/toml"
)

func Load(path string) (*Config, string, error) {
	return LoadConfigOrCompose(path)
}

func loadFile(path string) (*Config, error) {
	var cfg Config
	if _, err := toml.DecodeFile(path, &cfg); err != nil {
		return nil, fmt.Errorf("error parsing %s: %w", path, err)
	}
	return &cfg, nil
}


