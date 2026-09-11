package mux

import (
	"encoding/json"
	"testing"

	"github.com/b-nnett/codex-subscription-router/internal/protocol"
)

func TestIsUsageLimitResponseRecognizesStructuredError(t *testing.T) {
	message := protocol.Message{Error: &protocol.RPCError{
		Code:    -32000,
		Message: "turn failed",
		Data:    json.RawMessage(`{"codexErrorInfo":"usage_limit_exceeded"}`),
	}}
	if !isUsageLimitResponse(message) {
		t.Fatal("expected usage-limit error to be recognized")
	}
}

func TestIsUsageLimitResponseIgnoresUnrelatedError(t *testing.T) {
	message := protocol.Message{Error: &protocol.RPCError{
		Code:    -32000,
		Message: "workspace folder is unavailable",
	}}
	if isUsageLimitResponse(message) {
		t.Fatal("unrelated error was misclassified as a usage limit")
	}
}

func TestUsageLimitNotificationRecognizesTerminalAsyncError(t *testing.T) {
	params := json.RawMessage(`{
		"threadId":"thread-1",
		"willRetry":false,
		"error":{"message":"usage limit reached","codexErrorInfo":"usage_limit_exceeded"}
	}`)
	if !isTerminalUsageLimitNotification("error", params) {
		t.Fatal("expected terminal asynchronous usage error to be recognized")
	}
	if got := notificationThreadID(params); got != "thread-1" {
		t.Fatalf("notification thread ID = %q", got)
	}
}

func TestUsageLimitNotificationIgnoresRetryableError(t *testing.T) {
	params := json.RawMessage(`{"threadId":"thread-1","willRetry":true,"error":{"message":"rate limit"}}`)
	if isTerminalUsageLimitNotification("error", params) {
		t.Fatal("router must let Codex finish its own retry first")
	}
}
