package container

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"text/tabwriter"

	"dck/internal/state"
)

func pidAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	_, err := os.Stat("/proc/" + strconv.Itoa(pid))
	return err == nil
}

func List(all bool) ([]*Container, error) {
	entries, err := os.ReadDir(state.ContainersDir())
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var containers []*Container
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		id := strings.TrimSuffix(e.Name(), ".json")
		c, err := Load(id)
		if err != nil {
			continue
		}
		if !all && c.Status != Running {
			continue
		}
		containers = append(containers, c)
	}
	return containers, nil
}

func PrintContainers(containers []*Container) {
	w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', 0)
	fmt.Fprintln(w, "ID\tIMAGE\tSTATUS\tNAME\tCMD\tSFTP\tFTP")
	for _, c := range containers {
		shortID := c.ID[:12]
		image := fmt.Sprintf("%s:%s", c.ImageName, c.ImageTag)
		cmd := strings.Join(c.Cmd, " ")
		if len(cmd) > 40 {
			cmd = cmd[:40] + "..."
		}
		sftpStr := "-"
		ftpStr := "-"
		if c.SFTPPort > 0 {
			sftpStr = fmt.Sprintf(":%d", c.SFTPPort)
		} else if c.EnableSFTP {
			sftpStr = "enabled"
		}
		if c.FTPPort > 0 {
			ftpStr = fmt.Sprintf(":%d", c.FTPPort)
		} else if c.EnableFTP {
			ftpStr = "enabled"
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
			shortID, image, c.Status, c.Name, cmd, sftpStr, ftpStr)
	}
	w.Flush()
}
