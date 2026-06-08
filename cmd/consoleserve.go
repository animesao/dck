package cmd

import (
	"fmt"
	"io"
	"net"
	"os"
	"sync"

	"dck/internal/state"
)

func ConsoleServe(args []string) {
	if len(args) < 1 {
		os.Exit(1)
	}

	id := args[0]

	stdinW := os.NewFile(3, "stdinW")
	stdoutR := os.NewFile(4, "stdoutR")
	if stdinW == nil || stdoutR == nil {
		os.Exit(1)
	}
	defer stdinW.Close()
	defer stdoutR.Close()

	sockPath := state.ConsolePath(id)
	os.Remove(sockPath)

	listener, err := net.Listen("unix", sockPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "console-serve listen: %v\n", err)
		os.Exit(1)
	}
	defer os.Remove(sockPath)
	defer listener.Close()

	var mu sync.Mutex
	var clients []net.Conn

	go func() {
		buf := make([]byte, 4096)
		for {
			n, err := stdoutR.Read(buf)
			if err != nil {
				return
			}
			mu.Lock()
			for _, c := range clients {
				c.Write(buf[:n])
			}
			mu.Unlock()
		}
	}()

	for {
		conn, err := listener.Accept()
		if err != nil {
			break
		}

		mu.Lock()
		clients = append(clients, conn)
		mu.Unlock()

		go func(c net.Conn) {
			io.Copy(stdinW, c)
			c.Close()

			mu.Lock()
			for i, cl := range clients {
				if cl == c {
					clients = append(clients[:i], clients[i+1:]...)
					break
				}
			}
			mu.Unlock()
		}(conn)
	}
}
