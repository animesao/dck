package cmd

import (
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"syscall"

	"dck/internal/sftp"
)

func SFTPServe(args []string) {
	fs := flag.NewFlagSet("sftp-serve", flag.ExitOnError)
	root := fs.String("root", "", "Root directory to serve")
	port := fs.Int("port", 22000, "Port to listen on")
	password := fs.String("password", "dck", "SSH password")
	pid := fs.Int("pid", 0, "Container PID for nsenter shell access")
	pubkey := fs.String("pubkey", "", "Authorized SSH public key")
	fs.Parse(args)

	if *root == "" {
		fmt.Fprintln(os.Stderr, "Error: --root is required")
		os.Exit(1)
	}

	svr := sftp.New(*root, *port, *password)
	if *pid > 0 {
		svr.WithContainerPID(*pid)
	}
	if *pubkey != "" {
		svr.WithAuthorizedKey(*pubkey)
	}

	if err := svr.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	addr := svr.Addr()
	if addr != nil {
		if tcpAddr, ok := addr.(*net.TCPAddr); ok {
			fmt.Printf("SSH/SFTP server started on port %d\n", tcpAddr.Port)
		}
	}

	fmt.Println("Supported: sftp (file transfer) + shell (terminal access via nsenter)")

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	svr.Stop()
}
