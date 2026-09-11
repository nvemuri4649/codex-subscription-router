package mux

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/b-nnett/codex-subscription-router/internal/protocol"
	"github.com/b-nnett/codex-subscription-router/internal/state"
)

type RoutingQuery struct {
	ThreadID   string `json:"threadId,omitempty"`
	ProjectKey string `json:"projectKey,omitempty"`
	HostID     string `json:"hostId,omitempty"`
}

type RoutingUpdate struct {
	DefaultMode  *state.Mode       `json:"defaultMode,omitempty"`
	RoleAccounts map[string]string `json:"roleAccounts,omitempty"`
	HostID       string            `json:"hostId,omitempty"`
}

type ModeUpdate struct {
	RoutingQuery
	Mode *state.Mode `json:"mode"`
}

type WorkflowSelection struct {
	Mode       state.Mode `json:"mode"`
	Source     string     `json:"source"`
	AccountID  string     `json:"accountId"`
	Ready      bool       `json:"ready"`
	Error      string     `json:"error,omitempty"`
	ThreadID   string     `json:"threadId,omitempty"`
	ProjectKey string     `json:"projectKey,omitempty"`
	Busy       bool       `json:"busy"`
}

type RoutingSnapshot struct {
	HostID        string              `json:"hostId"`
	DefaultMode   state.Mode          `json:"defaultMode"`
	RoleAccounts  map[string]*string  `json:"roleAccounts"`
	Projects      []state.ProjectMode `json:"projects"`
	Selection     WorkflowSelection   `json:"selection"`
	RemoteManaged bool                `json:"remoteManaged"`
	Accounts      []AccountSnapshot   `json:"accounts"`
}

func (m *Multiplexer) hostID() string {
	for _, entry := range m.environment {
		if value, ok := strings.CutPrefix(entry, "CODEX_MUX_HOST_ID="); ok && value != "" {
			return value
		}
	}
	return "local"
}

func (m *Multiplexer) validateHost(hostID string) error {
	if hostID != "" && hostID != m.hostID() {
		return fmt.Errorf("host %q is not managed by this router (%s); connect to the Personal & Work router on that host", hostID, m.hostID())
	}
	return nil
}

func (m *Multiplexer) selection(query RoutingQuery) WorkflowSelection {
	mode, source := m.store.ResolveMode(m.hostID(), query.ProjectKey)
	settings := m.store.Routing()
	selection := WorkflowSelection{Mode: mode, Source: source, AccountID: settings.RoleAccounts[mode.Role()], ThreadID: query.ThreadID, ProjectKey: query.ProjectKey}
	if query.ThreadID != "" {
		if owner, ok := m.store.ThreadOwner(query.ThreadID); ok {
			selection.AccountID, selection.Source, selection.Mode = owner, "thread", ""
			for _, candidate := range []state.Mode{state.Casual, state.Intensive} {
				if settings.RoleAccounts[candidate.Role()] == owner {
					selection.Mode = candidate
				}
			}
		} else if controller, ok := m.store.Controller(); ok {
			// History predating the router belongs to the original login. It
			// must not move merely because a new default has been selected.
			selection.AccountID, selection.Source, selection.Mode = controller.ID, "existing", ""
			for _, candidate := range []state.Mode{state.Casual, state.Intensive} {
				if settings.RoleAccounts[candidate.Role()] == controller.ID {
					selection.Mode = candidate
				}
			}
		}
		m.activeTurnsMu.Lock()
		_, selection.Busy = m.activeTurns[query.ThreadID]
		m.activeTurnsMu.Unlock()
	}
	return selection
}

func (m *Multiplexer) availableWorkflowAccount(ctx context.Context, selection WorkflowSelection) (state.Account, error) {
	role := selection.Mode.Role()
	if selection.AccountID == "" {
		return state.Account{}, fmt.Errorf("connect and assign a %s account to use %s mode", role, selection.Mode)
	}
	account, ok := m.store.Account(selection.AccountID)
	if !ok {
		return state.Account{}, errors.New("selected account no longer exists; choose an account in Personal & Work")
	}
	if !account.Enabled {
		return state.Account{}, fmt.Errorf("%s is disabled; enable it in Personal & Work", account.Label)
	}
	snapshot, err := m.accountSnapshotWithProfile(ctx, account.ID, false)
	if err != nil {
		return state.Account{}, fmt.Errorf("%s is unavailable: %w", account.Label, err)
	}
	if !snapshot.Connected || snapshot.AuthType != "chatgpt" {
		return state.Account{}, fmt.Errorf("sign in to %s to use this workflow", account.Label)
	}
	// Capacity deliberately does not participate in workflow routing. The
	// selected account receives the request and Codex reports its own limit.
	return account, nil
}

func (m *Multiplexer) Routing(ctx context.Context, query RoutingQuery) (RoutingSnapshot, error) {
	if err := m.validateHost(query.HostID); err != nil {
		return RoutingSnapshot{}, err
	}
	settings := m.store.Routing()
	roles := map[string]*string{"personal": nil, "work": nil}
	for role, accountID := range settings.RoleAccounts {
		if accountID != "" {
			value := accountID
			roles[role] = &value
		}
	}
	selection := m.selection(query)
	accounts := m.accountSnapshots(ctx, false)
	selection.Error = fmt.Sprintf("connect and assign a %s account to use %s mode", selection.Mode.Role(), selection.Mode)
	for _, account := range accounts {
		if account.ID != selection.AccountID {
			continue
		}
		switch {
		case account.Error != "":
			selection.Error = account.Error
		case !account.Enabled:
			selection.Error = fmt.Sprintf("%s is disabled; enable it in Personal & Work", account.Label)
		case !account.Connected || account.AuthType != "chatgpt":
			selection.Error = fmt.Sprintf("sign in to %s to use this workflow", account.Label)
		default:
			selection.Ready, selection.Error = true, ""
		}
		break
	}
	return RoutingSnapshot{HostID: m.hostID(), DefaultMode: settings.DefaultMode, RoleAccounts: roles, Projects: settings.Projects, Selection: selection, RemoteManaged: m.hostID() != "local", Accounts: accounts}, nil
}

