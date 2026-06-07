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
	installURLs := []string{
		repoURL + "/-/raw/main/install.sh",
		"http://gitlab.com/animesao/dck/-/raw/main/install.sh",
	}

	var installBody []byte
	for _, url := range installURLs {
		resp, err := http.Get(url)
		if err != nil {
			continue
		}
		if resp.StatusCode != 200 {
			resp.Body.Close()
			continue
		}
		installBody, _ = io.ReadAll(resp.Body)
		resp.Body.Close()
		break
	}

	if installBody == nil {
		fmt.Fprintf(os.Stderr, "Failed to fetch installer from any URL\n")
		os.Exit(1)
	}

	tmpFile := "/tmp/dck-install.sh"
	if err := os.WriteFile(tmpFile, installBody, 0755); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create temp file: %v\n", err)
		os.Exit(1)
	}

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

func fetchURL(url string) (string, error) {
	client := &http.Client{
		Timeout: 10 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 3 {
				return fmt.Errorf("too many redirects")
			}
			return nil
		},
	}
	resp, err := client.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	return strings.TrimSpace(string(body)), err
}

func fetchLatestVersion() (string, error) {
	urls := []string{
		repoURL + "/-/raw/main/VERSION",
		"http://gitlab.com/animesao/dck/-/raw/main/VERSION",
	}
	var errs []string
	for _, url := range urls {
		v, err := fetchURL(url)
		if err == nil {
			return v, nil
		}
		errs = append(errs, fmt.Sprintf("%s: %v", url, err))
	}
	return "", fmt.Errorf("all attempts failed:\n  %s", strings.Join(errs, "\n  "))
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
