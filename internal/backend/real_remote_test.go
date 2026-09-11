package backend

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/b-nnett/codex-subscription-router/internal/protocol"
)

// Opt-in integration test uses empty temporary homes, never the user's login.
// It verifies the installed CLI's actual SSH WebSocket protocol and durable
// extra-account process behavior without connecting to any remote host.
func TestRealRemoteAppServerTransport(t *testing.T) {
	executable := os.Getenv("CODEX_MUX_TEST_REAL_CODEX")
	if executable == "" {
		t.Skip("set CODEX_MUX_TEST_REAL_CODEX to run isolated real-CLI transport test")
	}
	root, err := os.MkdirTemp("/tmp", "codex-pw-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(root)
	primary := filepath.Join(root, "primary")
	if err := os.MkdirAll(primary, 0o700); err != nil {
		t.Fatal(err)
	}
	env := withEnvironment(os.Environ(), "CODEX_HOME", primary)
	env = withEnvironment(env, "CODEX_SQLITE_HOME", primary)
	env = withEnvironment(env, "CODEX_MUX_HOME", filepath.Join(root, "state"))
	env = withEnvironment(env, "CODEX_MUX_TRANSPORT", "unix")
	log, err := os.Create(filepath.Join(root, "primary.log"))
	if err != nil {
		t.Fatal(err)
	}
	defer log.Close()
	daemon := exec.Command(executable, "app-server", "--listen", "unix://")
	daemon.Env, daemon.Stdout, daemon.Stderr = env, log, log
	if err := daemon.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = daemon.Process.Kill(); _ = daemon.Wait() }()
	deadline := time.Now().Add(10 * time.Second)
	ready := false
	for time.Now().Before(deadline) {
		paths, _ := filepath.Glob(filepath.Join(primary, "app-server-control", "*.sock"))
		for _, path := range paths {
			if socketReady(path) {
				ready = true
				break
			}
		}
		if ready {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	if !ready {
		data, _ := os.ReadFile(log.Name())
		t.Fatalf("temporary primary daemon did not start: %s", data)
	}
	inbound := make(chan Inbound, 100)
	check := func(id, home string) *Child {
		t.Helper()
		child, err := Start(id, home, primary, executable, []string{"app-server"}, env, inbound)
		if err != nil {
			t.Fatal(err)
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_, err = child.Request(ctx, "initialize", json.RawMessage(`{"clientInfo":{"name":"personal_work_transport_test","version":"1"},"capabilities":{"experimentalApi":true}}`))
		if err != nil {
			_ = child.Close()
			t.Fatal(err)
		}
		if err := child.Send(protocol.Message{Method: "initialized"}); err != nil {
			_ = child.Close()
			t.Fatal(err)
		}
		result, err := child.Request(ctx, "account/read", json.RawMessage(`{"refreshToken":false}`))
		if err != nil {
			_ = child.Close()
			t.Fatal(err)
		}
		var account struct {
			Account json.RawMessage `json:"account"`
		}
		if err := json.Unmarshal(result.Result, &account); err != nil || string(account.Account) != "null" {
			_ = child.Close()
			t.Fatalf("expected isolated signed-out account, result=%s, err=%v", result.Result, err)
		}
		return child
	}
	first := check("primary", primary)
	_ = first.Close()
	if err := daemon.Process.Signal(syscall.Signal(0)); err != nil {
		t.Fatalf("disconnect stopped primary daemon: %v", err)
	}
	secondary := filepath.Join(root, "secondary")
	if err := os.MkdirAll(secondary, 0o700); err != nil {
		t.Fatal(err)
	}
	second := check("secondary", secondary)
	defer second.Close()
	digest := sha256.Sum256([]byte(secondary))
	pidPath := filepath.Join(root, "state", "sockets", fmt.Sprintf("%x", digest[:6]), "personal-work.pid")
	pidText, err := os.ReadFile(pidPath)
	if err != nil {
		t.Fatal(err)
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(pidText)))
	if err != nil {
		t.Fatal(err)
	}
	process, err := os.FindProcess(pid)
	if err != nil {
		t.Fatal(err)
	}
	defer process.Kill()
	_ = second.Close()
	if err := process.Signal(syscall.Signal(0)); err != nil {
		t.Fatalf("disconnect stopped isolated daemon: %v", err)
	}
	third := check("secondary", secondary)
	_ = third.Close()
	after, err := os.ReadFile(pidPath)
	if err != nil || string(after) != string(pidText) {
		t.Fatalf("reconnect did not reuse isolated daemon: %s, %v", after, err)
	}
}
