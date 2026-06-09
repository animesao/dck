package container

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"dck/internal/image"
	"dck/internal/state"
)

func New(img *image.Image, opts CreateOpts) *Container {
	id := generateID()
	hostname := opts.Hostname
	if hostname == "" {
		hostname = id[:12]
	}
	name := opts.Name
	if name == "" {
		name = id[:12]
	}
	cmd := opts.Cmd
	if len(cmd) == 0 {
		if cfg, err := image.ReadConfig(img.Name, img.Tag); err == nil {
			if opts.Entrypoint != "" {
				cmd = append([]string{opts.Entrypoint}, cfg.Config.Cmd...)
			} else if len(cfg.Config.Entrypoint) > 0 {
				cmd = append(cfg.Config.Entrypoint, cfg.Config.Cmd...)
			} else {
				cmd = cfg.Config.Cmd
			}
		}
		if len(cmd) == 0 {
			cmd = []string{"/bin/sh"}
		}
	} else if opts.Entrypoint != "" {
		cmd = append([]string{opts.Entrypoint}, cmd...)
	}

	return &Container{
		ID:           id,
		Name:         name,
		ImageName:    img.Name,
		ImageTag:     img.Tag,
		Status:       Created,
		Cmd:          cmd,
		CreatedAt:    time.Now(),
		Ports:        opts.Ports,
		Volumes:      opts.Volumes,
		Env:          opts.Env,
		Hostname:     hostname,
		Restart:      opts.Restart,
		Detach:       opts.Detach,
		Interactive:  opts.Interactive,
		TTY:          opts.TTY,
		RemoveOnExit: opts.RemoveOnExit,
		MemoryLimit:  opts.MemoryLimit,
		CPUCount:     opts.CPUCount,
		Healthcheck:  opts.Healthcheck,
		Labels:       opts.Labels,
		CapAdd:       opts.CapAdd,
		CapDrop:      opts.CapDrop,
		User:         opts.User,
		ReadonlyRootfs: opts.ReadonlyRootfs,
		NoNewPrivileges: opts.NoNewPrivileges,
		Sysctls:      opts.Sysctls,
		DNS:          opts.DNS,
		NetworkMode:  opts.NetworkMode,
		Entrypoint:   opts.Entrypoint,
		Ulimits:      opts.Ulimits,
	}
}

func Load(id string) (*Container, error) {
	path := state.ContainerPath(id)
	if state.FileExists(path) {
		var c Container
		if err := state.ReadJSON(path, &c); err != nil {
			return nil, err
		}
		if c.Status == Running && !pidAlive(c.PID) {
			c.Status = Stopped
		}
		return &c, nil
	}

	entries, err := os.ReadDir(state.ContainersDir())
	if err != nil {
		return nil, fmt.Errorf("container %s not found", id)
	}
	for _, e := range entries {
		name := strings.TrimSuffix(e.Name(), ".json")
		if strings.HasPrefix(name, id) {
			var c Container
			if err := state.ReadJSON(filepath.Join(state.ContainersDir(), e.Name()), &c); err != nil {
				return nil, err
			}
			if c.Status == Running && !pidAlive(c.PID) {
				c.Status = Stopped
			}
			return &c, nil
		}
	}
	// Fallback: look up by name
	for _, e := range entries {
		var c Container
		if err := state.ReadJSON(filepath.Join(state.ContainersDir(), e.Name()), &c); err != nil {
			continue
		}
		if c.Name == id {
			if c.Status == Running && !pidAlive(c.PID) {
				c.Status = Stopped
			}
			return &c, nil
		}
	}
	return nil, fmt.Errorf("container %s not found", id)
}

func generateID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return hex.EncodeToString(b)
}

func FindByName(name string) *Container {
	all, _ := List(true)
	for _, c := range all {
		if c.Name == name {
			return c
		}
	}
	return nil
}

func SetupOverlay(rootfs, upper, work, merged string) error {
	for _, d := range []string{upper, work, merged} {
		if err := os.MkdirAll(d, 0755); err != nil {
			return err
		}
	}
	return mountOverlay(rootfs, upper, work, merged)
}
