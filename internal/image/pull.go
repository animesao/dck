package image

import (
	"archive/tar"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"dck/internal/state"
)

const (
	registryURL = "https://registry-1.docker.io"
	authURL     = "https://auth.docker.io/token"
	authService = "registry.docker.io"
)

var httpClient = &http.Client{Timeout: 300 * time.Second}

type authResponse struct {
	Token       string `json:"token"`
	AccessToken string `json:"access_token"`
}

func Pull(ref string) (*Image, error) {
	if err := os.MkdirAll(state.ImagesDir(), 0755); err != nil {
		return nil, err
	}

	name, tag := parseRef(ref)
	if img := LoadFromStore(name, tag); img != nil {
		fmt.Printf("Image %s:%s already exists\n", name, tag)
		return img, nil
	}

	fmt.Printf("Pulling %s:%s...\n", name, tag)

	token, err := getToken(name)
	if err != nil {
		return nil, fmt.Errorf("auth: %w", err)
	}

	manifest, err := getManifest(name, tag, token)
	if err != nil {
		return nil, fmt.Errorf("manifest: %w", err)
	}

	configData, err := downloadBlob(name, manifest.Config.Digest, token)
	if err != nil {
		return nil, fmt.Errorf("config: %w", err)
	}

	var cfg ContainerConfig
	if err := json.Unmarshal(configData, &cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	rootfsDir := state.ImageRootfsDir(name, tag)
	layersDir := filepath.Join(state.ImageDir(name, tag), "layers")
	os.MkdirAll(layersDir, 0755)

	for i, layer := range manifest.Layers {
		fmt.Printf("  Layer %d/%d: %s\n", i+1, len(manifest.Layers), shortDigest(layer.Digest))
		cachePath := filepath.Join(layersDir, strings.ReplaceAll(layer.Digest, ":", "_"))

		if _, err := os.Stat(cachePath); os.IsNotExist(err) {
			if err := downloadBlobToFile(name, layer.Digest, token, cachePath); err != nil {
				return nil, fmt.Errorf("layer %d: %w", i, err)
			}
		}

		if err := extractLayer(cachePath, rootfsDir); err != nil {
			return nil, fmt.Errorf("extract layer %d: %w", i, err)
		}
	}

	saveConfig(state.ImageDir(name, tag), configData)

	img := &Image{Name: name, Tag: tag, Digest: manifest.Config.Digest}
	if err := SaveToStore(img); err != nil {
		return nil, err
	}

	fmt.Printf("Done: %s:%s\n", name, tag)
	return img, nil
}

func saveConfig(dir string, data []byte) error {
	return os.WriteFile(filepath.Join(dir, "config.json"), data, 0644)
}

func ReadConfig(name, tag string) (*ContainerConfig, error) {
	path := filepath.Join(state.ImageDir(name, tag), "config.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cfg ContainerConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}

func getToken(repo string) (string, error) {
	u := fmt.Sprintf("%s?service=%s&scope=repository:%s:pull", authURL, authService, repo)
	resp, err := httpClient.Get(u)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	var ar authResponse
	if err := json.NewDecoder(resp.Body).Decode(&ar); err != nil {
		return "", err
	}
	if ar.Token != "" {
		return ar.Token, nil
	}
	return ar.AccessToken, nil
}

func getManifest(repo, ref, token string) (*ManifestV2, error) {
	u := fmt.Sprintf("%s/v2/%s/manifests/%s", registryURL, repo, ref)
	req, _ := http.NewRequest("GET", u, nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/vnd.docker.distribution.manifest.v2+json")
	req.Header.Set("Accept", "application/vnd.oci.image.manifest.v1+json")

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	var m ManifestV2
	if err := json.NewDecoder(resp.Body).Decode(&m); err != nil {
		return nil, err
	}
	return &m, nil
}

func downloadBlob(repo, digest, token string) ([]byte, error) {
	u := fmt.Sprintf("%s/v2/%s/blobs/%s", registryURL, repo, digest)
	req, _ := http.NewRequest("GET", u, nil)
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	return io.ReadAll(resp.Body)
}

func downloadBlobToFile(repo, digest, token, dest string) error {
	u := fmt.Sprintf("%s/v2/%s/blobs/%s", registryURL, repo, digest)
	req, _ := http.NewRequest("GET", u, nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/vnd.docker.image.rootfs.diff.tar.gzip")

	resp, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = io.Copy(f, resp.Body)
	return err
}

func extractLayer(cachePath, rootfsDir string) error {
	f, err := os.Open(cachePath)
	if err != nil {
		return err
	}
	defer f.Close()

	gzr, err := gzip.NewReader(f)
	if err != nil {
		return fmt.Errorf("gzip: %w", err)
	}
	defer gzr.Close()

	tr := tar.NewReader(gzr)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}

		path := filepath.Join(rootfsDir, hdr.Name)
		if !strings.HasPrefix(path, filepath.Clean(rootfsDir)+string(os.PathSeparator)) {
			continue
		}

		switch hdr.Typeflag {
		case tar.TypeDir:
			os.MkdirAll(path, os.FileMode(hdr.Mode))
		case tar.TypeReg:
			os.MkdirAll(filepath.Dir(path), 0755)
			f, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, os.FileMode(hdr.Mode))
			if err != nil {
				return err
			}
			if _, err := io.Copy(f, tr); err != nil {
				f.Close()
				return err
			}
			f.Close()
		case tar.TypeSymlink:
			os.Remove(path)
			os.Symlink(hdr.Linkname, path)
		case tar.TypeLink:
			os.Remove(path)
			os.Link(filepath.Join(rootfsDir, hdr.Linkname), path)
		}
	}
	return nil
}

func shortDigest(d string) string {
	if len(d) > 19 {
		return d[:19]
	}
	return d
}


