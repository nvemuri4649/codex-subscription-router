package mux

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/b-nnett/codex-subscription-router/internal/backend"
	"github.com/b-nnett/codex-subscription-router/internal/protocol"
	"github.com/b-nnett/codex-subscription-router/internal/state"
)

// This subprocess implements just the official RPC shapes used by these
// tests. No real account, network request, or model turn is involved.
func TestWorkflowBackendProcess(t *testing.T) {
	if os.Getenv("CODEX_MUX_TEST_HELPER") != "1" {
		return
	}
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		message, err := protocol.Parse(scanner.Bytes())
		if err != nil || len(message.ID) == 0 {
			continue
		}
		home := os.Getenv("CODEX_HOME")
		var result any = map[string]any{"home": home}
		switch message.Method {
		case "initialize":
			result = map[string]any{"userAgent": "test"}
		case "account/read":
			result = map[string]any{"account": map[string]any{"type": "chatgpt", "email": "example@test.invalid", "planType": "pro"}, "home": home}
		case "getAuthStatus":
			result = map[string]any{"authMethod": "chatgpt", "home": home}
		case "account/rateLimits/read":
			result = map[string]any{"rateLimits": map[string]any{"primary": map[string]any{"usedPercent": 100}}}
		case "thread/start":
			result = map[string]any{"thread": map[string]any{"id": "created", "path": "/fake/rollout.jsonl"}, "home": home, "params": json.RawMessage(message.Params)}
		case "thread/list":
			result = map[string]any{"data": []any{map[string]any{"id": "imported", "updatedAt": 1}}, "nextCursor": nil}
		case "thread/read":
			status := "idle"
			if os.Getenv("CODEX_MUX_TEST_BUSY") == "1" {
				status = "active"
			}
			result = map[string]any{"thread": map[string]any{"id": "existing", "path": "/fake/rollout.jsonl", "cwd": "/code", "modelProvider": "openai", "status": map[string]any{"type": status}}}
		case "thread/resume":
			result = map[string]any{"thread": map[string]any{"id": "existing"}, "home": home}
		case "turn/start":
			encoded, _ := protocol.Encode(protocol.Failure(message.ID, -32000, "native usage limit reached"))
			fmt.Fprintln(os.Stdout, string(encoded))
			continue
		}
		encodedResult, _ := json.Marshal(result)
		encoded, _ := protocol.Encode(protocol.Success(message.ID, encodedResult))
		fmt.Fprintln(os.Stdout, string(encoded))
	}
	os.Exit(0)
}

type workflowOutput struct{ messages chan protocol.Message }

func (w *workflowOutput) Write(data []byte) (int, error) {
	message, err := protocol.Parse(data)
	if err != nil {
		return 0, err
	}
	w.messages <- message
	return len(data), nil
}

func workflowFixture(t *testing.T, extraEnv ...string) (*Multiplexer, *state.Store, state.Account, *workflowOutput) {
	t.Helper()
	root := t.TempDir()
	store, err := state.Open(filepath.Join(root, "router"), filepath.Join(root, "primary"))
	if err != nil {
		t.Fatal(err)
	}
	personal, err := store.AddAccount("Personal")
	if err != nil {
		t.Fatal(err)
	}
	if err := store.UpdateRouting(nil, map[string]string{"personal": personal.ID, "work": "primary"}); err != nil {
		t.Fatal(err)
	}
	output := &workflowOutput{messages: make(chan protocol.Message, 32)}
	environment := append([]string{"CODEX_MUX_TEST_HELPER=1"}, extraEnv...)
	m, err := New(Options{Store: store, RealExecutable: os.Args[0], RealArgs: []string{"-test.run=^TestWorkflowBackendProcess$"}, Environment: environment, Output: output})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	if err := m.Start(ctx); err != nil {
		cancel()
		t.Fatal(err)
	}
	t.Cleanup(func() { cancel(); m.Close() })
	return m, store, personal, output
}

func workflowReply(t *testing.T, m *Multiplexer, output *workflowOutput, method, params string) protocol.Message {
	t.Helper()
	m.HandleClient(protocol.Request(method, json.RawMessage(`19`), json.RawMessage(params)))
	select {
	case reply := <-output.messages:
		return reply
	case <-time.After(5 * time.Second):
		t.Fatalf("timed out waiting for %s", method)
		return protocol.Message{}
	}
}

func TestNewTaskUsesWorkflowEvenWhenSelectedAccountIsDepleted(t *testing.T) {
	m, store, personal, output := workflowFixture(t)
	intensive := state.Intensive
	if err := store.SetProjectMode("local", "/code", &intensive); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ params, home string }{{`{"cwd":"/hobby"}`, personal.CodexHome}, {`{"cwd":"/code"}`, store.PrimaryCodexHome()}, {`{"cwd":"/code","_codexWorkflow":{"mode":"casual"}}`, personal.CodexHome}} {
		reply := workflowReply(t, m, output, "thread/start", test.params)
		if reply.Error != nil {
			t.Fatal(reply.Error.Message)
		}
		var result struct {
			Home   string         `json:"home"`
			Params map[string]any `json:"params"`
		}
		if err := json.Unmarshal(reply.Result, &result); err != nil {
			t.Fatal(err)
		}
		if result.Home != test.home {
			t.Fatalf("selected home %q, want %q", result.Home, test.home)
		}
		if _, exists := result.Params["_codexWorkflow"]; exists {
			t.Fatal("private selection reached official schema")
		}
	}
}

