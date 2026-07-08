package sftp

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"io"
	"io/fs"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/creack/pty"
	gosftp "github.com/pkg/sftp"
	gossh "golang.org/x/crypto/ssh"
)

type Server struct {
	RootDir       string
	Port          int
	Password      string
	ContainerPID  int
	ContainerID   string
	AuthorizedKey string
	ConsoleSocket string
	ln            net.Listener
	done          chan struct{}
}

func New(rootDir string, port int, password string) *Server {
	return &Server{
		RootDir:  rootDir,
		Port:     port,
		Password: password,
		done:     make(chan struct{}),
	}
}

func (s *Server) checkPublicKey(c gossh.ConnMetadata, pubKey gossh.PublicKey) (*gossh.Permissions, error) {
	if s.AuthorizedKey == "" {
		return nil, fmt.Errorf("no authorized keys configured")
	}
	parsed, _, _, _, err := gossh.ParseAuthorizedKey([]byte(s.AuthorizedKey))
	if err != nil {
		return nil, fmt.Errorf("invalid authorized key")
	}
	if string(parsed.Marshal()) == string(pubKey.Marshal()) {
		return nil, nil
	}
	return nil, fmt.Errorf("unauthorized key")
}

func (s *Server) WithAuthorizedKey(key string) *Server {
	s.AuthorizedKey = key
	return s
}

func (s *Server) WithContainerPID(pid int) *Server {
	s.ContainerPID = pid
	return s
}

func (s *Server) WithContainerID(id string) *Server {
	s.ContainerID = id
	return s
}

func (s *Server) WithConsoleSocket(socket string) *Server {
	s.ConsoleSocket = socket
	return s
}

func (s *Server) Start() error {
	config := &gossh.ServerConfig{
		PasswordCallback: func(c gossh.ConnMetadata, pass []byte) (*gossh.Permissions, error) {
			if string(pass) == s.Password {
				return nil, nil
			}
			return nil, fmt.Errorf("password rejected")
		},
		PublicKeyCallback: s.checkPublicKey,
	}

	hostKey, err := generateHostKey()
	if err != nil {
		return fmt.Errorf("generate host key: %w", err)
	}
	config.AddHostKey(hostKey)

	ln, err := net.Listen("tcp", ":"+strconv.Itoa(s.Port))
	if err != nil {
		return fmt.Errorf("listen: %w", err)
	}
	s.ln = ln

	go s.acceptLoop(config)
	return nil
}

func (s *Server) acceptLoop(config *gossh.ServerConfig) {
	defer close(s.done)
	for {
		conn, err := s.ln.Accept()
		if err != nil {
			break
		}
		go s.handleConn(conn, config)
	}
}

func (s *Server) handleConn(conn net.Conn, config *gossh.ServerConfig) {
	defer conn.Close()

	sshConn, chans, reqs, err := gossh.NewServerConn(conn, config)
	if err != nil {
		return
	}
	defer sshConn.Close()

	go gossh.DiscardRequests(reqs)

	for newChannel := range chans {
		if newChannel.ChannelType() != "session" {
			newChannel.Reject(gossh.UnknownChannelType, "unknown channel type")
			continue
		}

		ch, reqs2, err := newChannel.Accept()
		if err != nil {
			continue
		}

		go s.handleSession(ch, reqs2)
	}
}

func (s *Server) handleSession(ch gossh.Channel, reqs <-chan *gossh.Request) {
	defer ch.Close()

	var ptyReq *gossh.Request

	for req := range reqs {
		switch req.Type {
		case "subsystem":
			if len(req.Payload) >= 4 && string(req.Payload[4:]) == "sftp" {
				req.Reply(true, nil)
				s.handleSFTP(ch)
				return
			}
			req.Reply(false, nil)

		case "pty-req":
			ptyReq = req
			req.Reply(true, nil)

		case "window-change":
			if ptyReq != nil {
				req.Reply(true, nil)
			} else if req.WantReply {
				req.Reply(false, nil)
			}

		case "shell":
			req.Reply(true, nil)
			s.handleShell(ch, ptyReq)
			return

		case "exec":
			req.Reply(true, nil)
			cmd := string(req.Payload[4:])
			s.handleExec(ch, cmd)
			return

		default:
			if req.WantReply {
				req.Reply(false, nil)
			}
		}
	}
}

