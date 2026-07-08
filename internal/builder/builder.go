package builder

import (
	"archive/tar"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"dck/internal/image"
	"dck/internal/state"
)

type buildState struct {
	cfg     *BuildConfig
	rootfs  string // current rootfs directory
	lower   string // current lower layer(s) for overlay
	layers  []buildLayer
	config  imageConfig
	stackIdx int
}

type buildLayer struct {
	Digest   string `json:"digest"`
	Size     int    `json:"size"`
	CacheKey string `json:"cache_key,omitempty"`
	Command  string `json:"command,omitempty"`
}

type imageConfig struct {
	Created      string            `json:"created"`
	Author       string            `json:"author,omitempty"`
	Architecture string            `json:"architecture"`
	OS           string            `json:"os"`
	Config       imageConfigInner  `json:"config"`
	History      []imageHistory    `json:"history"`
	Rootfs       imageRootfs       `json:"rootfs"`
}

type imageConfigInner struct {
	Cmd         []string          `json:"Cmd,omitempty"`
	Entrypoint  []string          `json:"Entrypoint,omitempty"`
	Env         []string          `json:"Env,omitempty"`
	WorkingDir  string            `json:"WorkingDir,omitempty"`
	User        string            `json:"User,omitempty"`
	Labels      map[string]string `json:"Labels,omitempty"`
	ExposedPorts map[string]struct{} `json:"ExposedPorts,omitempty"`
	Volumes     map[string]struct{} `json:"Volumes,omitempty"`
	StopSignal  string            `json:"StopSignal,omitempty"`
	Healthcheck *healthConfig     `json:"Healthcheck,omitempty"`
	Shell       []string          `json:"Shell,omitempty"`
}

type healthConfig struct {
	Test     []string `json:"Test"`
	Interval string   `json:"Interval,omitempty"`
	Timeout  string   `json:"Timeout,omitempty"`
	Retries  int      `json:"Retries,omitempty"`
}

type imageHistory struct {
	Created   string `json:"created"`
	CreatedBy string `json:"created_by"`
	Comment   string `json:"comment,omitempty"`
}

type imageRootfs struct {
	Type    string   `json:"type"`
	DiffIDs []string `json:"diff_ids"`
}

func Build(cfg *BuildConfig) (*image.Image, error) {
	if runtime.GOOS != "linux" {
		return nil, fmt.Errorf("build is only supported on Linux")
	}

	if err := state.EnsureDirs(); err != nil {
		return nil, fmt.Errorf("ensure dirs: %w", err)
	}

	dfPath := cfg.Dockerfile
	if dfPath == "" {
		dfPath = filepath.Join(cfg.ContextDir, "Dockerfile")
	}

	insts, err := ParseDockerfile(dfPath)
	if err != nil {
		return nil, fmt.Errorf("parse dockerfile: %w", err)
	}

	if len(insts) == 0 {
		return nil, fmt.Errorf("no instructions in Dockerfile")
	}

	if insts[0].Type != From {
		return nil, fmt.Errorf("first instruction must be FROM")
	}

	buildTmp := filepath.Join(state.DataDir(), "build")
	os.MkdirAll(buildTmp, 0755)
	defer os.RemoveAll(buildTmp)

	var buildEnv []string
	// Apply --build-arg values
	for k, v := range cfg.BuildArgs {
		buildEnv = append(buildEnv, k+"="+v)
	}

	bs := &buildState{
		cfg: cfg,
		config: imageConfig{
			Created:      time.Now().UTC().Format(time.RFC3339),
			Architecture: "amd64",
			OS:           "linux",
			Config: imageConfigInner{
				Shell: []string{"/bin/sh", "-c"},
			},
			History: []imageHistory{},
			Rootfs: imageRootfs{
				Type: "layers",
			},
		},
		layers: []buildLayer{},
	}

	buildArgs := make(map[string]string)
	for k, v := range cfg.BuildArgs {
		buildArgs[k] = v
	}

	for i, inst := range insts {
		switch inst.Type {
		case From:
			if err := bs.handleFrom(inst, buildTmp); err != nil {
				return nil, fmt.Errorf("step %d (FROM): %w", i+1, err)
			}
		case Run:
			if err := bs.handleRun(inst, buildEnv, buildTmp); err != nil {
				return nil, fmt.Errorf("step %d (RUN): %w", i+1, err)
			}
		case Copy:
			if err := bs.handleCopy(inst, buildTmp); err != nil {
				return nil, fmt.Errorf("step %d (COPY): %w", i+1, err)
			}
		case Workdir:
			bs.handleWorkdir(inst)
		case Env:
			bs.handleEnv(inst)
		case Cmd:
			bs.handleCmd(inst)
		case Entrypoint:
			bs.handleEntrypoint(inst)
		case Expose:
			bs.handleExpose(inst)
		case Label:
			bs.handleLabel(inst)
		case User:
			bs.handleUser(inst)
		case Volume:
			bs.handleVolume(inst)
		case Shell:
			bs.handleShell(inst)
		case Arg:
			handleArg(inst, buildArgs)
		case StopSignal:
			bs.handleStopSignal(inst)
		case Healthcheck:
			bs.handleHealthcheck(inst)
		case Maintainer:
			bs.handleMaintainer(inst)
		case OnBuild:
			// ONBUILD is informational only; real execution happens when the image is used as base
			fmt.Println("  ONBUILD instruction recorded (not executed)")
		}

		// Record history
		bs.config.History = append(bs.config.History, imageHistory{
			Created:   time.Now().UTC().Format(time.RFC3339),
			CreatedBy: inst.Raw,
		})
	}

	return bs.finalize(buildTmp)
}

