package backend

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
)

// Remote app-server proxy speaks WebSocket, unlike the desktop stdio child.
// Keep the official primary remote daemon, and launch additional accounts at
// their own private sockets. Disconnecting SSH only closes these connections.
func startWebSocketChild(accountID, codexHome, executable string, env []string, inbound chan<- Inbound) (*Child, error) {
	args := []string{"app-server", "proxy"}
	if accountID != "primary" {
		socket, err := ensureAccountDaemon(codexHome, executable, env)
		if err != nil {
			return nil, err
		}
		args = append(args, "--sock", socket)
	}
	command := exec.Command(executable, args...)
	command.Env = env
	command.Stderr = os.Stderr
	stdin, err := command.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		_ = stdin.Close()
		return nil, err
	}
	if err := command.Start(); err != nil {
		_ = stdin.Close()
		_ = stdout.Close()
		return nil, err
	}
	pipe := &PipeConn{Reader: stdout, Writer: stdin, OnClose: func() { _ = command.Process.Kill() }}
	dialer := websocket.Dialer{
		HandshakeTimeout: 15 * time.Second,
		NetDialContext:   func(context.Context, string, string) (net.Conn, error) { return pipe, nil },
	}
	connection, _, err := dialer.Dial("ws://codex-app-server/rpc", nil)
	if err != nil {
		_ = pipe.Close()
		_ = command.Wait()
		return nil, fmt.Errorf("connect remote account %s: %w", accountID, err)
	}
	connection.SetReadLimit(64 * 1024 * 1024)
	child := &Child{
		accountID: accountID, exe: executable, args: args, env: env, inbound: inbound,
		command: command, websocket: connection, pending: make(map[string]chan response), closed: make(chan struct{}),
	}
	go func() {
		defer connection.Close()
		for {
			kind, raw, err := connection.ReadMessage()
			if err != nil {
				child.finished(err)
				return
			}
			if kind == websocket.TextMessage || kind == websocket.BinaryMessage {
				child.receiveRaw(raw)
			}
		}
	}()
	go child.waitLoop()
	return child, nil
}

func ensureAccountDaemon(codexHome, executable string, env []string) (string, error) {
	root := filepath.Join(codexHome, "app-server-control")
	if muxHome := environmentValue(env, "CODEX_MUX_HOME"); muxHome != "" {
		digest := sha256.Sum256([]byte(codexHome))
		root = filepath.Join(muxHome, "sockets", fmt.Sprintf("%x", digest[:6]))
	}
	if err := os.MkdirAll(root, 0o700); err != nil {
		return "", err
	}
	if err := os.Chmod(root, 0o700); err != nil {
		return "", err
	}
	socket := filepath.Join(root, "personal-work.sock")
	// Unix socket paths are limited to about 104 bytes on macOS. The installer
	// uses a short state root; fail explicitly instead of selecting another home.
	if len(socket) > 100 {
		return "", fmt.Errorf("remote socket path is too long; use a shorter CODEX_MUX_HOME: %s", socket)
	}
	lock, err := os.OpenFile(socket+".lock", os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return "", err
	}
	defer lock.Close()
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); err != nil {
		return "", err
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	if socketReady(socket) {
		return socket, nil
	}
	if info, err := os.Lstat(socket); err == nil {
		if info.Mode()&os.ModeSocket == 0 {
			return "", fmt.Errorf("refusing to replace non-socket %s", socket)
		}
		if err := os.Remove(socket); err != nil {
			return "", err
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	log, err := os.OpenFile(filepath.Join(root, "personal-work.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return "", err
	}
	defer log.Close()
	command := exec.Command(executable, "-c", "features.code_mode_host=true", "app-server", "--listen", "unix://"+socket)
	command.Env = env
	command.Stdout = log
	command.Stderr = log
	command.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err := command.Start(); err != nil {
		return "", fmt.Errorf("start remote account daemon: %w", err)
	}
	if err := os.WriteFile(filepath.Join(root, "personal-work.pid"), []byte(strconv.Itoa(command.Process.Pid)+"\n"), 0o600); err != nil {
		_ = command.Process.Kill()
		_ = command.Wait()
		return "", fmt.Errorf("record remote account daemon: %w", err)
	}
	exited := make(chan error, 1)
	go func() { exited <- command.Wait() }()
	deadline := time.NewTimer(15 * time.Second)
	defer deadline.Stop()
	tick := time.NewTicker(50 * time.Millisecond)
	defer tick.Stop()
	for {
		select {
		case err := <-exited:
			return "", fmt.Errorf("remote account daemon exited before opening socket: %v; see %s", err, log.Name())
		case <-deadline.C:
			_ = command.Process.Kill()
			return "", fmt.Errorf("remote account daemon did not open socket; see %s", log.Name())
		case <-tick.C:
			if socketReady(socket) {
				return socket, nil
			}
		}
	}
}

func socketReady(path string) bool {
	connection, err := net.DialTimeout("unix", path, 200*time.Millisecond)
	if err != nil {
		return false
	}
	_ = connection.Close()
	return true
}
