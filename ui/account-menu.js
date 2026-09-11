// Injected into the app's renderer. The patcher supplies React (kXc) and JSX (e7).
const CODEX_MUX_API = "http://127.0.0.1:__CODEX_MUX_CONTROL_PORT__/v1";
const CODEX_MUX_TOKEN = "__CODEX_MUX_CONTROL_TOKEN__";
const CODEX_MUX_MODES = [
  { id: "casual", label: "Casual", role: "personal", description: "Personal account" },
  { id: "intensive", label: "Intensive", role: "work", description: "Work account" },
];
let codexMuxLoginActive = false;

function CodexMuxProfileMenuOpenChange(setOpen) {
  return (nextOpen) => {
    if (!nextOpen && codexMuxLoginActive) return;
    setOpen(nextOpen);
  };
}

async function codexMuxRequest(path, options = {}) {
  const response = await fetch(`${CODEX_MUX_API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Codex-Mux-Token": CODEX_MUX_TOKEN,
      ...options.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

// A host-aware app integration can supply request(method, params) using its
// existing host RPC connection. No credentials cross this renderer boundary.
async function codexMuxRoutingRequest(method, params = {}, request = null) {
  if (request) return request(method, params);
  const suffix = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  ).toString();
  if (method === "personalWork/routing/read") {
    return codexMuxRequest(`/routing${suffix ? `?${suffix}` : ""}`);
  }
  const path = method === "personalWork/mode/set" ? "/thread-mode" : "/routing";
  return codexMuxRequest(path, { method: "POST", body: JSON.stringify(params) });
}

function codexMuxHostRequest(hostId) {
  if (!hostId || hostId === "local") return null;
  return (method, params) => {
    const bridge = globalThis.__codexPersonalWorkRequest;
    return bridge ? bridge(hostId, method, params) : Promise.reject(new Error("Connecting to this host…"));
  };
}

function codexMuxBroadcastChange() {
  window.dispatchEvent(new Event("codex-personal-work-changed"));
}

// Official app-server 8576 rejects this extension with -32600 "unknown
// variant", while other versions use -32601. An exact unsupported method is
// different from a router that is configured but temporarily unreachable.
function codexMuxUnsupportedRouting(failure) {
  const method = "personalWork/routing/read";
  return [failure, failure?.error, failure?.cause, failure?.cause?.error].some((item) => {
    const message = typeof item?.message === "string" ? item.message : "";
    if (!message.toLowerCase().includes(method.toLowerCase())) return false;
    return /\bunknown (?:variant|method)\s*[:=]?\s*[`'"]?personalWork\/routing\/read(?:[`'"]|[\s,.:]|$)/i.test(message)
      || ((item.code == null || item.code === -32601) && /\bmethod not found\b/i.test(message));
  });
}

function useCodexMuxRouting({ threadId, projectKey, hostId, request } = {}) {
  const [routing, setRouting] = kXc.useState(null);
  const [accounts, setAccounts] = kXc.useState([]);
  const [error, setError] = kXc.useState("");
  const generation = kXc.useRef(0);
  const refresh = kXc.useCallback(async () => {
    const current = ++generation.current;
    try {
      const [state, accountResult] = await Promise.all([
        codexMuxRoutingRequest("personalWork/routing/read", { threadId, projectKey, hostId }, request),
        // Host RPC routing results may include accounts. Local accounts are
        // fetched only for a local selector, never presented as remote logins.
        !request && (!hostId || hostId === "local")
          ? codexMuxRequest("/accounts")
          : Promise.resolve({ accounts: [] }),
      ]);
      if (current !== generation.current) return;
      setRouting(state);
      setAccounts(state.accounts || accountResult.accounts || []);
      setError("");
      return state;
    } catch (failure) {
      if (current !== generation.current) return;
      if (hostId && hostId !== "local" && request && codexMuxUnsupportedRouting(failure)) {
        setRouting({ hostId, unsupported: true });
        setAccounts([]);
        setError("");
      } else {
        setRouting(null);
        setError(failure.message || "Account settings are unavailable.");
      }
    }
  }, [threadId, projectKey, hostId, request]);
  kXc.useEffect(() => {
    setRouting(null);
    setError("");
    refresh();
    const changed = () => refresh();
    window.addEventListener("codex-personal-work-changed", changed);
    const timer = setInterval(changed, 15_000);
    // The SSE connection belongs to this local router. Remote RPC hosts are
    // refreshed through their own connection or on the next poll.
    const events = !request && (!hostId || hostId === "local")
      ? new EventSource(`${CODEX_MUX_API}/events?token=${encodeURIComponent(CODEX_MUX_TOKEN)}`)
      : null;
    if (events) events.onmessage = changed;
    return () => {
      generation.current += 1;
      clearInterval(timer);
      events?.close();
      window.removeEventListener("codex-personal-work-changed", changed);
    };
  }, [refresh, hostId, request]);
  return { routing, accounts, error, refresh };
}

