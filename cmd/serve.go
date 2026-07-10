package cmd

import (
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	"dck/internal/api"
)

func Serve(args []string) {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	port := fs.Int("p", 2375, "API port")
	host := fs.String("H", "0.0.0.0", "API host")
	daemon := fs.Bool("d", false, "Run as daemon (background)")
	token := fs.String("token", "", "Authentication token (or DCK_TOKEN env)")

	fs.Parse(args)

	// Allow override via DCK_HOST env
	if envHost := os.Getenv("DCK_HOST"); envHost != "" {
		if h, p, err := parseHost(envHost); err == nil {
			*host = h
			*port = p
		}
	}

	// Token: flag > env var > disabled
	apiToken := *token
	if apiToken == "" {
		apiToken = os.Getenv("DCK_TOKEN")
	}
	if apiToken != "" {
		api.SetAuthToken(apiToken)
	}

	if *daemon {
		// Fork and run in background
		fmt.Printf("Daemon mode: starting on %s:%d...\n", *host, *port)
		// TODO: implement proper daemonization with background process
	}

	if err := api.StartServer(*port, *host); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func parseHost(s string) (string, int, error) {
	if strings.HasPrefix(s, "tcp://") {
		s = s[6:]
	}
	parts := strings.Split(s, ":")
	if len(parts) != 2 {
		return "", 0, fmt.Errorf("invalid host format: %s (expected host:port)", s)
	}
	port, err := strconv.Atoi(parts[1])
	if err != nil {
		return "", 0, fmt.Errorf("invalid port: %v", err)
	}
	return parts[0], port, nil
}
