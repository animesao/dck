package cmd

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
)

const dockerHubSearchURL = "https://hub.docker.com/v2/search/repositories/"

type searchResult struct {
	Count   int              `json:"count"`
	Results []searchRepoItem `json:"results"`
}

type searchRepoItem struct {
	Name        string `json:"repo_name"`
	Description string `json:"short_description"`
	Stars       int    `json:"star_count"`
	Pulls       int64  `json:"pull_count"`
	Official    bool   `json:"is_official"`
}

func Search(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "Usage: dck search <term>")
		os.Exit(1)
	}

	term := strings.Join(args, " ")
	u := fmt.Sprintf("%s?query=%s&page_size=25", dockerHubSearchURL, url.QueryEscape(term))

	resp, err := http.Get(u)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error searching: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		fmt.Fprintf(os.Stderr, "Error: Docker Hub returned HTTP %d\n", resp.StatusCode)
		os.Exit(1)
	}

	var sr searchResult
	if err := json.NewDecoder(resp.Body).Decode(&sr); err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing response: %v\n", err)
		os.Exit(1)
	}

	if sr.Count == 0 {
		fmt.Println("No results found")
		return
	}

	fmt.Printf("Found %d results for \"%s\":\n\n", sr.Count, term)
	for _, r := range sr.Results {
		official := ""
		if r.Official {
			official = " [official]"
		}
		desc := strings.TrimSpace(r.Description)
		if len(desc) > 80 {
			desc = desc[:77] + "..."
		}
		if desc == "" {
			desc = "(no description)"
		}
		fmt.Printf("  %s%s\n", r.Name, official)
		if desc != "" {
			fmt.Printf("    %s\n", desc)
		}
		fmt.Printf("    Stars: %d  Pulls: %d\n\n", r.Stars, r.Pulls)
	}
}