func (s *Server) handleSFTP(ch gossh.Channel) {
	handlers := &sftpHandlers{root: s.RootDir}
	rs := gosftp.NewRequestServer(ch, gosftp.Handlers{
		FileGet:  handlers,
		FilePut:  handlers,
		FileCmd:  handlers,
		FileList: handlers,
	})
	defer rs.Close()
	rs.Serve()
}

func (s *Server) findContainerPID() int {
	if s.ContainerPID > 0 {
		if syscall.Kill(s.ContainerPID, 0) == nil {
			return s.ContainerPID
		}
	}
	if s.ContainerID != "" {
		out, err := exec.Command("dck", "inspect", s.ContainerID).Output()
		if err == nil {
			pidStr := extractPID(string(out))
			if pidStr > 0 {
				s.ContainerPID = pidStr
				return pidStr
			}
		}
	}
	return 0
}

func extractPID(jsonData string) int {
	idx := strings.Index(jsonData, `"pid":`)
	if idx < 0 {
		return 0
	}
	rest := jsonData[idx+6:]
	end := strings.IndexAny(rest, ",}\n")
	if end < 0 {
		return 0
	}
	pid, err := strconv.Atoi(strings.TrimSpace(rest[:end]))
	if err != nil {
		return 0
	}
	return pid
}

func (s *Server) handleShell(ch gossh.Channel, ptyReq *gossh.Request) {
	// Try connecting to the container's console socket (like dck attach)
	if s.ConsoleSocket != "" {
		conn, err := net.DialTimeout("unix", s.ConsoleSocket, 2*time.Second)
		if err == nil {
			defer conn.Close()
			ch.Write([]byte("Connected to container console. Type 'stop' to stop the server.\r\n"))
			go func() {
				io.Copy(conn, ch)
			}()
			io.Copy(ch, conn)
			return
		}
	}

	pid := s.findContainerPID()
	shellCmd := "exec bash 2>/dev/null || exec sh"

	if pid <= 0 {
		ch.Write([]byte("Container PID not available, falling back to local shell\n"))
		shell := exec.Command("/bin/sh")
		shell.Stdin = ch
		shell.Stdout = ch
		shell.Stderr = ch.Stderr()
		shell.Run()
		return
	}

	nsArgs := []string{
		"-t", strconv.Itoa(pid),
		"-m", "-p", "-i", "-n",
		"--", "sh", "-c", shellCmd,
	}
	cmd := exec.Command("nsenter", nsArgs...)

	if ptyReq != nil && len(ptyReq.Payload) >= 4 {
		rows := uint16(ptyReq.Payload[5])<<8 | uint16(ptyReq.Payload[6])
		cols := uint16(ptyReq.Payload[3])<<8 | uint16(ptyReq.Payload[4])
		wp := pty.Winsize{Rows: rows, Cols: cols}
		f, err := pty.StartWithAttrs(cmd, &wp, nil)
		if err == nil {
			go func() {
				io.Copy(f, ch)
			}()
			io.Copy(ch, f)
			f.Close()
			cmd.Wait()
			return
		}
	}

	cmd.Stdin = ch
	cmd.Stdout = ch
	cmd.Stderr = ch.Stderr()
	cmd.Run()
}

func (s *Server) handleExec(ch gossh.Channel, command string) {
	pid := s.ContainerPID
	if pid <= 0 {
		shell := exec.Command("/bin/sh", "-c", command)
		shell.Stdin = ch
		shell.Stdout = ch
		shell.Stderr = ch.Stderr()
		shell.Run()
		return
	}

	nsArgs := []string{
		"-t", strconv.Itoa(pid),
		"-m", "-p", "-i", "-n",
		"--",
		"sh", "-c", command,
	}
	cmd := exec.Command("nsenter", nsArgs...)
	cmd.Stdin = ch
	cmd.Stdout = ch
	cmd.Stderr = ch.Stderr()

	cmd.Run()
}

func (s *Server) Stop() {
	if s.ln != nil {
		s.ln.Close()
		<-s.done
	}
}

func (s *Server) Addr() net.Addr {
	if s.ln == nil {
		return nil
	}
	return s.ln.Addr()
}

