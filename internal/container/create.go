package container

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"os"
	"os/exec"
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
	workdir := opts.WorkingDir
	if workdir == "" {
		workdir = "/"
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
		StartupScript: opts.StartupScript,
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
		DiskLimit:    opts.DiskLimit,
		WorkingDir:   workdir,
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

func SetupDiskLimit(overlayBase, id string, limitBytes int64) error {
	if limitBytes <= 0 {
		return nil
	}
	imgPath := filepath.Join(overlayBase, id, "disk.img")
	mnt := filepath.Join(overlayBase, id, "data")
	_ = os.MkdirAll(filepath.Dir(imgPath), 0755)

	// Create disk image if it doesn't exist
	if _, err := os.Stat(imgPath); os.IsNotExist(err) {
		f, err := os.Create(imgPath)
		if err != nil {
			return fmt.Errorf("create disk image: %w", err)
		}
		if err := f.Truncate(limitBytes); err != nil {
			f.Close()
			return fmt.Errorf("truncate disk image: %w", err)
		}
		f.Close()
		if out, err := exec.Command("mkfs.ext4", "-F", imgPath).CombinedOutput(); err != nil {
			return fmt.Errorf("mkfs.ext4: %s: %w", strings.TrimSpace(string(out)), err)
		}
	}

	// Mount disk image to data dir
	if !isMounted(mnt) {
		os.MkdirAll(mnt, 0755)
		if out, err := exec.Command("mount", "-o", "loop", imgPath, mnt).CombinedOutput(); err != nil {
			return fmt.Errorf("mount disk: %s: %w", strings.TrimSpace(string(out)), err)
		}
		// Create upper and work inside the mounted filesystem
		// (overlay requires upperdir and workdir on the same fs)
		os.MkdirAll(filepath.Join(mnt, "upper"), 0755)
		os.MkdirAll(filepath.Join(mnt, "work"), 0755)
	}
	return nil
}

func TeardownDiskLimit(overlayBase, id string) {
	mnt := filepath.Join(overlayBase, id, "data")
	if isMounted(mnt) {
		if err := exec.Command("umount", mnt).Run(); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: umount %s: %v\n", mnt, err)
		}
	}
}
