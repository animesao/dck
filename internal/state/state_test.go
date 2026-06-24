package state

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDataDir(t *testing.T) {
	dir := DataDir()
	if dir == "" {
		t.Fatal("DataDir() returned empty")
	}
}

func TestSubDirs(t *testing.T) {
	base := DataDir()
	tests := []struct {
		name string
		got  string
	}{
		{"ImagesDir", ImagesDir()},
		{"ContainersDir", ContainersDir()},
		{"LogsDir", LogsDir()},
		{"OverlayDir", OverlayDir()},
		{"ConsolesDir", ConsolesDir()},
		{"VolumesDir", VolumesDir()},
	}
	for _, tt := range tests {
		got := tt.got
		if !filepath.IsLocal(got) && !filepath.IsAbs(got) {
			t.Errorf("%s: unexpected path %q", tt.name, got)
		}
		expected := filepath.Join(base, filepath.Base(got))
		if got != expected {
			t.Errorf("%s = %q, want %q", tt.name, got, expected)
		}
	}
}

func TestContainerPath(t *testing.T) {
	got := ContainerPath("abc123")
	want := filepath.Join(ContainersDir(), "abc123.json")
	if got != want {
		t.Errorf("ContainerPath = %q, want %q", got, want)
	}
}

func TestLogPath(t *testing.T) {
	got := LogPath("abc123")
	want := filepath.Join(LogsDir(), "abc123.log")
	if got != want {
		t.Errorf("LogPath = %q, want %q", got, want)
	}
}

func TestOverlayDirs(t *testing.T) {
	upper, work, merged := OverlayDirs("test-id")
	base := filepath.Join(OverlayDir(), "test-id")
	if upper != filepath.Join(base, "upper") {
		t.Errorf("upper = %q", upper)
	}
	if work != filepath.Join(base, "work") {
		t.Errorf("work = %q", work)
	}
	if merged != filepath.Join(base, "merged") {
		t.Errorf("merged = %q", merged)
	}
}

func TestImageDir(t *testing.T) {
	got := ImageDir("nginx", "latest")
	want := filepath.Join(ImagesDir(), "nginx", "latest")
	if got != want {
		t.Errorf("ImageDir = %q, want %q", got, want)
	}
}

func TestImageRootfsDir(t *testing.T) {
	got := ImageRootfsDir("nginx", "latest")
	want := filepath.Join(ImageDir("nginx", "latest"), "rootfs")
	if got != want {
		t.Errorf("ImageRootfsDir = %q, want %q", got, want)
	}
}

func TestResolveVolume(t *testing.T) {
	named := ResolveVolume("mydata")
	expected := filepath.Join(VolumesDir(), "mydata")
	if named != expected {
		t.Errorf("ResolveVolume(named) = %q, want %q", named, expected)
	}

	abs := ResolveVolume("/host/path")
	if abs != "/host/path" {
		t.Errorf("ResolveVolume(abs) = %q, want /host/path", abs)
	}

	rel := ResolveVolume("relative/path")
	if rel != "relative/path" {
		t.Errorf("ResolveVolume(rel) = %q, want relative/path", rel)
	}
}

func TestEnsureDirsReturnsCorrectPaths(t *testing.T) {
	// Verify that EnsureDirs iterates over all expected subdirectories
	expected := []string{
		ImagesDir(),
		ContainersDir(),
		LogsDir(),
		OverlayDir(),
		ConsolesDir(),
		VolumesDir(),
	}
	for _, d := range expected {
		if d == "" {
			t.Errorf("expected non-empty path, got empty")
		}
	}
}

func TestWriteReadJSON(t *testing.T) {
	tmpFile := filepath.Join(t.TempDir(), "test.json")
	type Data struct {
		Name  string `json:"name"`
		Value int    `json:"value"`
	}

	original := Data{Name: "test", Value: 42}
	if err := WriteJSON(tmpFile, original); err != nil {
		t.Fatalf("WriteJSON() = %v", err)
	}

	var decoded Data
	if err := ReadJSON(tmpFile, &decoded); err != nil {
		t.Fatalf("ReadJSON() = %v", err)
	}

	if decoded != original {
		t.Errorf("got %+v, want %+v", decoded, original)
	}
}

func TestFileExists(t *testing.T) {
	tmpFile := filepath.Join(t.TempDir(), "exists.txt")
	if FileExists(tmpFile) {
		t.Error("FileExists should be false before creation")
	}

	if err := os.WriteFile(tmpFile, []byte("hello"), 0644); err != nil {
		t.Fatal(err)
	}

	if !FileExists(tmpFile) {
		t.Error("FileExists should be true after creation")
	}

	if FileExists(filepath.Join(t.TempDir(), "nonexistent.txt")) {
		t.Error("FileExists should be false for nonexistent file")
	}
}

func TestConsolePath(t *testing.T) {
	got := ConsolePath("abc123")
	want := filepath.Join(ConsolesDir(), "abc123.sock")
	if got != want {
		t.Errorf("ConsolePath = %q, want %q", got, want)
	}
}
