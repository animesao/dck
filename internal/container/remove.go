package container

import (
	"fmt"
	"os"
	"path/filepath"

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

	c.cleanupNetwork()
	cleanupContainerCgroup(c.ID, c.CgroupPath)

	TeardownDiskLimit(state.OverlayDir(), c.ID)
	upper, _, merged := c.OverlayDirs()
	unmountOverlay(merged)
	os.RemoveAll(filepath.Dir(upper))
	os.Remove(c.LogFile())
	c.DeleteState()

	return nil
}