func (m *Multiplexer) UpdateRouting(ctx context.Context, update RoutingUpdate) (RoutingSnapshot, error) {
	if err := m.validateHost(update.HostID); err != nil {
		return RoutingSnapshot{}, err
	}
	m.routingMu.Lock()
	defer m.routingMu.Unlock()
	previousController := m.defaultAccountID()
	if err := m.store.UpdateRouting(update.DefaultMode, update.RoleAccounts); err != nil {
		return RoutingSnapshot{}, err
	}
	snapshot, err := m.Routing(ctx, RoutingQuery{})
	if err != nil {
		return RoutingSnapshot{}, err
	}
	if controller := m.defaultAccountID(); controller != previousController {
		// The desktop's native account/updated handler clears its cached
		// getAuthStatus token and refreshes account-scoped state. Merely
		// changing account/read routing would leave cloud requests using the
		// previous account until that token expired or the app restarted.
		var authMode any
		for _, account := range snapshot.Accounts {
			if account.ID == controller && account.Connected {
				authMode = account.AuthType
				break
			}
		}
		params, _ := json.Marshal(map[string]any{"authMode": authMode})
		m.write(protocol.Message{Method: "account/updated", Params: params})
	}
	m.publish(Event{Type: "routing-updated"})
	return snapshot, nil
}

func (m *Multiplexer) SetMode(ctx context.Context, update ModeUpdate) (RoutingSnapshot, error) {
	if err := m.validateHost(update.HostID); err != nil {
		return RoutingSnapshot{}, err
	}
	if update.Mode != nil && !update.Mode.Valid() {
		return RoutingSnapshot{}, errors.New("mode must be casual or intensive")
	}
	if update.ThreadID != "" {
		if update.Mode == nil {
			return RoutingSnapshot{}, errors.New("choose casual or intensive for an existing task")
		}
		accountID := m.store.Routing().RoleAccounts[update.Mode.Role()]
		selection := WorkflowSelection{Mode: *update.Mode, AccountID: accountID}
		if _, err := m.availableWorkflowAccount(ctx, selection); err != nil {
			return RoutingSnapshot{}, err
		}
		if _, err := m.SwitchThreadAccount(ctx, update.ThreadID, accountID); err != nil {
			return RoutingSnapshot{}, err
		}
	} else if update.ProjectKey != "" {
		if err := m.store.SetProjectMode(m.hostID(), update.ProjectKey, update.Mode); err != nil {
			return RoutingSnapshot{}, err
		}
	} else {
		if update.Mode == nil {
			return RoutingSnapshot{}, errors.New("mode must be casual or intensive")
		}
		if err := m.store.UpdateRouting(update.Mode, nil); err != nil {
			return RoutingSnapshot{}, err
		}
	}
	m.publish(Event{Type: "routing-updated"})
	return m.Routing(ctx, update.RoutingQuery)
}

// workflowThreadRequest removes private renderer metadata before the strict
// official app-server schema sees it. An explicit mode is one task only.
func workflowThreadRequest(params json.RawMessage) (RoutingQuery, *state.Mode, json.RawMessage, error) {
	if len(params) == 0 {
		return RoutingQuery{}, nil, params, nil
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(params, &fields); err != nil {
		return RoutingQuery{}, nil, params, err
	}
	var query RoutingQuery
	_ = json.Unmarshal(fields["cwd"], &query.ProjectKey)
	raw, exists := fields["_codexWorkflow"]
	if !exists {
		return query, nil, params, nil
	}
	var marker struct {
		RoutingQuery
		Mode *state.Mode `json:"mode"`
	}
	if err := json.Unmarshal(raw, &marker); err != nil {
		return query, nil, nil, fmt.Errorf("invalid workflow selection: %w", err)
	}
	if marker.Mode != nil && !marker.Mode.Valid() {
		return query, nil, nil, errors.New("mode must be casual or intensive")
	}
	if marker.ProjectKey != "" {
		query.ProjectKey = marker.ProjectKey
	}
	query.HostID = marker.HostID
	delete(fields, "_codexWorkflow")
	cleaned, err := json.Marshal(fields)
	return query, marker.Mode, cleaned, err
}

func (m *Multiplexer) routeWorkflowRequest(message protocol.Message) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*requestTimeout)
	defer cancel()
	var result RoutingSnapshot
	var err error
	switch message.Method {
	case "personalWork/routing/read":
		var query RoutingQuery
		if len(message.Params) > 0 {
			err = json.Unmarshal(message.Params, &query)
		}
		if err == nil {
			result, err = m.Routing(ctx, query)
		}
	case "personalWork/routing/update":
		var update RoutingUpdate
		err = json.Unmarshal(message.Params, &update)
		if err == nil {
			result, err = m.UpdateRouting(ctx, update)
		}
	case "personalWork/mode/set":
		var update ModeUpdate
		err = json.Unmarshal(message.Params, &update)
		if err == nil {
			result, err = m.SetMode(ctx, update)
		}
	default:
		err = fmt.Errorf("unknown Personal & Work request %q", message.Method)
	}
	if err != nil {
		m.write(protocol.Failure(message.ID, -32030, err.Error()))
		return
	}
	encoded, _ := json.Marshal(result)
	m.write(protocol.Success(message.ID, encoded))
}