function CodexMuxModeButtons({ mode, disabled, onChange, label = "Workflow" }) {
  const selectedIndex = Math.max(0, CODEX_MUX_MODES.findIndex((item) => item.id === mode));
  return (0, e7.jsx)("div", {
    role: "radiogroup",
    "aria-label": label,
    className: "flex items-center gap-1 rounded-lg bg-token-foreground/5 p-1",
    style: { minWidth: 160, fontSize: 12, lineHeight: "16px" },
    children: CODEX_MUX_MODES.map((item, index) => (0, e7.jsx)("button", {
      type: "button",
      role: "radio",
      "aria-checked": mode === item.id,
      "aria-label": `${item.label} · ${item.description}`,
      tabIndex: index === selectedIndex ? 0 : -1,
      disabled,
      title: `${item.label} uses your ${item.role} account`,
      className: `flex-1 rounded-md px-3 py-1 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-token-focus-border disabled:opacity-50 ${mode === item.id ? "bg-token-bg-primary text-token-text-primary shadow-sm" : "text-token-text-secondary hover:bg-token-foreground/5"}`,
      onClick: () => onChange(item.id),
      onKeyDown: (event) => {
        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        event.stopPropagation();
        if (disabled) return;
        const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
        event.currentTarget.parentElement?.querySelectorAll('[role="radio"]')[nextIndex]?.focus();
        onChange(CODEX_MUX_MODES[nextIndex].id);
      },
      children: item.label,
    }, item.id)),
  });
}

function codexMuxSelectionDescription(routing, accounts, hostId) {
  if (routing?.unsupported) return "Uses this host’s current account";
  const selected = routing?.selection;
  const accountId = selected?.accountId;
  const account = accounts.find((item) => item.id === accountId);
  if (!selected) return hostId && hostId !== "local" ? "Set up Personal & Work on this host" : "Loading account…";
  if (selected.error) return selected.error;
  if (!selected.ready) return "Connect an account in the profile menu";
  const role = selected.mode === "intensive" ? "Work" : selected.mode === "casual" ? "Personal" : "Current account";
  const identity = account?.email || account?.label;
  return identity ? `${role} · ${identity}` : role;
}