func (bs *buildState) handleFrom(inst Instruction, buildTmp string) error {
	ref := inst.Args[0]

	// Parse optional AS alias (skip for now)
	if len(inst.Args) > 1 && strings.ToUpper(inst.Args[1]) == "AS" {
		// Multi-stage alias - now we just use the image ref
	}

	img, err := image.Pull(ref)
	if err != nil {
		return fmt.Errorf("pull base image %s: %w", ref, err)
	}

	rootfs := state.ImageRootfsDir(img.Name, img.Tag)
	bs.rootfs = rootfs
	bs.lower = rootfs
	bs.stackIdx = 0

	// Inherit config from base image
	cfg, err := image.ReadConfig(img.Name, img.Tag)
	if err == nil && cfg != nil {
		if cfg.Config.Cmd != nil {
			bs.config.Config.Cmd = cfg.Config.Cmd
		}
		if cfg.Config.Entrypoint != nil {
			bs.config.Config.Entrypoint = cfg.Config.Entrypoint
		}
		if cfg.Config.Env != nil {
			bs.config.Config.Env = cfg.Config.Env
		}
		if cfg.Config.WorkingDir != "" {
			bs.config.Config.WorkingDir = cfg.Config.WorkingDir
		}
		if cfg.Config.User != "" {
			bs.config.Config.User = cfg.Config.User
		}
	}

	fmt.Printf("Step 1 : FROM %s\n", ref)
	return nil
}

