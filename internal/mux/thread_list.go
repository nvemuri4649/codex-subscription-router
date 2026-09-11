package mux

import (
	"context"
	"encoding/json"
	"sync"

	"github.com/b-nnett/codex-subscription-router/internal/protocol"
)

func (m *Multiplexer) aggregateThreadList(request protocol.Message) {
	entries := m.childEntries()
	type result struct {
		accountID string
		index     int
		threads   []map[string]any
	}
	results := make(chan result, len(entries))
	var wait sync.WaitGroup
	for index, entry := range entries {
		wait.Add(1)
		go func(index int, entry childEntry) {
			defer wait.Done()
			results <- result{accountID: entry.account.ID, index: index, threads: m.listAllThreads(entry, request.Params)}
		}(index, entry)
	}
	wait.Wait()
	close(results)

	ordered := make([]result, len(entries))
	for accountResult := range results {
		ordered[accountResult.index] = accountResult
	}
	threads := make([]map[string]any, 0)
	seen := make(map[string]bool)
	for _, accountResult := range ordered {
		for _, thread := range accountResult.threads {
			if threadID, ok := thread["id"].(string); ok {
				if seen[threadID] {
					continue
				}
				seen[threadID] = true
				_ = m.store.LearnThreadOwner(threadID, accountResult.accountID)
			}
			threads = append(threads, thread)
		}
	}
	sortThreads(threads)
	encoded, err := json.Marshal(map[string]any{"data": threads, "nextCursor": nil})
	if err != nil {
		m.write(protocol.Failure(request.ID, -32603, "failed to merge thread list"))
		return
	}
	m.write(protocol.Success(request.ID, encoded))
}

func (m *Multiplexer) listAllThreads(entry childEntry, originalParams json.RawMessage) []map[string]any {
	var params map[string]any
	if json.Unmarshal(originalParams, &params) != nil {
		params = make(map[string]any)
	}
	params["limit"] = 500
	threads := make([]map[string]any, 0)
	seenCursors := make(map[string]struct{})
	var cursor string
	for {
		if cursor == "" {
			params["cursor"] = nil
		} else {
			params["cursor"] = cursor
		}
		encodedParams, _ := json.Marshal(params)
		ctx, cancel := context.WithTimeout(context.Background(), requestTimeout)
		response, err := entry.child.Request(ctx, "thread/list", encodedParams)
		cancel()
		if err != nil {
			return threads
		}
		var decoded struct {
			Data       []map[string]any `json:"data"`
			NextCursor *string          `json:"nextCursor"`
		}
		if json.Unmarshal(response.Result, &decoded) != nil {
			return threads
		}
		threads = append(threads, decoded.Data...)
		if decoded.NextCursor == nil || *decoded.NextCursor == "" {
			return threads
		}
		cursor = *decoded.NextCursor
		if _, repeated := seenCursors[cursor]; repeated {
			return threads
		}
		seenCursors[cursor] = struct{}{}
	}
}