// Props are explicit so the same compact control can live in the composer or
// task details without guessing a project's host from DOM text or task IDs.
function CodexMuxWorkflowSelector({ threadId, projectKey, hostId = "local", busy = false, request = null, compact = false } = {}) {
  const hostRequest = kXc.useMemo(() => request || codexMuxHostRequest(hostId), [hostId, request]);
  const { routing, accounts, error: loadError, refresh } = useCodexMuxRouting({ threadId, projectKey, hostId, request: hostRequest });
  const [saving, setSaving] = kXc.useState(false);
  const [error, setError] = kXc.useState("");
  const selection = routing?.selection;
  const mode = routing?.unsupported ? null : selection?.mode || (threadId ? null : routing?.defaultMode || "casual");
  const running = busy || selection?.busy;
  const label = threadId ? "This task" : projectKey ? "Project default" : "New tasks";
  const description = codexMuxSelectionDescription(routing, accounts, hostId);
  async function changeMode(nextMode) {
    if (!routing || routing.unsupported || saving || running || (nextMode === mode && selection?.mode)) return;
    setSaving(true);
    setError("");
    try {
      await codexMuxRoutingRequest("personalWork/mode/set", { threadId, projectKey, hostId, mode: nextMode }, hostRequest);
      await refresh();
      codexMuxBroadcastChange();
    } catch (failure) {
      setError(failure.message || "The workflow could not be changed.");
    } finally {
      setSaving(false);
    }
  }
  return (0, e7.jsxs)("div", {
    "data-codex-personal-work": "workflow",
    className: compact ? "flex min-w-0 items-center gap-2" : "space-y-2 py-1",
    style: { maxWidth: compact ? 340 : undefined },
    children: [
      (0, e7.jsxs)("div", {
        className: compact ? "min-w-0" : "flex min-w-0 items-center justify-between gap-3",
        children: [
          !compact ? (0, e7.jsx)("span", { className: "text-xs text-token-text-secondary", children: label }) : null,
          (0, e7.jsx)(CodexMuxModeButtons, { mode, disabled: saving || running || !routing || routing.unsupported, onChange: changeMode, label: `${label} workflow` }),
        ],
      }),
      (0, e7.jsxs)("div", {
        className: "min-w-0 text-xs text-token-text-secondary",
        style: { lineHeight: "16px" },
        children: [
          (0, e7.jsx)("div", {
            role: "status",
            "aria-live": "polite",
            className: "truncate",
            title: error || loadError || description,
            children: error || loadError || (saving ? "Updating workflow…" : running ? `${description} · Task running` : description),
          }),
          !compact && hostId !== "local" ? (0, e7.jsx)("div", { className: "mt-1 truncate text-token-text-tertiary", children: `Host: ${hostId}` }) : null,
          !compact && projectKey && !threadId ? (0, e7.jsx)("div", { className: "mt-1 text-token-text-tertiary", children: "Used for new tasks in this project." }) : null,
          !compact && threadId && selection?.source === "project" ? (0, e7.jsx)("div", { className: "mt-1 text-token-text-tertiary", children: "Using the project default." }) : null,
        ],
      }),
    ],
  });
}