func (bs *buildState) handleRun(inst Instruction, buildEnv []string, buildTmp string) error {
	step := len(bs.config.History) + 2

	// Parse RUN args into command string
	var cmdStr string
	if parsed, ok := GetExecForm(inst.Args); ok {
		// JSON exec form - join with spaces for shell, but we'll parse it back
		cmdStr = strings.Join(parsed, " ")
	} else {
		// Shell form
		cmdStr = strings.Join(inst.Args, " ")
	}

	fmt.Printf("Step %d : RUN %s\n", step, cmdStr)

	// Create temporary overlay to capture changes
	runID := fmt.Sprintf("run_%d", step)
	upperDir := filepath.Join(buildTmp, runID, "upper")
	workDir := filepath.Join(buildTmp, runID, "work")
	mergedDir := filepath.Join(buildTmp, runID, "merged")

	os.MkdirAll(upperDir, 0755)
	os.MkdirAll(workDir, 0755)
	os.MkdirAll(mergedDir, 0755)

	// Mount overlay: base image layers as lower, empty upper
	if err := mountOverlay(buildTmp, bs.lower, upperDir, workDir, mergedDir); err != nil {
		return fmt.Errorf("overlay mount: %w", err)
	}
	defer unmountOverlay(mergedDir)

	// Resolve the shell
	shell := bs.config.Config.Shell
	if len(shell) == 0 {
		shell = []string{"/bin/sh", "-c"}
	}
	// If the configured shell does not exist inside the rootfs, find an alternative
	if _, err := os.Stat(filepath.Join(mergedDir, shell[0])); os.IsNotExist(err) {
		for _, candidate := range []string{"/bin/sh", "/usr/bin/sh", "/bin/bash", "/usr/bin/bash", "/bin/dash", "/usr/bin/dash"} {
			if _, err2 := os.Stat(filepath.Join(mergedDir, candidate)); err2 == nil {
				shell = []string{candidate, "-c"}
				break
			}
		}
	}

	// Build environment
	env := os.Environ()
	env = append(env, buildEnv...)
	env = append(env, bs.config.Config.Env...)

	// Execute command in chroot
	var cmd *exec.Cmd
	if _, err := os.Stat(mergedDir); err == nil {
		cmd = exec.Command("unshare",
			"--fork", "--pid", "--mount", "--ipc", "--uts", "--",
			"chroot", mergedDir,
			shell[0], "-c", cmdStr,
		)
	} else {
		cmd = exec.Command(shell[0], "-c", cmdStr)
	}

	cmd.Dir = "/"
	cmd.Env = env
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("RUN command failed: %w", err)
	}

	// Create layer from upperdir changes
	layerFile := filepath.Join(buildTmp, runID, "layer.tar.gz")
	if err := createLayerFromDir(upperDir, layerFile); err != nil {
		return fmt.Errorf("create layer: %w", err)
	}

	layerHash, layerSize := hashFile(layerFile)
	layerDigest := "sha256:" + layerHash

	// Ensure in shared content-addressable cache
	if _, _, err := image.EnsureLayer(layerFile); err != nil {
		return fmt.Errorf("cache layer: %w", err)
	}

	bl := buildLayer{
		Digest:   layerDigest,
		Size:     layerSize,
		CacheKey: layerDigest,
		Command:  cmdStr,
	}
	bs.layers = append(bs.layers, bl)
	bs.config.Rootfs.DiffIDs = append(bs.config.Rootfs.DiffIDs, layerDigest)
	bs.stackIdx++

	// Update rootfs to extracted layer
	newRootfs := filepath.Join(buildTmp, fmt.Sprintf("rootfs_%d", bs.stackIdx))
	os.RemoveAll(newRootfs)
	os.MkdirAll(newRootfs, 0755)
	if err := extractLayer(layerFile, newRootfs); err != nil {
		return fmt.Errorf("extract layer: %w", err)
	}

	// Also apply on top of existing rootfs
	if err := extractLayer(layerFile, bs.rootfs); err != nil {
		return fmt.Errorf("apply layer: %w", err)
	}

	bs.lower = fmt.Sprintf("%s:%s", bs.rootfs, newRootfs)

	return nil
}

func (bs *buildState) handleCopy(inst Instruction, buildTmp string) error {
	step := len(bs.config.History) + 2

	// Parse COPY: COPY <src>... <dst>
	// Handle --chown flag
	args := inst.Args
	chown := ""
	if strings.HasPrefix(args[0], "--chown=") {
		chown = strings.TrimPrefix(args[0], "--chown=")
		args = args[1:]
	} else if strings.HasPrefix(args[0], "--") {
		args = args[1:]
	}

	if len(args) < 2 {
		return fmt.Errorf("COPY requires at least source and destination")
	}

	srcs := args[:len(args)-1]
	dst := args[len(args)-1]

	fmt.Printf("Step %d : COPY %v %s\n", step, srcs, dst)

	// Resolve destination
	dstPath := filepath.Join(bs.rootfs, dst)
	os.MkdirAll(dstPath, 0755)

	// Create temp dir to track what was copied
	copyDir := filepath.Join(buildTmp, fmt.Sprintf("copy_%d", step))
	os.RemoveAll(copyDir)
	os.MkdirAll(copyDir, 0755)

	for _, src := range srcs {
		srcPath := filepath.Join(bs.cfg.ContextDir, src)

		// Copy to both the rootfs and the tracking dir
		if err := copyRecursive(srcPath, filepath.Join(dstPath, filepath.Base(src))); err != nil {
			return fmt.Errorf("copy %s: %w", src, err)
		}
		if err := copyRecursive(srcPath, filepath.Join(copyDir, filepath.Base(src))); err != nil {
			return fmt.Errorf("copy cache %s: %w", src, err)
		}
	}

	// Handle --chown if specified (chown recursively)
	if chown != "" {
		for _, src := range srcs {
			dstTarget := filepath.Join(dstPath, filepath.Base(src))
			exec.Command("chown", "-R", chown, dstTarget).Run()
		}
	}

	// Create layer from copied files
	layerFile := filepath.Join(buildTmp, fmt.Sprintf("copy_%d.tar.gz", step))
	if err := createLayerFromDir(copyDir, layerFile); err != nil {
		return fmt.Errorf("create layer: %w", err)
	}

	layerHash, layerSize := hashFile(layerFile)
	layerDigest := "sha256:" + layerHash

	bl := buildLayer{
		Digest:   layerDigest,
		Size:     layerSize,
		CacheKey: layerDigest,
		Command:  fmt.Sprintf("COPY %v %s", srcs, dst),
	}
	bs.layers = append(bs.layers, bl)
	bs.config.Rootfs.DiffIDs = append(bs.config.Rootfs.DiffIDs, layerDigest)
	bs.stackIdx++

	return nil
}

