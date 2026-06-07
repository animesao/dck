package container

import (
	"bufio"
	"fmt"
	"io"
	"os"
)

func (c *Container) Logs(follow bool) error {
	f, err := os.Open(c.LogFile())
	if err != nil {
		return fmt.Errorf("open log: %w", err)
	}
	defer f.Close()

	if follow {
		return followLogs(f)
	}

	_, err = io.Copy(os.Stdout, f)
	return err
}

func followLogs(r io.ReadSeeker) error {
	r.Seek(0, io.SeekEnd)
	reader := bufio.NewReader(r)

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				continue
			}
			return err
		}
		fmt.Print(line)
	}
}