function CodexMuxAccountMenu() {
  const { routing, accounts, error: loadError, refresh } = useCodexMuxRouting();
  const [busy, setBusy] = kXc.useState(false);
  const [error, setError] = kXc.useState("");
  const [login, setLogin] = kXc.useState(null);
  const [codeCopied, setCodeCopied] = kXc.useState(false);
  const roles = routing?.roleAccounts || {};
  const prefix = kXc.useId();
  const connected = accounts.filter((account) => account.connected && account.enabled);
  const missingRole = ["personal", "work"].find((role) => !connected.some((account) => account.id === roles[role]));

  async function assignRole(role, accountId) {
    setBusy(true);
    setError("");
    try {
      await codexMuxRoutingRequest("personalWork/routing/update", { roleAccounts: { ...roles, [role]: accountId || null } });
      await refresh();
      codexMuxBroadcastChange();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  kXc.useEffect(() => {
    if (!login) return;
    const account = accounts.find((item) => item.id === login.accountId && item.connected);
    if (account) {
      codexMuxLoginActive = false;
      const role = login.role;
      setLogin(null);
      if (role) assignRole(role, account.id);
    }
  }, [accounts, login]);
  kXc.useEffect(() => {
    const dismiss = (event) => {
      if (event.key !== "Escape" || !login) return;
      codexMuxLoginActive = false;
      setLogin(null);
    };
    window.addEventListener("keydown", dismiss, true);
    return () => {
      window.removeEventListener("keydown", dismiss, true);
      codexMuxLoginActive = false;
    };
  }, [login]);

  async function connectAccount(role, event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const label = role === "personal" ? "Personal" : role === "work" ? "Work" : "Account";
      const pending = accounts.find((item) => !item.connected && item.id === roles[role]) || accounts.find((item) => !item.connected && item.label === label);
      const created = pending ? { account: pending } : await codexMuxRequest("/accounts", { method: "POST", body: JSON.stringify({ label }) });
      const result = await codexMuxRequest(`/accounts/${encodeURIComponent(created.account.id)}/login`, { method: "POST", body: JSON.stringify({ mode: "chatgptDeviceCode" }) });
      if (!result.login) throw new Error("Sign-in did not start. Try again.");
      codexMuxLoginActive = true;
      setCodeCopied(false);
      setLogin({ ...result.login, accountId: created.account.id, role });
      await refresh();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  async function continueLogin(event) {
    event.preventDefault();
    const userCode = login?.userCode || "";
    try {
      const destination = new URL(login?.verificationUrl || login?.authUrl || "");
      if (destination.protocol !== "https:" || !["chatgpt.com", "auth.openai.com"].includes(destination.hostname)) throw new Error("The sign-in page is not recognized.");
      // Start clipboard access while the click still has user activation.
      const copy = userCode ? navigator.clipboard.writeText(userCode) : Promise.resolve();
      window.open(destination.href, "_blank", "noopener,noreferrer");
      await copy;
      setCodeCopied(Boolean(userCode));
    } catch (failure) {
      setError(failure.message || "The sign-in page could not be opened.");
    }
  }

  return (0, e7.jsxs)("div", {
    "data-codex-personal-work": "accounts",
    role: "group",
    "aria-label": "Personal and work accounts",
    className: "px-2 py-2",
    style: { minWidth: 270, maxWidth: 340 },
    onKeyDown: (event) => {
      if (event.target.tagName === "SELECT" && event.key !== "Escape") event.stopPropagation();
    },
    children: [
      (0, e7.jsx)("div", { className: "px-1 pb-2 text-xs font-medium text-token-text-secondary", children: "Personal & Work" }),
      ...CODEX_MUX_MODES.map((item) => {
        const account = accounts.find((candidate) => candidate.id === roles[item.role]);
        const otherRole = item.role === "personal" ? "work" : "personal";
        return (0, e7.jsxs)("div", {
          className: "flex items-center gap-2 rounded-lg px-1 py-2",
          children: [
            (0, e7.jsx)(CodexMuxAccountAvatar, { label: item.role === "personal" ? "Personal" : "Work", imageUrl: account?.profileImageUrl, className: "size-7 shrink-0" }),
            (0, e7.jsxs)("div", {
              className: "min-w-0 flex-1",
              children: [
                (0, e7.jsx)("label", { htmlFor: `${prefix}-${item.role}`, className: "block text-sm font-medium text-token-text-primary", children: item.role === "personal" ? "Personal" : "Work" }),
                (0, e7.jsx)("div", { className: "text-xs text-token-text-tertiary", children: `${item.label}${account && !account.connected ? " · Sign in again" : ""}` }),
              ],
            }),
            (0, e7.jsxs)("select", {
              id: `${prefix}-${item.role}`,
              value: roles[item.role] || "",
              disabled: busy || !routing,
              "aria-label": `${item.role === "personal" ? "Personal" : "Work"} account`,
              title: account?.email || account?.label || "Choose an account",
              className: "max-w-40 rounded-md border border-token-border bg-token-bg-primary px-2 py-1 text-xs text-token-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-token-focus-border",
              style: { fontFamily: "inherit", minWidth: 132 },
              onChange: (event) => assignRole(item.role, event.target.value),
              children: [
                (0, e7.jsx)("option", { value: "", children: "Not assigned" }),
                ...accounts.filter((candidate) => candidate.enabled || candidate.id === roles[item.role]).map((candidate) => (0, e7.jsx)("option", {
                  value: candidate.id,
                  disabled: candidate.id === roles[otherRole],
                  children: candidate.email || candidate.label || candidate.id,
                }, candidate.id)),
              ],
            }),
          ],
        }, item.id);
      }),
      (0, e7.jsx)("div", { className: "my-2 border-t border-token-border" }),
      (0, e7.jsx)(CodexMuxWorkflowSelector, {}),
      (0, e7.jsx)("div", { className: "my-2 border-t border-token-border" }),
      login ? (0, e7.jsxs)("div", {
        className: "space-y-2 px-1 py-1",
        children: [
          (0, e7.jsx)("div", { className: "text-xs text-token-text-secondary", children: `Sign in to ${login.role === "work" ? "your work" : login.role === "personal" ? "your personal" : "an"} account in your browser.` }),
          login.userCode ? (0, e7.jsx)("div", { className: "font-mono text-sm text-token-text-primary", children: login.userCode }) : null,
          (0, e7.jsx)("button", { type: "button", onClick: continueLogin, className: "w-full rounded-lg bg-token-foreground/5 px-3 py-2 text-left text-sm text-token-text-primary hover:bg-token-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-token-focus-border", children: codeCopied ? "Code copied · Continue sign-in" : "Copy code and sign in" }),
        ],
      }) : (0, e7.jsx)("button", {
        type: "button",
        role: "menuitem",
        disabled: busy || !routing,
        onClick: (event) => connectAccount(missingRole || null, event),
        className: "flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-token-text-primary hover:bg-token-foreground/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-token-focus-border disabled:opacity-50",
        children: busy ? "Connecting…" : missingRole ? `${roles[missingRole] ? "Sign in to" : "Connect"} ${missingRole} account…` : "Connect another account…",
      }),
      error || loadError ? (0, e7.jsx)("div", { role: "alert", className: "px-1 pt-2 text-xs text-token-text-secondary", children: error || loadError }) : null,
      connected.length ? (0, e7.jsx)("div", { className: "px-1 pt-2 text-xs text-token-text-tertiary", children: "Each task uses the account you choose." }) : null,
    ],
  });
}

function CodexMuxAccountAvatar({ imageUrl, label = "Account", className = "size-7" }) {
  const [failed, setFailed] = kXc.useState(false);
  kXc.useEffect(() => setFailed(false), [imageUrl]);
  if (imageUrl?.startsWith("https://") && !failed) return (0, e7.jsx)("img", {
    src: imageUrl,
    alt: "",
    className: `${className} rounded-full object-cover`,
    referrerPolicy: "no-referrer",
    onError: () => setFailed(true),
  });
  const initials = label.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
  return (0, e7.jsx)("span", {
    className: `${className} flex items-center justify-center rounded-full bg-token-foreground/5 text-token-text-secondary`,
    style: { fontSize: 11, fontWeight: 500 },
    "aria-hidden": true,
    children: initials || "?",
  });
}

globalThis.CodexMuxAccountAvatar = CodexMuxAccountAvatar;
globalThis.CodexMuxWorkflowSelector = CodexMuxWorkflowSelector;

// Draft choices belong to the actual composer scope, never a host-wide mutable
// selection. A submit captures this value before asynchronous task preparation.
const codexMuxDraftChoices = new WeakMap();
const codexMuxDraftSnapshots = new WeakMap();

function codexMuxDraftSelection(routing, accounts, mode) {
  if (!mode) return routing?.selection || null;
  const role = mode === "intensive" ? "work" : "personal";
  const accountId = routing?.roleAccounts?.[role];
  const account = accounts.find((item) => item.id === accountId);
  const ready = Boolean(account?.enabled && account?.connected && account?.authType === "chatgpt" && !account?.error);
  return {
    mode, accountId, source: "draft", ready,
    error: ready ? "" : account?.error || `Connect and assign your ${role} account to use ${mode === "intensive" ? "Intensive" : "Casual"}.`,
  };
}

function codexMuxDraftMetadata(scope, hostId) {
  const snapshot = codexMuxDraftSnapshots.get(scope);
  if (!snapshot) return null;
  if (snapshot.hostId !== hostId) throw new Error("The task's host changed. Choose its workflow again before sending.");
  if (snapshot.unsupported && hostId !== "local") return null;
  if (!snapshot.selection?.ready) throw new Error(snapshot.error || snapshot.selection?.error || "Account settings are still loading. Try sending again in a moment.");
  return { mode: snapshot.selection.mode, hostId, ...(snapshot.projectKey ? { projectKey: snapshot.projectKey } : {}) };
}

function CodexMuxDraftWorkflowSelector({ scope, projectKey, hostId = "local", busy = false }) {
  const request = kXc.useMemo(() => codexMuxHostRequest(hostId), [hostId]);
  const { routing, accounts, error: loadError, refresh } = useCodexMuxRouting({ projectKey, hostId, request });
  const [, render] = kXc.useState(0);
  const [saving, setSaving] = kXc.useState(false);
  const [error, setError] = kXc.useState("");
  const contextKey = JSON.stringify([hostId, projectKey || ""]);
  const modeOverride = codexMuxDraftChoices.get(scope)?.get(contextKey) || null;
  const unsupported = routing?.hostId === hostId && routing.unsupported === true;
  const current = !unsupported && routing?.hostId === hostId && (routing.selection?.projectKey || "") === (projectKey || "") ? routing : null;
  const selection = unsupported ? null : codexMuxDraftSelection(current, accounts, modeOverride);
  const mode = selection?.mode || null;
  const description = loadError || codexMuxSelectionDescription({ selection, unsupported }, accounts, hostId);
  kXc.useLayoutEffect(() => {
    const snapshot = { hostId, projectKey, unsupported, selection: current ? selection : null, error: loadError };
    codexMuxDraftSnapshots.set(scope, snapshot);
    return () => {
      if (codexMuxDraftSnapshots.get(scope) === snapshot) codexMuxDraftSnapshots.delete(scope);
    };
  }, [scope, hostId, projectKey, current, accounts, modeOverride, loadError, unsupported]);

  function chooseMode(nextMode) {
    if (busy || saving || !current) return;
    let choices = codexMuxDraftChoices.get(scope);
    if (!choices) { choices = new Map(); codexMuxDraftChoices.set(scope, choices); }
    choices.set(contextKey, nextMode);
    codexMuxDraftSnapshots.set(scope, { hostId, projectKey, selection: codexMuxDraftSelection(current, accounts, nextMode) });
    setError("");
    render((value) => value + 1);
  }
  async function saveProjectDefault() {
    if (!projectKey || !modeOverride || !current || saving || busy) return;
    setSaving(true);
    setError("");
    try {
      await codexMuxRoutingRequest("personalWork/mode/set", { hostId, projectKey, mode: modeOverride }, request);
      codexMuxDraftChoices.get(scope)?.delete(contextKey);
      await refresh();
      codexMuxBroadcastChange();
    } catch (failure) {
      setError(failure.message || "The project default could not be saved.");
    } finally { setSaving(false); }
  }
  return (0, e7.jsxs)("div", {
    "data-codex-personal-work": "draft",
    className: "flex flex-wrap items-center justify-between gap-2 px-3 pt-2",
    children: [
      (0, e7.jsx)(CodexMuxModeButtons, { mode, disabled: busy || saving || !current, onChange: chooseMode, label: "This task workflow" }),
      (0, e7.jsxs)("div", {
        className: "min-w-0 text-right text-xs text-token-text-secondary",
        style: { maxWidth: 240, lineHeight: "16px" },
        children: [
          (0, e7.jsx)("div", { role: "status", "aria-live": "polite", className: "truncate", title: error || description, children: error || description }),
          (0, e7.jsxs)("div", { className: "flex justify-end gap-2 text-token-text-tertiary", children: [
            !unsupported && modeOverride ? (0, e7.jsx)("button", { type: "button", disabled: busy || saving, onClick: () => chooseMode(null), className: "rounded-sm hover:text-token-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-token-focus-border", title: "Use the default for this project or host", children: "Use default" }) : (0, e7.jsx)("span", { children: unsupported ? "Personal & Work not configured" : current?.selection?.source === "project" ? "Project default" : "Default" }),
            !unsupported && modeOverride && projectKey ? (0, e7.jsx)("button", { type: "button", disabled: busy || saving, onClick: saveProjectDefault, className: "rounded-sm hover:text-token-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-token-focus-border", children: saving ? "Saving…" : "Make project default" }) : null,
          ] }),
        ],
      }),
    ],
  });
}

globalThis.CodexMuxDraftWorkflowSelector = CodexMuxDraftWorkflowSelector;
globalThis.__codexPersonalWorkDraftMetadata = codexMuxDraftMetadata;
