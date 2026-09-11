package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"

	"github.com/b-nnett/codex-subscription-router/internal/backend"
	"github.com/gorilla/websocket"
)

func isAppServerProxy(args []string) bool {
	// Intercept only the exact invocation emitted by the native SSH client.
	// Explicit sockets, help, and other tooling flags retain CLI semantics.
	return len(args) == 2 && args[0] == "app-server" && args[1] == "proxy"
}

// The native SSH transport sends a WebSocket handshake and frames through
// stdin/stdout. Translate those frames into the mux's JSONL stream without a
// TCP listener, tunnel, uploaded credential, or change to the official CLI.
func runRemoteProxy() error {
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	return bridgeRemoteProxy(os.Stdin, os.Stdout, func(ctx context.Context) *exec.Cmd {
		command := exec.CommandContext(ctx, executable, "app-server")
		command.Env = append(os.Environ(), "CODEX_MUX_TRANSPORT=unix", "CODEX_MUX_NO_CONTROL=1")
		return command
	})
}

func bridgeRemoteProxy(input io.ReadCloser, output io.WriteCloser, muxCommand func(context.Context) *exec.Cmd) error {
	pipe := &backend.PipeConn{Reader: input, Writer: output}
	reader := bufio.NewReaderSize(pipe, 64*1024)
	request, err := http.ReadRequest(reader)
	if err != nil {
		return fmt.Errorf("read SSH WebSocket handshake: %w", err)
	}
	if request.URL.Path != "/rpc" {
		return errors.New("SSH WebSocket endpoint must be /rpc")
	}
	response := &pipeResponseWriter{connection: pipe, buffered: bufio.NewReadWriter(reader, bufio.NewWriter(pipe)), header: make(http.Header)}
	upgrader := websocket.Upgrader{CheckOrigin: func(request *http.Request) bool { return request.Header.Get("Origin") == "" }}
	connection, err := upgrader.Upgrade(response, request, nil)
	if err != nil {
		return fmt.Errorf("upgrade SSH WebSocket: %w", err)
	}
	defer connection.Close()
	connection.SetReadLimit(64 * 1024 * 1024)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	command := muxCommand(ctx)
	command.Stderr = os.Stderr
	stdin, err := command.StdinPipe()
	if err != nil {
		return err
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		_ = stdin.Close()
		return err
	}
	if err := command.Start(); err != nil {
		_ = stdin.Close()
		_ = stdout.Close()
		return err
	}
	defer func() { _ = stdin.Close(); cancel(); _ = command.Wait() }()
	outputDone := make(chan error, 1)
	go func() {
		scanner := bufio.NewScanner(stdout)
		scanner.Buffer(make([]byte, 64*1024), 64*1024*1024)
		for scanner.Scan() {
			if err := connection.WriteMessage(websocket.TextMessage, scanner.Bytes()); err != nil {
				outputDone <- err
				_ = connection.Close()
				return
			}
		}
		outputDone <- scanner.Err()
		_ = connection.Close()
	}()
	for {
		kind, raw, err := connection.ReadMessage()
		if err != nil {
			select {
			case outputErr := <-outputDone:
				return outputErr
			default:
			}
			if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) || errors.Is(err, io.EOF) {
				return nil
			}
			return err
		}
		if kind != websocket.TextMessage && kind != websocket.BinaryMessage {
			continue
		}
		// JSON WebSocket messages may contain formatting whitespace or a
		// trailing newline. The child transport requires exactly one JSON line.
		var compact bytes.Buffer
		if err := json.Compact(&compact, raw); err != nil {
			return fmt.Errorf("invalid SSH JSON frame: %w", err)
		}
		if _, err := stdin.Write(append(compact.Bytes(), '\n')); err != nil {
			return err
		}
	}
}

type pipeResponseWriter struct {
	connection net.Conn
	buffered   *bufio.ReadWriter
	header     http.Header
}

func (w *pipeResponseWriter) Header() http.Header { return w.header }
func (w *pipeResponseWriter) WriteHeader(code int) {
	fmt.Fprintf(w.buffered, "HTTP/1.1 %d %s\r\n", code, http.StatusText(code))
	_ = w.header.Write(w.buffered)
	_, _ = w.buffered.WriteString("\r\n")
	_ = w.buffered.Flush()
}
func (w *pipeResponseWriter) Write(p []byte) (int, error) { return w.connection.Write(p) }
func (w *pipeResponseWriter) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	return w.connection, w.buffered, nil
}
