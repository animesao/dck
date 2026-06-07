package container

import (
	"os"
	"time"

	"dck/internal/state"
)

type Container struct {
	ID         string        `json:"id"`
	Name       string        `json:"name"`
	ImageName  string        `json:"image_name"`
	ImageTag   string        `json:"image_tag"`
	PID        int           `json:"pid"`
	Status     Status        `json:"status"`
	Cmd        []string      `json:"cmd"`
	CreatedAt  time.Time     `json:"created_at"`
	Ports      []PortMap     `json:"ports,omitempty"`
	Volumes    []VolumeMount `json:"volumes,omitempty"`
	Env        []string      `json:"env,omitempty"`
	Hostname   string        `json:"hostname,omitempty"`
	Restart    string        `json:"restart,omitempty"`
	IP         string        `json:"ip,omitempty"`
}

type Status string

const (
	Created Status = "created"
	Running Status = "running"
	Stopped Status = "stopped"
)

type PortMap struct {
	HostPort      int    `json:"host_port"`
	ContainerPort int    `json:"container_port"`
	Protocol      string `json:"protocol"`
}

type VolumeMount struct {
	Source string `json:"source"`
	Target string `json:"target"`
}

type CreateOpts struct {
	Name        string
	Cmd         []string
	Ports       []PortMap
	Volumes     []VolumeMount
	Env         []string
	Hostname    string
	Restart     string
	Detach      bool
	Interactive bool
	TTY         bool
	RemoveOnExit bool
}

func (c *Container) Save() error {
	return state.WriteJSON(state.ContainerPath(c.ID), c)
}

func (c *Container) DeleteState() error {
	return os.Remove(state.ContainerPath(c.ID))
}

func (c *Container) LogFile() string {
	return state.LogPath(c.ID)
}

func (c *Container) OverlayDirs() (upper, work, merged string) {
	return state.OverlayDirs(c.ID)
}
