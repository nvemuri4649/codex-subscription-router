package state

import (
	"errors"
	"fmt"
	"maps"
	"path/filepath"
	"slices"
	"strings"
)

type Mode string

const (
	Casual    Mode = "casual"
	Intensive Mode = "intensive"
)

func (m Mode) Valid() bool { return m == Casual || m == Intensive }

func (m Mode) Role() string {
	if m == Intensive {
		return "work"
	}
	return "personal"
}

type ProjectMode struct {
	ProjectKey string `json:"projectKey"`
	HostID     string `json:"hostId"`
	Mode       Mode   `json:"mode"`
}

type RoutingSettings struct {
	DefaultMode  Mode              `json:"defaultMode"`
	RoleAccounts map[string]string `json:"roleAccounts"`
	Projects     []ProjectMode     `json:"projects"`
}

func defaultRouting() RoutingSettings {
	return RoutingSettings{DefaultMode: Casual, RoleAccounts: map[string]string{"personal": "", "work": ""}, Projects: []ProjectMode{}}
}

func normalizeRouting(r RoutingSettings) RoutingSettings {
	if !r.DefaultMode.Valid() {
		r.DefaultMode = Casual
	}
	if r.RoleAccounts == nil {
		r.RoleAccounts = defaultRouting().RoleAccounts
	}
	if r.Projects == nil {
		r.Projects = []ProjectMode{}
	}
	return r
}

func (s *Store) Routing() RoutingSettings {
	s.mu.RLock()
	defer s.mu.RUnlock()
	r := s.routing
	r.RoleAccounts = maps.Clone(r.RoleAccounts)
	r.Projects = slices.Clone(r.Projects)
	return r
}

// UpdateRouting never guesses which account is personal or work. Changing a
// role affects future tasks only; existing tasks retain their recorded owner.
func (s *Store) UpdateRouting(mode *Mode, roles map[string]string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	next := s.routing
	next.RoleAccounts = maps.Clone(next.RoleAccounts)
	if mode != nil {
		if !mode.Valid() {
			return errors.New("mode must be casual or intensive")
		}
		next.DefaultMode = *mode
	}
	for role, accountID := range roles {
		if role != "personal" && role != "work" {
			return fmt.Errorf("unknown account role %q", role)
		}
		if accountID != "" {
			found := false
			for _, account := range s.accounts {
				if account.ID == accountID {
					found = true
					break
				}
			}
			if !found {
				return fmt.Errorf("account %q not found", accountID)
			}
		}
		next.RoleAccounts[role] = accountID
	}
	if next.RoleAccounts["personal"] != "" && next.RoleAccounts["personal"] == next.RoleAccounts["work"] {
		return errors.New("choose separate personal and work accounts")
	}
	previous := s.routing
	s.routing = next
	if err := s.saveLocked(); err != nil {
		s.routing = previous
		return err
	}
	return nil
}

func (s *Store) SetProjectMode(hostID, projectKey string, mode *Mode) error {
	if hostID == "" {
		hostID = "local"
	}
	projectKey = strings.TrimSpace(projectKey)
	if projectKey == "" || !filepath.IsAbs(projectKey) {
		return errors.New("projectKey must be an absolute project path")
	}
	projectKey = filepath.Clean(projectKey)
	if mode != nil && !mode.Valid() {
		return errors.New("mode must be casual or intensive")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	previous := s.routing.Projects
	next := make([]ProjectMode, 0, len(previous)+1)
	for _, project := range previous {
		if project.HostID != hostID || project.ProjectKey != projectKey {
			next = append(next, project)
		}
	}
	if mode != nil {
		next = append(next, ProjectMode{HostID: hostID, ProjectKey: projectKey, Mode: *mode})
	}
	s.routing.Projects = next
	if err := s.saveLocked(); err != nil {
		s.routing.Projects = previous
		return err
	}
	return nil
}

// ResolveMode uses the nearest configured parent project, keeping identical
// paths on different machines separate.
func (s *Store) ResolveMode(hostID, projectKey string) (Mode, string) {
	r := s.Routing()
	if hostID == "" {
		hostID = "local"
	}
	if projectKey == "" {
		return r.DefaultMode, "default"
	}
	projectKey = filepath.Clean(projectKey)
	best := ""
	mode := r.DefaultMode
	for _, project := range r.Projects {
		if project.HostID != hostID {
			continue
		}
		rel, err := filepath.Rel(project.ProjectKey, projectKey)
		if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			continue
		}
		if len(project.ProjectKey) > len(best) {
			best = project.ProjectKey
			mode = project.Mode
		}
	}
	if best != "" {
		return mode, "project"
	}
	return mode, "default"
}

// LearnThreadOwner records imported history once. Shared indexes and resume
// notifications must not silently reassign existing personal or work tasks.
func (s *Store) LearnThreadOwner(threadID, accountID string) error {
	if threadID == "" || accountID == "" {
		return errors.New("thread and account IDs are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.owners[threadID]; exists {
		return nil
	}
	s.owners[threadID] = accountID
	if err := s.saveLocked(); err != nil {
		delete(s.owners, threadID)
		return err
	}
	return nil
}
