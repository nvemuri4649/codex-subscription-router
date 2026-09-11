package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/b-nnett/codex-subscription-router/internal/state"
)

// These explicit administrative commands configure the remote installation.
// The installer never logs into an account, reads a token, or copies auth.json.
func runPersonalWork(realExecutable string, args []string) error {
	if len(args) == 0 {
		return errors.New("usage: codex personal-work setup|login|status")
	}
	flags := flag.NewFlagSet("personal-work "+args[0], flag.ContinueOnError)
	role := flags.String("role", "work", "account role: personal or work")
	mode := flags.String("default-mode", "intensive", "default workflow: casual or intensive")
	label := flags.String("label", "", "display name for a new account")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if args[0] != "setup" && args[0] != "login" && args[0] != "status" {
		return fmt.Errorf("unknown personal-work command %q", args[0])
	}
	if *role != "personal" && *role != "work" {
		return errors.New("role must be personal or work")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	root := os.Getenv("CODEX_MUX_HOME")
	if root == "" {
		root = filepath.Join(home, ".codex-mux")
	}
	primary := os.Getenv("CODEX_HOME")
	if primary == "" {
		primary = filepath.Join(home, ".codex")
	}
	store, err := state.Open(root, primary)
	if err != nil {
		return err
	}
	switch args[0] {
	case "setup":
		workflow := state.Mode(*mode)
		if !workflow.Valid() {
			return errors.New("default-mode must be casual or intensive")
		}
		if err := store.UpdateRouting(&workflow, map[string]string{*role: "primary"}); err != nil {
			return err
		}
		fmt.Fprintf(os.Stdout, "Configured %s on host %s. Existing remote login is the %s account.\n", workflow, os.Getenv("CODEX_MUX_HOST_ID"), *role)
	case "login":
		accountID := store.Routing().RoleAccounts[*role]
		account, exists := store.Account(accountID)
		if !exists {
			name := *label
			if name == "" {
				name = *role
			}
			account, err = store.AddAccount(name)
			if err != nil {
				return err
			}
			if err := store.UpdateRouting(nil, map[string]string{*role: account.ID}); err != nil {
				return err
			}
		}
		if account.ID == "primary" {
			return errors.New("this role uses the existing remote login; use the official Codex login command to change it, or assign a separate account")
		}
		command := exec.Command(realExecutable, "login", "--device-auth")
		command.Env = append(os.Environ(), "CODEX_HOME="+account.CodexHome)
		command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
		if err := command.Run(); err != nil {
			return fmt.Errorf("remote %s login: %w", *role, err)
		}
		fmt.Fprintf(os.Stdout, "Signed in the %s account on this host. Reconnect this host in Codex Personal & Work.\n", *role)
	case "status":
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"hostId": os.Getenv("CODEX_MUX_HOST_ID"), "routing": store.Routing(), "accounts": store.Accounts()})
	}
	return nil
}
