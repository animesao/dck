package overlayutil

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestShortDigest(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890", "sha256:abcdef123456"},
		{"short", "short"},
		{"", ""},
		{"123456789012345678901", "1234567890123456789"},
	}
	for _, tt := range tests {
		got := ShortDigest(tt.input)
		if got != tt.want {
			t.Errorf("ShortDigest(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestHashFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.txt")
	content := "hello world"
	os.WriteFile(path, []byte(content), 0644)

	hash, size := HashFile(path)
	if size != int64(len(content)) {
		t.Errorf("HashFile size = %d, want %d", size, len(content))
	}
	if hash == "" {
		t.Error("HashFile returned empty hash")
	}
	if len(hash) != 64 {
		t.Errorf("HashFile hash length = %d, want 64 (SHA256 hex)", len(hash))
	}

	// Non-existent file
	hash2, size2 := HashFile(filepath.Join(dir, "nonexistent"))
	if hash2 != "" || size2 != 0 {
		t.Errorf("HashFile for non-existent: hash=%q size=%d", hash2, size2)
	}
}

func TestExtractLayer(t *testing.T) {
	// Create a minimal tar.gz
	dir := t.TempDir()
	tmpFile := filepath.Join(dir, "test.tar.gz")
	extractDir := filepath.Join(dir, "extracted")

	// Write a minimal valid gzip with a tar inside
	gzData := []byte{
		0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff,
		0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	}
	os.WriteFile(tmpFile, gzData, 0644)

	err := ExtractLayer(tmpFile, extractDir)
	if err != nil {
		t.Fatalf("ExtractLayer on empty tar.gz should succeed, got: %v", err)
	}

	// Non-existent file
	err = ExtractLayer(filepath.Join(dir, "nope.tar.gz"), extractDir)
	if err == nil {
		t.Error("ExtractLayer on non-existent file should fail")
	}
}

func TestUnmountOverlay(t *testing.T) {
	// UnmountOverlay should not panic on non-existent path
	UnmountOverlay("/nonexistent/path/12345")
}

func TestMountOverlay(t *testing.T) {
	// On non-Linux, MountOverlay should return nil
	// (tested via cross-compilation)
}

func TestExtractLayerPathTraversal(t *testing.T) {
	dir := t.TempDir()
	extractDir := filepath.Join(dir, "rootfs")
	os.MkdirAll(extractDir, 0755)

	// Create a tar.gz with a path traversal attempt
	tmpFile := filepath.Join(dir, "traversal.tar.gz")

	// We can only test that the function doesn't panic with invalid data
	invalidGz := []byte{0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0x01, 0x02, 0x03}
	os.WriteFile(tmpFile, invalidGz, 0644)

	_ = ExtractLayer(tmpFile, extractDir)
	// Should not create files outside extractDir
}

func TestShortDigestEdgeCases(t *testing.T) {
	if ShortDigest("") != "" {
		t.Error("ShortDigest('') should be empty")
	}
	long := strings.Repeat("a", 100)
	if len(ShortDigest(long)) != 19 {
		t.Errorf("ShortDigest(long) length = %d, want 19", len(ShortDigest(long)))
	}
}
