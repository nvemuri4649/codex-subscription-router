package control

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"github.com/b-nnett/codex-subscription-router/internal/mux"
	"github.com/b-nnett/codex-subscription-router/internal/state"
)

func TestRoutingControlRequiresAuthenticationAndKeepsHostScope(t *testing.T) {
	root := t.TempDir()
	store, err := state.Open(filepath.Join(root, "router"), filepath.Join(root, "primary"))
	if err != nil {
		t.Fatal(err)
	}
	m, err := mux.New(mux.Options{Store: store, RealExecutable: "unused", Output: io.Discard})
	if err != nil {
		t.Fatal(err)
	}
	server := New("127.0.0.1:0", "test-secret", m, false)
	for _, test := range []struct {
		method, path, body, token string
		status                    int
	}{
		{http.MethodGet, "/v1/routing", "", "", http.StatusUnauthorized},
		{http.MethodPost, "/v1/routing", `{"roleAccounts":{"personal":null,"work":"primary"}}`, "test-secret", http.StatusOK},
		{http.MethodPost, "/v1/thread-mode", `{"projectKey":"/code","hostId":"local","mode":"intensive"}`, "test-secret", http.StatusOK},
		{http.MethodPost, "/v1/thread-mode", `{"projectKey":"/code","hostId":"remote","mode":"casual"}`, "test-secret", http.StatusBadRequest},
		{http.MethodPost, "/v1/thread-mode", `{"projectKey":"/code","mode":"unknown"}`, "test-secret", http.StatusBadRequest},
		{http.MethodPost, "/v1/routing", `{"roleAccounts":{"personal":"primary","work":"primary"}}`, "test-secret", http.StatusBadRequest},
	} {
		request := httptest.NewRequest(test.method, test.path, bytes.NewBufferString(test.body))
		request.Header.Set("X-Codex-Mux-Token", test.token)
		response := httptest.NewRecorder()
		server.http.Handler.ServeHTTP(response, request)
		if response.Code != test.status {
			t.Fatalf("%s %s => %d: %s", test.method, test.path, response.Code, response.Body.String())
		}
	}
	if role := store.Routing().RoleAccounts["work"]; role != "primary" {
		t.Fatal("role mapping not saved")
	}
	if mode, _ := store.ResolveMode("local", "/code"); mode != state.Intensive {
		t.Fatal("remote or invalid request changed local project default")
	}
}
