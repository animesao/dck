package image

import (
	"os"
	"path/filepath"
	"strings"

	"dck/internal/state"
)

func SaveToStore(img *Image) error {
	imgDir := state.ImageDir(img.Name, img.Tag)
	return state.WriteJSON(filepath.Join(imgDir, "manifest.json"), img)
}

func LoadFromStore(name, tag string) *Image {
	path := filepath.Join(state.ImageDir(name, tag), "manifest.json")
	if !state.FileExists(path) {
		return nil
	}
	var img Image
	if err := state.ReadJSON(path, &img); err != nil {
		return nil
	}
	return &img
}

func ListImages() ([]Image, error) {
	imagesDir := state.ImagesDir()
	entries, err := os.ReadDir(imagesDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var images []Image
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		namespace := entry.Name()
		imgNames, err := os.ReadDir(filepath.Join(imagesDir, namespace))
		if err != nil {
			continue
		}
		for _, imgName := range imgNames {
			if !imgName.IsDir() {
				continue
			}
			fullName := namespace + "/" + imgName.Name()
			tags, err := os.ReadDir(filepath.Join(imagesDir, namespace, imgName.Name()))
			if err != nil {
				continue
			}
			for _, tag := range tags {
				if tag.IsDir() {
					img := LoadFromStore(fullName, tag.Name())
					if img != nil {
						images = append(images, *img)
					}
				}
			}
		}
	}
	return images, nil
}

func RemoveImage(name, tag string) error {
	return os.RemoveAll(state.ImageDir(name, tag))

}

func HasImage(name, tag string) bool {
	return state.FileExists(filepath.Join(state.ImageDir(name, tag), "manifest.json"))
}

func parseRef(ref string) (name, tag string) {
	tag = "latest"
	if i := strings.LastIndex(ref, ":"); i > 0 && strings.LastIndex(ref, "/") < i {
		tag = ref[i+1:]
		ref = ref[:i]
	}
	if !strings.Contains(ref, "/") {
		ref = "library/" + ref
	}
	return ref, tag
}
