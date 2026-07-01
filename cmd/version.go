package cmd

import (
	_ "embed"
	"strings"
)

//go:embed VERSION
var versionFile string

var version string

func init() {
	if version == "" {
		version = strings.TrimSpace(versionFile)
	}
}
