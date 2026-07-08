package cmd

import (
	"flag"
	"fmt"
	"os"

	"dck/internal/container"
	"dck/internal/sftp"
)

func Sshkey(args []string) {
	fs := flag.NewFlagSet("sshkey", flag.ExitOnError)
	showPub := fs.Bool("pub", false, "Show public key only")
	showPath := fs.Bool("path", false, "Show private key path only")
	gen := fs.Bool("gen", false, "Generate new SSH keypair")
	fs.Parse(args)

	remaining := fs.Args()
	if len(remaining) < 1 {
		fmt.Println("Usage: dck sshkey [--pub|--path|--gen] <container>")
		os.Exit(1)
	}

	c, err := container.Load(remaining[0])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	if *gen {
		privPEM, pubSSH, err := sftp.GenerateClientKey()
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		c.SSHPublicKey = pubSSH

		privPath := ""
		if *showPath {
			fmt.Println(privPath)
			return
		}
		if *showPub {
			fmt.Print(pubSSH)
			return
		}
		fmt.Println("=== PRIVATE KEY (keep secret) ===")
		fmt.Println(privPEM)
		fmt.Println("=== PUBLIC KEY ===")
		fmt.Print(pubSSH)
		c.Save()
		return
	}

	if c.SSHPublicKey == "" {
		fmt.Printf("Container %s has no SSH keypair\n", c.ID[:12])
		fmt.Println("Generate one with: dck sshkey --gen " + c.ID[:12])
		os.Exit(1)
	}

	if *showPub {
		fmt.Print(c.SSHPublicKey)
		return
	}
	if *showPath {
		fmt.Println(c.SSHPrivateKeyPath)
		return
	}

	// Show full info
	fmt.Printf("Container: %s (%s)\n", c.Name, c.ID[:12])
	fmt.Printf("SSH Port: %d\n", c.SFTPPort)
	fmt.Println()
	fmt.Println("=== PRIVATE KEY PATH ===")
	fmt.Println(c.SSHPrivateKeyPath)
	fmt.Println()
	fmt.Println("=== PUBLIC KEY ===")
	fmt.Print(c.SSHPublicKey)
	fmt.Println()
	fmt.Println("Connect: ssh -p", c.SFTPPort, "-i", c.SSHPrivateKeyPath, "dck@host")
}
