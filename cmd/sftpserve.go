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
	user := fs.String("user", "dck", "SFTP username")
	password := fs.String("password", "", "SFTP password")
	fs.Parse(args)

	if *root == "" {
		fmt.Fprintln(os.Stderr, "Error: --root is required")
		os.Exit(1)
	}
	if *password == "" {
		fmt.Fprintln(os.Stderr, "Error: --password is required")
		os.Exit(1)
	}

	svr := sftp.New(*root, *port, *user, *password)

	if err := svr.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	addr := svr.Addr()
	if addr != nil {
		if tcpAddr, ok := addr.(*net.TCPAddr); ok {
			fmt.Printf("SFTP server started on port %d\n", tcpAddr.Port)
		}
	}

	fmt.Printf("Connect: sftp://%s@host:%d password=%s\n", *user, *port, *password)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	svr.Stop()
}
