package cmd

import (
	"fmt"
	"io"
	"net"
	"os"
	"sync"

	"dck/internal/container"
	"dck/internal/state"
)

func ConsoleServe(args []string) {
	if len(args) < 1 {
		os.Exit(1)
	}

	id := args[0]
	logPath := state.LogPath(id)

	container.RotateLogFile(logPath)
	logFile, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		os.Exit(1)
	}
	defer logFile.Close()

	stdinW := os.NewFile(3, "stdinW")
	stdoutR := os.NewFile(4, "stdoutR")
	if stdinW == nil || stdoutR == nil {
		logFile.WriteString("[console-serve] failed: missing FDs\n")
		os.Exit(1)
	}
	defer stdinW.Close()
	defer stdoutR.Close()

	sockPath := state.ConsolePath(id)
	os.Remove(sockPath)

	listener, err := net.Listen("unix", sockPath)
	if err != nil {
		logFile.WriteString(fmt.Sprintf("[console-serve] listen error: %v\n", err))
		os.Exit(1)
	}
	defer os.Remove(sockPath)
	defer listener.Close()

	logFile.WriteString("[console-serve] started\n")

	var mu sync.Mutex
	var clients []net.Conn

	go func() {
		buf := make([]byte, 4096)
		for {
			n, err := stdoutR.Read(buf)
			if err != nil {
				logFile.WriteString(fmt.Sprintf("[console-serve] stdout read done: %v\n", err))
				return
			}

			logFile.Write(buf[:n])

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
			logFile.WriteString(fmt.Sprintf("[console-serve] listener done: %v\n", err))
			break
		}

		logFile.WriteString("[console-serve] client connected\n")

		mu.Lock()
		logContent, _ := os.ReadFile(logPath)
		if len(logContent) > 0 {
			conn.Write(logContent)
		}
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

	logFile.WriteString("[console-serve] exiting\n")
}