func (bs *buildState) handleWorkdir(inst Instruction) {
	step := len(bs.config.History) + 2
	dir := strings.Join(inst.Args, " ")

	if !filepath.IsAbs(dir) {
		if bs.config.Config.WorkingDir != "" {
			dir = filepath.Join(bs.config.Config.WorkingDir, dir)
		}
	}

	bs.config.Config.WorkingDir = dir
	// Create directory in rootfs
	os.MkdirAll(filepath.Join(bs.rootfs, dir), 0755)

	fmt.Printf("Step %d : WORKDIR %s\n", step, dir)
}

func (bs *buildState) handleEnv(inst Instruction) {
	step := len(bs.config.History) + 2

	if len(inst.Args) >= 2 && !strings.Contains(inst.Args[0], "=") {
		// ENV KEY VAL format
		bs.config.Config.Env = append(bs.config.Config.Env, inst.Args[0]+"="+inst.Args[1])
		fmt.Printf("Step %d : ENV %s=%s\n", step, inst.Args[0], inst.Args[1])
	} else {
		// ENV KEY=VAL [KEY2=VAL2 ...] format
		for _, arg := range inst.Args {
			if strings.Contains(arg, "=") {
				bs.config.Config.Env = append(bs.config.Config.Env, arg)
				fmt.Printf("Step %d : ENV %s\n", step, arg)
			}
		}
	}
}

func (bs *buildState) handleCmd(inst Instruction) {
	if parsed, ok := GetExecForm(inst.Args); ok {
		bs.config.Config.Cmd = parsed
	} else {
		// Shell form - wrap with shell
		shell := bs.config.Config.Shell
		if len(shell) == 0 {
			shell = []string{"/bin/sh", "-c"}
		}
		cmdLine := strings.Join(inst.Args, " ")
		bs.config.Config.Cmd = append(shell, cmdLine)
	}
}

func (bs *buildState) handleEntrypoint(inst Instruction) {
	if parsed, ok := GetExecForm(inst.Args); ok {
		bs.config.Config.Entrypoint = parsed
	} else {
		// Shell form
		entry := strings.Join(inst.Args, " ")
		bs.config.Config.Entrypoint = []string{"/bin/sh", "-c", entry}
	}
	// Reset CMD when entrypoint is set in exec form (Docker behavior)
}

func (bs *buildState) handleExpose(inst Instruction) {
	if bs.config.Config.ExposedPorts == nil {
		bs.config.Config.ExposedPorts = make(map[string]struct{})
	}
	for _, port := range inst.Args {
		// Handle both "80" and "80/tcp" formats
		if strings.Contains(port, "/") {
			bs.config.Config.ExposedPorts[port] = struct{}{}
		} else {
			bs.config.Config.ExposedPorts[port+"/tcp"] = struct{}{}
		}
	}
}

func (bs *buildState) handleLabel(inst Instruction) {
	if bs.config.Config.Labels == nil {
		bs.config.Config.Labels = make(map[string]string)
	}
	for _, arg := range inst.Args {
		if parts := strings.SplitN(arg, "=", 2); len(parts) == 2 {
			bs.config.Config.Labels[parts[0]] = parts[1]
		}
	}
}

