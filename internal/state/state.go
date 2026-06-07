package state

import (
	"encoding/json"
	"os"
	"path/filepath"
)

func DataDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".dck")
}

func ImagesDir() string {
	return filepath.Join(DataDir(), "images")
}

func ContainersDir() string {
	return filepath.Join(DataDir(), "containers")
}

func LogsDir() string {
	return filepath.Join(DataDir(), "logs")
}

func OverlayDir() string {
	return filepath.Join(DataDir(), "overlay")
}

func ImageDir(name, tag string) string {
	return filepath.Join(ImagesDir(), name, tag)
}

func ImageRootfsDir(name, tag string) string {
	return filepath.Join(ImageDir(name, tag), "rootfs")
}

func ContainerPath(id string) string {
	return filepath.Join(ContainersDir(), id+".json")
}

func LogPath(id string) string {
	return filepath.Join(LogsDir(), id+".log")
}

func OverlayDirs(id string) (upper, work, merged string) {
	base := filepath.Join(OverlayDir(), id)
	return filepath.Join(base, "upper"),
		filepath.Join(base, "work"),
		filepath.Join(base, "merged")
}

func EnsureDirs() error {
	for _, d := range []string{DataDir(), ImagesDir(), ContainersDir(), LogsDir(), OverlayDir()} {
		if err := os.MkdirAll(d, 0755); err != nil {
			return err
		}
	}
	return nil
}

func WriteJSON(path string, v interface{}) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return json.NewEncoder(f).Encode(v)
}

func ReadJSON(path string, v interface{}) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return json.NewDecoder(f).Decode(v)
}

func FileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
