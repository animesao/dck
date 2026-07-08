package cmd

import (
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"syscall"

	"dck/internal/ftp"
)

func FTPServe(args []string) {
	fs := flag.NewFlagSet("ftp-serve", flag.ExitOnError)
	root := fs.String("root", "", "Root directory to serve")
	port := fs.Int("port", 23000, "Port to listen on")
	password := fs.String("password", "dck", "FTP password")
	fs.Parse(args)

	if *root == "" {
		fmt.Fprintln(os.Stderr, "Error: --root is required")
		os.Exit(1)
	}

	svr := ftp.New(*root, *port, *password)
	if err := svr.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	addr := svr.Addr()
	if addr != nil {
		if tcpAddr, ok := addr.(*net.TCPAddr); ok {
			fmt.Printf("FTP server started on port %d\n", tcpAddr.Port)
		}
	}

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	svr.Stop()
}
