package cmd

import (
	"flag"
	"fmt"
	"os"
	"text/tabwriter"
	"time"

	"dck/internal/orchestrator"
)

func Cluster(args []string) {
	if len(args) < 1 {
		printClusterUsage()
		os.Exit(1)
	}

	subcommand := args[0]
	subargs := args[1:]

	switch subcommand {
	case "init":
		clusterInit(subargs)
	case "join":
		clusterJoin(subargs)
	case "leave":
		clusterLeave(subargs)
	case "ls", "list":
		clusterList(subargs)
	default:
		fmt.Printf("unknown cluster command: %s\n", subcommand)
		printClusterUsage()
		os.Exit(1)
	}
}

func printClusterUsage() {
	fmt.Println(`Usage: dck cluster COMMAND

Manage clusters

Commands:
  init           Initialize a new cluster
  join <peer>    Join an existing cluster
  leave          Leave the cluster
  ls             List cluster nodes`)
}

func clusterInit(args []string) {
	fs := flag.NewFlagSet("cluster init", flag.ExitOnError)
	name := fs.String("name", "default", "Cluster name")
	bind := fs.String("bind", "0.0.0.0", "Bind address")
	port := fs.Int("port", 2375, "API port")
	fs.Parse(args)

	if err := orchestrator.InitCluster(*name, *bind, *port); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func clusterJoin(args []string) {
	if len(args) < 1 {
		fmt.Println("Usage: dck cluster join <peer_addr>")
		os.Exit(1)
	}

	peerAddr := args[0]
	bind := "0.0.0.0"
	port := 2375

	// Check for flags in remaining args
	fs := flag.NewFlagSet("cluster join", flag.ExitOnError)
	fs.StringVar(&bind, "bind", "0.0.0.0", "Bind address")
	fs.IntVar(&port, "port", 2375, "API port")
	fs.Parse(args[1:])

	if err := orchestrator.JoinCluster(peerAddr, bind, port); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func clusterLeave(args []string) {
	if err := orchestrator.LeaveCluster(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func clusterList(args []string) {
	nodes, err := orchestrator.ListNodes()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if len(nodes) == 0 {
		fmt.Println("No nodes in cluster")
		return
	}

	w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', 0)
	fmt.Fprintln(w, "ID\tNAME\tADDRESS\tROLE\tSTATE\tLAST SEEN")
	for _, n := range nodes {
		fmt.Fprintf(w, "%s\t%s\t%s:%d\t%s\t%s\t%s\n",
			shortID(n.ID),
			n.Name,
			n.Address, n.APIPort,
			n.Role,
			n.State,
			n.LastSeen.Format("15:04:05"),
		)
	}
	w.Flush()
}

func shortID(id string) string {
	if len(id) > 8 {
		return id[:8]
	}
	return id
}

// Ensure the import is used
var _ = time.Now