func (bs *buildState) handleUser(inst Instruction) {
	bs.config.Config.User = strings.Join(inst.Args, " ")
}

func (bs *buildState) handleVolume(inst Instruction) {
	if bs.config.Config.Volumes == nil {
		bs.config.Config.Volumes = make(map[string]struct{})
	}
	for _, vol := range inst.Args {
		// Handle both ["/path"] and /path formats
		v := strings.Trim(vol, "\"'")
		bs.config.Config.Volumes[v] = struct{}{}
	}
}

func (bs *buildState) handleShell(inst Instruction) {
	if parsed, ok := GetExecForm(inst.Args); ok {
		bs.config.Config.Shell = parsed
	}
}

func (bs *buildState) handleStopSignal(inst Instruction) {
	bs.config.Config.StopSignal = strings.Join(inst.Args, " ")
}

func (bs *buildState) handleHealthcheck(inst Instruction) {
	if len(inst.Args) == 0 {
		// HEALTHCHECK NONE - disable
		bs.config.Config.Healthcheck = nil
		return
	}

	hc := &healthConfig{}
	args := inst.Args
	for i := 0; i < len(args); i++ {
		switch strings.ToUpper(args[i]) {
		case "--INTERVAL":
			if i+1 < len(args) {
				i++
				hc.Interval = args[i]
			}
		case "--TIMEOUT":
			if i+1 < len(args) {
				i++
				hc.Timeout = args[i]
			}
		case "--RETRIES":
			if i+1 < len(args) {
				i++
				fmt.Sscanf(args[i], "%d", &hc.Retries)
			}
		default:
			// CMD or CMD-SHELL or NONE
			if strings.ToUpper(args[i]) == "NONE" {
				hc = nil
				break
			}
			if i < len(args) {
				hc.Test = args[i:]
				i = len(args)
			}
		}
	}
	if hc != nil {
		bs.config.Config.Healthcheck = hc
	}
}

func (bs *buildState) handleMaintainer(inst Instruction) {
	bs.config.Author = strings.Join(inst.Args, " ")
}

func handleArg(inst Instruction, buildArgs map[string]string) {
	// ARG name or ARG name=default
	argStr := strings.Join(inst.Args, " ")
	var name, defaultValue string
	if idx := strings.Index(argStr, "="); idx >= 0 {
		name = argStr[:idx]
		defaultValue = argStr[idx+1:]
	} else {
		name = argStr
	}

	if _, exists := buildArgs[name]; !exists {
		// Use default if not provided via --build-arg
		if defaultValue != "" {
			buildArgs[name] = defaultValue
		}
	}
}

