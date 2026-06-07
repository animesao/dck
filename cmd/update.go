package cmd

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

func Update(args []string) {
	checkOnly := false
	for _, a := range args {
		if a == "--check" || a == "-c" {
			checkOnly = true
		}
	}

	fmt.Printf("Current version: %s\n", version)

	latest, err := fetchLatestVersion()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error checking for updates: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Latest version:  %s\n", latest)

	if compareVersions(latest, version) <= 0 {
		fmt.Println("You are already up to date.")
		return
	}

	fmt.Printf("Update available: %s → %s\n", version, latest)

	if checkOnly {
		return
	}

	fmt.Print("Download and install? [y/N] ")
	var confirm string
	fmt.Scanln(&confirm)
	if confirm != "y" && confirm != "Y" {
		fmt.Println("Update cancelled.")
		return
	}

	fmt.Println("Downloading update...")
	installURL := repoURL + "/-/raw/main/install.sh"

	resp, err := http.Get(installURL)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to fetch installer: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		fmt.Fprintf(os.Stderr, "Installer returned HTTP %d\n", resp.StatusCode)
		os.Exit(1)
	}

	tmpFile := "/tmp/dck-install.sh"
	f, err := os.Create(tmpFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create temp file: %v\n", err)
		os.Exit(1)
	}
	io.Copy(f, resp.Body)
	f.Close()
	os.Chmod(tmpFile, 0755)

	cmd := exec.Command("sudo", tmpFile)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	if err := cmd.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "Update failed: %v\n", err)
		os.Exit(1)
	}

	os.Remove(tmpFile)
	fmt.Println("Update complete!")
}

func fetchLatestVersion() (string, error) {
	url := repoURL + "/-/raw/main/cmd/root.go"
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	for _, line := range strings.Split(string(body), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, `var version = "`) {
			v := strings.TrimPrefix(line, `var version = "`)
			v = strings.TrimSuffix(v, `"`)
			return v, nil
		}
	}

	return "", fmt.Errorf("could not determine latest version")
}

func compareVersions(a, b string) int {
	ap := strings.Split(strings.TrimLeft(a, "v"), ".")
	bp := strings.Split(strings.TrimLeft(b, "v"), ".")
	for i := 0; i < 3; i++ {
		var ai, bi int
		fmt.Sscanf(ap[i], "%d", &ai)
		fmt.Sscanf(bp[i], "%d", &bi)
		if ai < bi {
			return -1
		}
		if ai > bi {
			return 1
		}
	}
	return 0
}
