package container

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"time"
)

const MaxLogSize = 10 * 1024 * 1024

func RotateLogFile(path string) {
	info, err := os.Stat(path)
	if err != nil || info.Size() < MaxLogSize {
		return
	}
	rotated := path + ".1"
	os.Remove(rotated)
	os.Rename(path, rotated)
}

func (c *Container) Logs(follow bool) error {
	f, err := os.Open(c.LogFile())
	if err != nil {
		return fmt.Errorf("open log: %w", err)
	}
	defer f.Close()

	if follow {
		return c.followLogs(f)
	}

	_, err = io.Copy(os.Stdout, f)
	return err
}

func (c *Container) followLogs(r io.ReadSeeker) error {
	r.Seek(0, io.SeekEnd)
	reader := bufio.NewReader(r)

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				c.dataMu.RLock()
				running := c.Status == Running
				c.dataMu.RUnlock()
				if !running {
					return nil
				}
				time.Sleep(100 * time.Millisecond)
				continue
			}
			return err
		}
		fmt.Print(line)
	}
}