func TestMissingPersonalNeverFallsBackToWork(t *testing.T) {
	m, store, _, output := workflowFixture(t)
	if err := store.UpdateRouting(nil, map[string]string{"personal": ""}); err != nil {
		t.Fatal(err)
	}
	reply := workflowReply(t, m, output, "thread/start", `{"cwd":"/hobby"}`)
	if reply.Error == nil || !strings.Contains(reply.Error.Message, "personal account") {
		t.Fatalf("missing personal did not fail clearly: %#v", reply)
	}
}

func TestNativeUsageLimitPreservesTaskOwnerAndError(t *testing.T) {
	m, store, personal, output := workflowFixture(t)
	if err := store.SetThreadOwner("existing", personal.ID); err != nil {
		t.Fatal(err)
	}
	reply := workflowReply(t, m, output, "turn/start", `{"threadId":"existing","input":[]}`)
	if reply.Error == nil || reply.Error.Message != "native usage limit reached" {
		t.Fatalf("native limit was intercepted: %#v", reply)
	}
	if owner, _ := store.ThreadOwner("existing"); owner != personal.ID {
		t.Fatalf("quota moved task to %q", owner)
	}
	m.activeTurnsMu.Lock()
	_, active := m.activeTurns["existing"]
	m.activeTurnsMu.Unlock()
	if active {
		t.Fatal("rejected turn remained active")
	}
}

func TestAsyncLimitIsForwardedWithoutSwitchingOrContinuing(t *testing.T) {
	m, store, _, output := workflowFixture(t)
	if err := store.SetThreadOwner("existing", "primary"); err != nil {
		t.Fatal(err)
	}
	m.activeTurnsMu.Lock()
	m.activeTurns["existing"] = activeTurn{accountID: "primary"}
	m.activeTurnsMu.Unlock()
	message := protocol.Message{Method: "error", Params: json.RawMessage(`{"threadId":"existing","willRetry":false,"error":{"message":"usage limit reached"}}`)}
	raw, _ := protocol.Encode(message)
	m.handleInbound(backend.Inbound{AccountID: "primary", Message: message, Raw: raw})
	select {
	case result := <-output.messages:
		if result.Method != "error" {
			t.Fatalf("unexpected notification: %v", result)
		}
	case <-time.After(time.Second):
		t.Fatal("native error was hidden")
	}
	if owner, _ := store.ThreadOwner("existing"); owner != "primary" {
		t.Fatal("async limit moved account")
	}
}

func TestExistingTasksKeepWorkWhileAppDefaultsToPersonal(t *testing.T) {
	m, store, personal, output := workflowFixture(t)
	reply := workflowReply(t, m, output, "account/read", `{}`)
	var identity struct {
		Home string `json:"home"`
	}
	if err := json.Unmarshal(reply.Result, &identity); err != nil {
		t.Fatal(err)
	}
	if identity.Home != personal.CodexHome {
		t.Fatal("account identity did not use personal")
	}
	if err := store.LearnThreadOwner("old", "primary"); err != nil {
		t.Fatal(err)
	}
	selection := m.selection(RoutingQuery{ThreadID: "old"})
	if selection.AccountID != "primary" || selection.Mode != state.Intensive {
		t.Fatalf("existing task moved: %#v", selection)
	}
	selection = m.selection(RoutingQuery{ThreadID: "unindexed"})
	if selection.AccountID != "primary" {
		t.Fatal("history predating router guessed personal owner")
	}
}

func TestPersonalAssignmentInvalidatesNativeAuthCache(t *testing.T) {
	m, store, personal, output := workflowFixture(t)
	if err := store.UpdateRouting(nil, map[string]string{"personal": ""}); err != nil {
		t.Fatal(err)
	}
	if _, err := m.UpdateRouting(context.Background(), RoutingUpdate{RoleAccounts: map[string]string{"personal": personal.ID}}); err != nil {
		t.Fatal(err)
	}
	select {
	case event := <-output.messages:
		if event.Method != "account/updated" || string(event.Params) != `{"authMode":"chatgpt"}` {
			t.Fatalf("wrong native cache invalidation: %#v", event)
		}
	case <-time.After(time.Second):
		t.Fatal("controller changed without native account notification")
	}
	reply := workflowReply(t, m, output, "getAuthStatus", `{"includeToken":true,"refreshToken":false}`)
	var identity struct {
		Home string `json:"home"`
	}
	if err := json.Unmarshal(reply.Result, &identity); err != nil {
		t.Fatal(err)
	}
	if identity.Home != personal.CodexHome {
		t.Fatal("native cloud authentication was not routed to personal")
	}
	if _, err := m.UpdateRouting(context.Background(), RoutingUpdate{RoleAccounts: map[string]string{"personal": personal.ID}}); err != nil {
		t.Fatal(err)
	}
	select {
	case event := <-output.messages:
		t.Fatalf("unchanged role reset native state: %#v", event)
	default:
	}
}

