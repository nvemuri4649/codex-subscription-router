package mux

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/b-nnett/codex-subscription-router/internal/protocol"
	"github.com/b-nnett/codex-subscription-router/internal/state"
)

func migratedControllerStore(t *testing.T) (*state.Store, string) {
	t.Helper()
	root := t.TempDir()
	primaryHome := filepath.Join(root, "primary")
	personalHome := filepath.Join(root, "personal")
	if err := os.MkdirAll(personalHome, 0700); err != nil {
		t.Fatal(err)
	}
	owners := map[string]string{}
	for i := 0; i < 16; i++ {
		owners[fmt.Sprintf("saved-%d", i)] = "primary"
	}
	contents, err := json.Marshal(map[string]any{
		"version": 1,
		"accounts": []state.Account{
			{ID: "primary", Label: "Work", CodexHome: primaryHome, Enabled: true},
			{ID: "personal", Label: "Personal", CodexHome: personalHome, Enabled: true, Controller: true},
		},
		"threadOwner": owners,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "state.json"), contents, 0600); err != nil {
		t.Fatal(err)
	}
	store, err := state.Open(root, primaryHome)
	if err != nil {
		t.Fatal(err)
	}
	return store, personalHome
}

func TestPersonalControllerKeepsOriginalHistoryAndConfigSource(t *testing.T) {
	store, personalHome := migratedControllerStore(t)
	controller, ok := store.Controller()
	if !ok || controller.ID != "personal" || controller.CodexHome != personalHome {
		t.Fatal("personal controller was not retained")
	}
	primary, ok := store.Primary()
	if !ok || primary.ID != "primary" {
		t.Fatal("original history/configuration home was not retained")
	}
	m := &Multiplexer{store: store}
	for _, test := range []struct{ method, thread, owner string }{
		{"getAuthStatus", "", "personal"},
		{"account/read", "", "personal"},
		{"config/read", "", "primary"},
		{"config/value/write", "", "primary"},
		{"experimentalFeature/enablement/set", "", "primary"},
		{"thread/read", "saved-0", "primary"},
		{"thread/resume", "previously-unindexed", "primary"},
	} {
		if got := m.existingRequestAccountID(test.method, test.thread); got != test.owner {
			t.Errorf("%s(%q) selects %q; want %q", test.method, test.thread, got, test.owner)
		}
	}
	if err := store.SetThreadOwner("explicit-move", "personal"); err != nil {
		t.Fatal(err)
	}
	if got := m.existingRequestAccountID("turn/start", "explicit-move"); got != "personal" {
		t.Fatal("existing affinity lost")
	}
	for i := 0; i < 16; i++ {
		if owner, _ := store.ThreadOwner(fmt.Sprintf("saved-%d", i)); owner != "primary" {
			t.Fatal("saved work owner changed")
		}
	}
}

// A shared-index subprocess provides no model or authentication behavior.
func TestSharedIndexBackendProcess(t *testing.T) {
	if os.Getenv("CODEX_MUX_TEST_SHARED_INDEX") != "1" {
		return
	}
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		request, err := protocol.Parse(scanner.Bytes())
		if err != nil || len(request.ID) == 0 {
			continue
		}
		result := json.RawMessage(`{"data":[{"id":"saved-0","updatedAt":2},{"id":"imported","updatedAt":1},{"id":"explicit-move","updatedAt":3}],"nextCursor":null}`)
		encoded, _ := protocol.Encode(protocol.Success(request.ID, result))
		fmt.Fprintln(os.Stdout, string(encoded))
	}
	os.Exit(0)
}

type controllerTestOutput chan protocol.Message

func (o controllerTestOutput) Write(contents []byte) (int, error) {
	message, err := protocol.Parse(contents)
	if err != nil {
		return 0, err
	}
	o <- message
	return len(contents), nil
}

func TestSharedListDeduplicatesWithoutOverwritingStickyOwners(t *testing.T) {
	store, _ := migratedControllerStore(t)
	if err := store.SetThreadOwner("explicit-move", "personal"); err != nil {
		t.Fatal(err)
	}
	output := make(controllerTestOutput, 4)
	m, err := New(Options{Store: store, RealExecutable: os.Args[0], RealArgs: []string{"-test.run=^TestSharedIndexBackendProcess$"}, Environment: []string{"CODEX_MUX_TEST_SHARED_INDEX=1"}, Output: output})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	if err := m.Start(ctx); err != nil {
		cancel()
		t.Fatal(err)
	}
	defer func() { cancel(); m.Close() }()
	for i := 0; i < 3; i++ {
		m.HandleClient(protocol.Request("thread/list", json.RawMessage(`1`), json.RawMessage(`{}`)))
		select {
		case reply := <-output:
			var result struct {
				Data []map[string]any `json:"data"`
			}
			if err := json.Unmarshal(reply.Result, &result); err != nil {
				t.Fatal(err)
			}
			if len(result.Data) != 3 {
				t.Fatalf("shared history returned %d rows, want 3", len(result.Data))
			}
		case <-time.After(5 * time.Second):
			t.Fatal("shared thread list timed out")
		}
		for thread, want := range map[string]string{"saved-0": "primary", "imported": "primary", "explicit-move": "personal"} {
			if owner, _ := store.ThreadOwner(thread); owner != want {
				t.Fatalf("%s assigned to %q, want %q", thread, owner, want)
			}
		}
	}
}