type sftpHandlers struct {
	root string
}

func (h *sftpHandlers) Fileread(r *gosftp.Request) (io.ReaderAt, error) {
	path := safePath(h.root, r.Filepath)
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	return f, nil
}

func (h *sftpHandlers) Filewrite(r *gosftp.Request) (io.WriterAt, error) {
	path := safePath(h.root, r.Filepath)
	os.MkdirAll(filepath.Dir(path), 0755)
	f, err := os.Create(path)
	if err != nil {
		return nil, err
	}
	return f, nil
}

func (h *sftpHandlers) Filecmd(r *gosftp.Request) error {
	path := safePath(h.root, r.Filepath)
	target := ""
	if r.Target != "" {
		target = safePath(h.root, r.Target)
	}

	switch r.Method {
	case "Setstat":
		return nil
	case "Rename":
		return os.Rename(path, target)
	case "Rmdir":
		return os.RemoveAll(path)
	case "Remove":
		return os.Remove(path)
	case "Mkdir":
		return os.MkdirAll(path, 0755)
	case "Symlink":
		return os.Symlink(target, path)
	case "Link":
		return os.Link(target, path)
	}
	return nil
}

func (h *sftpHandlers) Filelist(r *gosftp.Request) (gosftp.ListerAt, error) {
	path := safePath(h.root, r.Filepath)

	switch r.Method {
	case "List":
		entries, err := os.ReadDir(path)
		if err != nil {
			return nil, err
		}
		items := make([]os.FileInfo, 0, len(entries))
		for _, e := range entries {
			info, err := e.Info()
			if err != nil {
				continue
			}
			items = append(items, info)
		}
		return listerAt(items), nil

	case "Stat":
		info, err := os.Stat(path)
		if err != nil {
			return nil, err
		}
		return listerAt{info}, nil

	case "Readlink":
		target, err := os.Readlink(path)
		if err != nil {
			return nil, err
		}
		return listerAt{&linkInfo{name: target}}, nil
	}

	return nil, fmt.Errorf("unknown list method: %s", r.Method)
}

type listerAt []os.FileInfo

func (l listerAt) ListAt(ls []os.FileInfo, offset int64) (int, error) {
	if offset >= int64(len(l)) {
		return 0, io.EOF
	}
	n := copy(ls, l[offset:])
	if n < len(ls) {
		return n, io.EOF
	}
	return n, nil
}

type linkInfo struct {
	name string
}

func (l *linkInfo) Name() string       { return l.name }
func (l *linkInfo) Size() int64        { return 0 }
func (l *linkInfo) Mode() fs.FileMode  { return os.ModeSymlink | 0777 }
func (l *linkInfo) ModTime() time.Time { return time.Time{} }
func (l *linkInfo) IsDir() bool        { return false }
func (l *linkInfo) Sys() interface{}   { return nil }

func safePath(root, p string) string {
	p = filepath.Clean("/" + p)
	p = strings.TrimPrefix(p, "/")
	return filepath.Join(root, p)
}

func generateHostKey() (gossh.Signer, error) {
	keyPath := filepath.Join(os.TempDir(), "dck_sftp_hostkey")

	if data, err := os.ReadFile(keyPath); err == nil {
		return gossh.ParsePrivateKey(data)
	}

	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return nil, fmt.Errorf("generate rsa key: %w", err)
	}

	err = os.WriteFile(keyPath, pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(privateKey),
	}), 0600)
	if err != nil {
		return nil, fmt.Errorf("save host key: %w", err)
	}

	signer, err := gossh.NewSignerFromKey(privateKey)
	if err != nil {
		return nil, fmt.Errorf("create signer: %w", err)
	}

	return signer, nil
}

func GenerateClientKey() (privateKeyPEM string, publicKeySSH string, err error) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return "", "", fmt.Errorf("generate key: %w", err)
	}

	privBytes := x509.MarshalPKCS1PrivateKey(privateKey)
	privPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: privBytes,
	})

	pub, err := gossh.NewPublicKey(&privateKey.PublicKey)
	if err != nil {
		return "", "", fmt.Errorf("create public key: %w", err)
	}
	pubSSH := string(gossh.MarshalAuthorizedKey(pub))

	return string(privPEM), pubSSH, nil
}