func TestSharedConfigStaysOnSourceWhileAuthenticationUsesPersonal(t *testing.T) {
	m, store, personal, output := workflowFixture(t)
	for _, test := range []struct{ method, home string }{
		{"config/read", store.PrimaryCodexHome()},
		{"config/value/write", store.PrimaryCodexHome()},
		{"experimentalFeature/enablement/set", store.PrimaryCodexHome()},
		{"getAuthStatus", personal.CodexHome},
	} {
		reply := workflowReply(t, m, output, test.method, `{}`)
		var result struct {
			Home string `json:"home"`
		}
		if err := json.Unmarshal(reply.Result, &result); err != nil {
			t.Fatal(err)
		}
		if result.Home != test.home {
			t.Fatalf("%s routed to %q; want %q", test.method, result.Home, test.home)
		}
	}
}

func TestSharedThreadListDoesNotDuplicateOrReassignHistory(t *testing.T) {
	m, store, personal, output := workflowFixture(t)
	for run := 0; run < 3; run++ {
		if run == 1 {
			if err := store.SetThreadOwner("imported", personal.ID); err != nil {
				t.Fatal(err)
			}
		}
		reply := workflowReply(t, m, output, "thread/list", `{}`)
		var result struct {
			Data []map[string]any `json:"data"`
		}
		if err := json.Unmarshal(reply.Result, &result); err != nil {
			t.Fatal(err)
		}
		if len(result.Data) != 1 {
			t.Fatalf("shared list has %d copies", len(result.Data))
		}
		want := "primary"
		if run > 0 {
			want = personal.ID
		}
		if owner, _ := store.ThreadOwner("imported"); owner != want {
			t.Fatalf("history owner %q, want %q", owner, want)
		}
	}
}

func TestExplicitSwitchAllowsDepletedAccountAndRejectsBusyTask(t *testing.T) {
	m, store, personal, _ := workflowFixture(t)
	if err := store.SetThreadOwner("existing", "primary"); err != nil {
		t.Fatal(err)
	}
	casual := state.Casual
	result, err := m.SetMode(context.Background(), ModeUpdate{RoutingQuery: RoutingQuery{ThreadID: "existing"}, Mode: &casual})
	if err != nil {
		t.Fatal(err)
	}
	if result.Selection.AccountID != personal.ID || !result.Selection.Ready {
		t.Fatalf("explicit switch failed: %#v", result)
	}
	m.activeTurnsMu.Lock()
	m.activeTurns["existing"] = activeTurn{accountID: personal.ID}
	m.activeTurnsMu.Unlock()
	intensive := state.Intensive
	if _, err := m.SetMode(context.Background(), ModeUpdate{RoutingQuery: RoutingQuery{ThreadID: "existing"}, Mode: &intensive}); err == nil {
		t.Fatal("active task switched")
	}
	if owner, _ := store.ThreadOwner("existing"); owner != personal.ID {
		t.Fatal("failed switch changed owner")
	}
}

func TestSwitchAlsoChecksNativeRunningStatus(t *testing.T) {
	m, store, personal, _ := workflowFixture(t, "CODEX_MUX_TEST_BUSY=1")
	if err := store.SetThreadOwner("existing", "primary"); err != nil {
		t.Fatal(err)
	}
	if _, err := m.SwitchThreadAccount(context.Background(), "existing", personal.ID); err == nil || !strings.Contains(err.Error(), "current turn") {
		t.Fatalf("native running task was not protected: %v", err)
	}
}

func TestRemoteWorkflowRPCUsesHostScopeAndReturnsAccounts(t *testing.T) {
	m, _, _, output := workflowFixture(t, "CODEX_MUX_HOST_ID=crusoe")
	reply := workflowReply(t, m, output, "personalWork/routing/read", `{"hostId":"crusoe"}`)
	if reply.Error != nil {
		t.Fatal(reply.Error.Message)
	}
	var snapshot RoutingSnapshot
	if err := json.Unmarshal(reply.Result, &snapshot); err != nil {
		t.Fatal(err)
	}
	if snapshot.HostID != "crusoe" || !snapshot.RemoteManaged || len(snapshot.Accounts) != 2 {
		t.Fatalf("incomplete remote snapshot: %#v", snapshot)
	}
	reply = workflowReply(t, m, output, "personalWork/mode/set", `{"hostId":"local","mode":"intensive"}`)
	if reply.Error == nil || !strings.Contains(reply.Error.Message, "not managed") {
		t.Fatal("remote request silently altered local routing")
	}
}