func (bs *buildState) finalize(buildTmp string) (*image.Image, error) {
	// Create image directories
	name := bs.cfg.ImageName
	tag := bs.cfg.Tag
	if tag == "" {
		tag = "latest"
	}
	if !strings.Contains(name, "/") {
		name = "library/" + name
	}

	imgDir := state.ImageDir(name, tag)
	os.MkdirAll(imgDir, 0755)

	fmt.Printf("---\nCreating image %s/%s:%s with %d layers\n", name, tag, bs.cfg.Tag, len(bs.layers))

	// Ensure all layers are in shared content-addressable cache
	// and copy to image dir for backward compat
	for i, layer := range bs.layers {
		cachedPath := image.ResolveLayer(layer.Digest)
		if cachedPath == "" {
			return nil, fmt.Errorf("layer %d (%s) not found in cache", i, shortDigest(layer.Digest))
		}
		dstLayer := filepath.Join(imgDir, fmt.Sprintf("layer_%d.tar.gz", i))
		if err := copyFile(cachedPath, dstLayer); err != nil {
			return nil, fmt.Errorf("copy layer %d: %w", i, err)
		}
	}

	// Write config.json
	bs.config.Created = time.Now().UTC().Format(time.RFC3339)
	configData, err := json.Marshal(bs.config)
	if err != nil {
		return nil, fmt.Errorf("marshal config: %w", err)
	}
	configHash := sha256.Sum256(configData)
	configDigest := "sha256:" + hex.EncodeToString(configHash[:])
	if err := os.WriteFile(filepath.Join(imgDir, "config.json"), configData, 0644); err != nil {
		return nil, fmt.Errorf("write config: %w", err)
	}

	// Write manifest.json
	manifest := image.ManifestV2{
		SchemaVersion: 2,
		MediaType:     "application/vnd.docker.distribution.manifest.v2+json",
	}
	manifest.Config.MediaType = "application/vnd.docker.container.image.v1+json"
	manifest.Config.Size = len(configData)
	manifest.Config.Digest = configDigest

	for _, layer := range bs.layers {
		manifest.Layers = append(manifest.Layers, struct {
			MediaType string `json:"mediaType"`
			Size      int    `json:"size"`
			Digest    string `json:"digest"`
		}{
			MediaType: "application/vnd.docker.image.rootfs.diff.tar.gzip",
			Size:      layer.Size,
			Digest:    layer.Digest,
		})
	}

	manifestData, _ := json.Marshal(manifest)
	if err := os.WriteFile(filepath.Join(imgDir, "manifest.json"), manifestData, 0644); err != nil {
		return nil, fmt.Errorf("write manifest: %w", err)
	}

	// Extract rootfs for runtime use
	rootfsDir := state.ImageRootfsDir(name, tag)
	os.RemoveAll(rootfsDir)
	os.MkdirAll(rootfsDir, 0755)

	for i := range bs.layers {
		layerFile := filepath.Join(imgDir, fmt.Sprintf("layer_%d.tar.gz", i))
		if err := extractLayer(layerFile, rootfsDir); err != nil {
			return nil, fmt.Errorf("extract layer %d: %w", i, err)
		}
	}

	// Save image metadata
	img := &image.Image{Name: name, Tag: tag, Digest: configDigest}
	if err := image.SaveToStore(img); err != nil {
		return nil, fmt.Errorf("save image: %w", err)
	}

	shortName := filepath.Base(name)
	fmt.Printf("Successfully built %s:%s (%s)\n", shortName, tag, configDigest[:19])
	return img, nil
}

// Overlay helpers
func mountOverlay(buildTmp, lower, upper, work, merged string) error {
	if err := exec.Command("mount", "-t", "overlay", "overlay",
		"-o", fmt.Sprintf("lowerdir=%s,upperdir=%s,workdir=%s", lower, upper, work),
		merged).Run(); err != nil {
		return fmt.Errorf("mount overlay: %w", err)
	}
	return nil
}

func unmountOverlay(merged string) {
	exec.Command("umount", merged).Run()
}

func createLayerFromDir(srcDir, outputPath string) error {
	outFile, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer outFile.Close()

	gw := gzip.NewWriter(outFile)
	defer gw.Close()

	tw := tar.NewWriter(gw)
	defer tw.Close()

	return filepath.Walk(srcDir, func(path string, fi os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		relPath := strings.TrimPrefix(path, srcDir)
		relPath = strings.TrimPrefix(relPath, string(os.PathSeparator))
		if relPath == "" {
			return nil
		}

		hdr, err := tar.FileInfoHeader(fi, "")
		if err != nil {
			return err
		}
		hdr.Name = relPath
		if fi.IsDir() && len(relPath) > 0 {
			hdr.Name = relPath + "/"
		}

		if err := tw.WriteHeader(hdr); err != nil {
			return err
		}

		if !fi.Mode().IsRegular() {
			return nil
		}

		f, err := os.Open(path)
		if err != nil {
			return err
		}
		defer f.Close()

		_, err = io.Copy(tw, f)
		return err
	})
}

func hashFile(path string) (string, int) {
	f, err := os.Open(path)
	if err != nil {
		return "", 0
	}
	defer f.Close()

	h := sha256.New()
	size, _ := io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil)), int(size)
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

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}

func copyRecursive(src, dst string) error {
	srcInfo, err := os.Stat(src)
	if err != nil {
		return err
	}

	if srcInfo.IsDir() {
		os.MkdirAll(dst, srcInfo.Mode())
		entries, err := os.ReadDir(src)
		if err != nil {
			return err
		}
		for _, entry := range entries {
			srcPath := filepath.Join(src, entry.Name())
			dstPath := filepath.Join(dst, entry.Name())
			if err := copyRecursive(srcPath, dstPath); err != nil {
				return err
			}
		}
		return nil
	}

	return copyFile(src, dst)
}
