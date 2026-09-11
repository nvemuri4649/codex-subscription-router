package state

import (
	"os"
	"path/filepath"
	"testing"
)

func TestWorkflowSettingsMigrateWithoutGuessingRoles(t *testing.T) {
	root := t.TempDir()
	primary := filepath.Join(root, "primary")
	if err := os.WriteFile(filepath.Join(root, "state.json"), []byte(`{"version":1,"accounts":[{"id":"primary","label":"Existing work","codexHome":"`+primary+`","controller":true,"enabled":true}],"threadOwner":{"old":"primary"}}`), 0600); err != nil {
		t.Fatal(err)
	}
	store, err := Open(root, primary)
	if err != nil {
		t.Fatal(err)
	}
	settings := store.Routing()
	if settings.DefaultMode != Casual || settings.RoleAccounts["personal"] != "" || settings.RoleAccounts["work"] != "" {
		t.Fatalf("migration guessed account roles: %#v", settings)
	}
	if owner, _ := store.ThreadOwner("old"); owner != "primary" {
		t.Fatal("existing task owner changed")
	}
}

func TestWorkflowRolesProjectsAndOwnershipPersist(t *testing.T) {
	root := t.TempDir()
	primary := filepath.Join(root, "primary")
	store, err := Open(filepath.Join(root, "router"), primary)
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
	intensive, casual := Intensive, Casual
	for _, project := range []ProjectMode{{HostID: "local", ProjectKey: "/code", Mode: intensive}, {HostID: "local", ProjectKey: "/code/hobby", Mode: casual}, {HostID: "remote", ProjectKey: "/code", Mode: casual}} {
		if err := store.SetProjectMode(project.HostID, project.ProjectKey, &project.Mode); err != nil {
			t.Fatal(err)
		}
	}
	if err := store.LearnThreadOwner("existing", "primary"); err != nil {
		t.Fatal(err)
	}
	if err := store.LearnThreadOwner("existing", personal.ID); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(filepath.Join(root, "router"), primary)
	if err != nil {
		t.Fatal(err)
	}
	if got := reopened.Routing().RoleAccounts["personal"]; got != personal.ID {
		t.Fatalf("personal account = %q", got)
	}
	for _, test := range []struct {
		host, path string
		mode       Mode
		source     string
	}{{"local", "/code/server", Intensive, "project"}, {"local", "/code/hobby/src", Casual, "project"}, {"local", "/code-other", Casual, "default"}, {"remote", "/code/server", Casual, "project"}, {"other", "/code/server", Casual, "default"}} {
		if mode, source := reopened.ResolveMode(test.host, test.path); mode != test.mode || source != test.source {
			t.Errorf("resolve(%q,%q) = %q,%q", test.host, test.path, mode, source)
		}
	}
	if owner, _ := reopened.ThreadOwner("existing"); owner != "primary" {
		t.Fatalf("shared history changed owner to %q", owner)
	}
	if err := reopened.SetProjectMode("local", "/code", nil); err != nil {
		t.Fatal(err)
	}
	if mode, source := reopened.ResolveMode("local", "/code/server"); mode != Casual || source != "default" {
		t.Fatal("project override was not removed")
	}
}

func TestWorkflowRoleValidationIsAtomic(t *testing.T) {
	root := t.TempDir()
	store, err := Open(filepath.Join(root, "router"), filepath.Join(root, "primary"))
	if err != nil {
		t.Fatal(err)
	}
	for _, roles := range []map[string]string{{"personal": "missing"}, {"unknown": "primary"}, {"personal": "primary", "work": "primary"}} {
		if err := store.UpdateRouting(nil, roles); err == nil {
			t.Fatalf("accepted invalid roles %v", roles)
		}
		if settings := store.Routing(); settings.RoleAccounts["personal"] != "" || settings.RoleAccounts["work"] != "" {
			t.Fatalf("failed update leaked changes: %#v", settings)
		}
	}
}
