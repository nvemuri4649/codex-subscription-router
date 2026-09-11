package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net"
	"os/exec"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestRemoteProxyDetection(t *testing.T) {
	for _, test := range []struct {
		args []string
		want bool
	}{
		{[]string{"app-server", "proxy"}, true},
		{[]string{"-c", "x=true", "app-server", "proxy", "--sock", "/tmp/server.sock"}, false},
		{[]string{"app-server", "proxy", "--help"}, false},
		{[]string{"app-server"}, false},
		{[]string{"app-server", "daemon", "start"}, false},
		{[]string{"exec", "proxy"}, false},
	} {
		if got := isAppServerProxy(test.args); got != test.want {
			t.Errorf("isAppServerProxy(%q)=%v", test.args, got)
		}
	}
}

func TestRemoteWebSocketBridgeCarriesRPCWithoutNetworkListener(t *testing.T) {
	client, server := net.Pipe()
	done := make(chan error, 1)
	go func() {
		done <- bridgeRemoteProxy(server, server, func(ctx context.Context) *exec.Cmd { return exec.CommandContext(ctx, "cat") })
	}()
	dialer := websocket.Dialer{HandshakeTimeout: time.Second, NetDialContext: func(context.Context, string, string) (net.Conn, error) { return client, nil }}
	connection, _, err := dialer.Dial("ws://codex-app-server/rpc", nil)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	_ = connection.SetReadDeadline(time.Now().Add(3 * time.Second))
	for _, message := range []string{
		`{"id":1,"method":"initialize","params":{}}`,
		`{"id":2,"method":"personalWork/routing/read","params":{"hostId":"remote:test"}}`,
		`{"id":3,"method":"personalWork/mode/set","params":{"mode":"intensive","threadId":"test"}}`,
		"{\n  \"id\":4,\n  \"method\":\"thread/list\",\n  \"params\":{}\n}\n",
	} {
		if err := connection.WriteMessage(websocket.TextMessage, []byte(message)); err != nil {
			t.Fatal(err)
		}
		_, result, err := connection.ReadMessage()
		if err != nil {
			t.Fatal(err)
		}
		var expected bytes.Buffer
		if err := json.Compact(&expected, []byte(message)); err != nil {
			t.Fatal(err)
		}
		if string(result) != expected.String() {
			t.Fatalf("RPC changed across SSH bridge: %s", result)
		}
	}
	_ = connection.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
	_ = connection.Close()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("closing bridge: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("SSH bridge did not stop after disconnect")
	}
}
