package cmd

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

var baseURL = getBaseURL()

func getBaseURL() string {
	if m := os.Getenv("DCK_UPDATE_MIRROR"); m != "" {
		return strings.TrimRight(m, "/")
	}
	return repoURL
}

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
	body, err := fetchURL(baseURL + "/main/install.sh")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to fetch installer: %v\n", err)
		os.Exit(1)
	}

	tmpFile := "/tmp/dck-install.sh"
	if err := os.WriteFile(tmpFile, []byte(body), 0755); err != nil {
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
	body, err := fetchURLGo(url)
	if err == nil {
		return body, nil
	}
	body, err = fetchURLWithCurl(url)
	if err == nil {
		return body, nil
	}
	body, err = fetchURLWithWget(url)
	if err == nil {
		return body, nil
	}
	return "", fmt.Errorf("all methods failed")
}

func fetchURLGo(url string) (string, error) {
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

func fetchURLWithCurl(url string) (string, error) {
	var stderr bytes.Buffer
	cmd := exec.Command("curl", "-sL", url)
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("curl failed: %v (stderr: %s)", err, strings.TrimSpace(stderr.String()))
	}
	return strings.TrimSpace(string(out)), nil
}

func fetchURLWithWget(url string) (string, error) {
	var stderr bytes.Buffer
	cmd := exec.Command("wget", "-qO-", url)
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("wget failed: %v (stderr: %s)", err, strings.TrimSpace(stderr.String()))
	}
	return strings.TrimSpace(string(out)), nil
}

func fetchLatestVersion() (string, error) {
	url := baseURL + "/main/VERSION"
	v, err := fetchURL(url)
	if err == nil {
		return v, nil
	}
	// Last resort: try git ls-remote over SSH
	if v, err := fetchVersionViaGit(); err == nil {
		return v, nil
	}
	return "", err
}

func fetchVersionViaGit() (string, error) {
	var stderr bytes.Buffer
	cmd := exec.Command("git", "ls-remote", "--tags", "https://github.com/animesao/dck.git")
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("git ls-remote failed: %v (stderr: %s)", err, strings.TrimSpace(stderr.String()))
	}
	// Parse the last tag matching v*.*.*
	latest := ""
	for _, line := range strings.Split(string(out), "\n") {
		parts := strings.SplitN(line, "\t", 2)
		if len(parts) < 2 {
			continue
		}
		ref := parts[1]
		if strings.HasPrefix(ref, "refs/tags/v") {
			tag := strings.TrimPrefix(ref, "refs/tags/")
			if compareVersions(tag, latest) > 0 {
				latest = tag
			}
		}
	}
	if latest == "" {
		return "", fmt.Errorf("no version tags found")
	}
	return latest, nil
}

func compareVersions(a, b string) int {
	if a == "" && b == "" {
		return 0
	}
	if a == "" {
		return -1
	}
	if b == "" {
		return 1
	}

	ap := strings.Split(strings.TrimLeft(a, "v"), ".")
	bp := strings.Split(strings.TrimLeft(b, "v"), ".")
	max := len(ap)
	if len(bp) > max {
		max = len(bp)
	}
	for i := 0; i < max; i++ {
		var ai, bi int
		if i < len(ap) {
			fmt.Sscanf(ap[i], "%d", &ai)
		}
		if i < len(bp) {
			fmt.Sscanf(bp[i], "%d", &bi)
		}
		if ai < bi {
			return -1
		}
		if ai > bi {
			return 1
		}
	}
	return 0
}
