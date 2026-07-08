//go:build linux

package container

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"dck/internal/state"
)

func (c *Container) Remove(force bool) error {
	if c.Status == Running {
		if !force {
			return fmt.Errorf("cannot remove running container %s (use -f)", c.ID)
		}
		if err := c.Stop(); err != nil {
			return err
		}
	}

	// Remove named volumes
	for _, vol := range c.Volumes {
		if !strings.Contains(vol.Source, "/") && !strings.Contains(vol.Source, "\\") {
			volPath := state.ResolveVolume(vol.Source)
			os.RemoveAll(volPath)
		}
	}

	c.cleanupNetwork()
	cleanupContainerCgroup(c.ID, c.CgroupPath)

	upper, _, merged := c.OverlayDirs()
	unmountOverlay(merged)
	TeardownDiskLimit(state.OverlayDir(), c.ID)
	os.RemoveAll(filepath.Dir(upper))
	os.Remove(c.LogFile())
	c.DeleteState()
	EmitEvent(EventDestroy, c)

	return nil
}
