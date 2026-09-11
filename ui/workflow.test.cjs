const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('./account-menu.js'), 'utf8').replaceAll('__CODEX_MUX_CONTROL_PORT__', '43187');
function fixture(overrides = {}) {
  const calls = [];
  const context = vm.createContext({
    URL, URLSearchParams, Event, console,
    fetch: async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => ({ ok: true }) }; },
    window: { dispatchEvent() {} },
    e7: { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    kXc: { useState: (value) => [value, () => {}], useEffect() {}, useLayoutEffect: (fn) => fn(), useMemo: (fn) => fn(), useCallback: (fn) => fn, useRef: () => ({ current: 0 }), useId: () => 'fixture' },
    ...overrides,
  });
  vm.runInContext(source, context);
  return { context, calls, run: (script) => vm.runInContext(script, context) };
}

function descend(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  const children = node.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    const found = descend(child, predicate);
    if (found) return found;
  }
  return null;
}

test('remote request uses only its supplied host transport', async () => {
  const f = fixture();
  const hostCalls = [];
  f.context.hostRequest = async (method, params) => { hostCalls.push({ method, params }); return { hostId: 'remote' }; };
  const result = await f.run('codexMuxRoutingRequest("personalWork/routing/read", {hostId:"remote",threadId:"abc"},hostRequest)');
  assert.equal(result.hostId, 'remote');
  assert.equal(hostCalls[0].method, 'personalWork/routing/read');
  assert.equal(hostCalls[0].params.threadId, 'abc');
  assert.equal(f.calls.length, 0, 'must not fetch local state for a remote host');
});

test('local reads retain explicit host scope and correctly encode project paths', async () => {
  const f = fixture();
  await f.run('codexMuxRoutingRequest("personalWork/routing/read", {hostId:"remote-ssh:box",projectKey:"/work/a b",threadId:null})');
  const url = new URL(f.calls[0].url);
  assert.equal(url.searchParams.get('hostId'), 'remote-ssh:box');
  assert.equal(url.searchParams.get('projectKey'), '/work/a b');
  assert.equal(url.searchParams.has('threadId'), false);
});

test('mode changes send the explicit task and never an account inferred from quota', async () => {
  const f = fixture();
  await f.run('codexMuxRoutingRequest("personalWork/mode/set", {threadId:"one",mode:"intensive",hostId:"local"})');
  assert.equal(f.calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(f.calls[0].options.body), { threadId: 'one', mode: 'intensive', hostId: 'local' });
  assert.match(f.calls[0].url, /\/thread-mode$/);
});

test('server readiness failures remain visible and are not presented as a ready account', () => {
  const f = fixture();
  const result = f.run('codexMuxSelectionDescription({selection:{ready:false,mode:"intensive",error:"Sign in on this host"}}, [{id:"work",label:"Work"}], "remote")');
  assert.equal(result, 'Sign in on this host');
  assert.equal(f.run('codexMuxSelectionDescription(null, [], "remote")'), 'Set up Personal & Work on this host');
});

test('HTTP errors preserve the backend explanation', async () => {
  const f = fixture({ fetch: async () => ({ ok: false, status: 409, json: async () => ({ error: 'Wait until this task is idle.' }) }) });
  await assert.rejects(() => f.run('codexMuxRequest("/thread-mode", {method:"POST"})'), /Wait until this task is idle/);
});

test('workflow radios support keyboard navigation and meaningful accessible names', () => {
  const f = fixture();
  const selected = [];
  f.context.onMode = (mode) => selected.push(mode);
  const tree = f.run('CodexMuxModeButtons({mode:"casual",onChange:onMode,label:"This task workflow"})');
  assert.equal(tree.props.role, 'radiogroup');
  assert.equal(tree.props['aria-label'], 'This task workflow');
  const [casual, intensive] = tree.props.children;
  assert.equal(casual.props.tabIndex, 0);
  assert.equal(intensive.props.tabIndex, -1);
  assert.equal(intensive.props['aria-label'], 'Intensive · Work account');
  let focus = null;
  casual.props.onKeyDown({ key: 'ArrowRight', preventDefault() {}, stopPropagation() {}, currentTarget: { parentElement: { querySelectorAll: () => [{ focus: () => { focus = 0; } }, { focus: () => { focus = 1; } }] } } });
  assert.equal(focus, 1);
  assert.deepEqual(selected, ['intensive']);
});

test('running tasks disable changes even if their callback is invoked', async () => {
  const f = fixture();
  f.run('useCodexMuxRouting=()=>({routing:{defaultMode:"casual",selection:{mode:"casual",ready:true,busy:true}},accounts:[],error:"",refresh:async()=>{}})');
  const tree = f.run('CodexMuxWorkflowSelector({threadId:"running"})');
  const radios = descend(tree, (node) => node.type?.name === 'CodexMuxModeButtons');
  assert.equal(radios.props.disabled, true);
  await radios.props.onChange('intensive');
  assert.equal(f.calls.length, 0);
});

test('account assignments prevent sharing a role and send the selected account ID', () => {
  const f = fixture();
  const assigned = [];
  f.context.onAssign = (role, accountId) => assigned.push({ role, accountId });
  const tree = f.run('CodexMuxAccountAssignments({accounts:[{id:"work",label:"Trajectory",email:"work@example.test",enabled:true},{id:"personal",email:"personal@example.test",enabled:true}],roles:{personal:null,work:"work"},busy:false,prefix:"test",onAssign})');
  const personal = descend(tree, (node) => node.type === 'select' && node.props['aria-label'] === 'Personal account');
  assert.equal(personal.props.children[1].props.disabled, true);
  assert.equal(personal.props.children[2].props.disabled, false);
  personal.props.onChange({ target: { value: 'personal' } });
  assert.deepEqual(assigned, [{ role: 'personal', accountId: 'personal' }]);
});

function draftFixture({ personalReady = true } = {}) {
  const f = fixture();
  f.context.personalReady = personalReady;
  f.run(`
    draftScopeA={};draftScopeB={};
    useCodexMuxRouting=()=>({routing:{hostId:"local",defaultMode:"casual",roleAccounts:{personal:"personal",work:"work"},selection:{projectKey:"/project",mode:"casual",source:"default",accountId:"personal",ready:personalReady,error:personalReady?"":"Personal needs sign-in"}},accounts:[{id:"personal",label:"Personal",enabled:true,connected:personalReady,authType:"chatgpt"},{id:"work",label:"Work",enabled:true,connected:true,authType:"chatgpt"}],error:"",refresh:async()=>{}});
  `);
  return f;
}

test('draft choices are isolated even for two composers on the same host and path', async () => {
  const f = draftFixture();
  const first = f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeA,hostId:"local",projectKey:"/project"})');
  f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeB,hostId:"local",projectKey:"/project"})');
  const radios = descend(first, (node) => node.type?.name === 'CodexMuxModeButtons');
  await radios.props.onChange('intensive');
  assert.equal(f.run('codexMuxDraftMetadata(draftScopeA,"local").mode'), 'intensive');
  assert.equal(f.run('codexMuxDraftMetadata(draftScopeB,"local").mode'), 'casual');
  assert.equal(f.calls.length, 0, 'choosing a draft must not mutate any default');
});

test('draft Intensive readiness comes from Work even when the Casual default is unavailable', () => {
  const f = draftFixture({ personalReady: false });
  const tree = f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeA,hostId:"local",projectKey:"/project"})');
  assert.throws(() => f.run('codexMuxDraftMetadata(draftScopeA,"local")'), /Personal needs sign-in/);
  descend(tree, (node) => node.type?.name === 'CodexMuxModeButtons').props.onChange('intensive');
  assert.equal(f.run('codexMuxDraftMetadata(draftScopeA,"local").mode'), 'intensive');
});

test('submitted draft metadata remains stable after later UI changes and rejects host drift', () => {
  const f = draftFixture();
  const tree = f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeA,hostId:"local",projectKey:"/project"})');
  const radios = descend(tree, (node) => node.type?.name === 'CodexMuxModeButtons');
  radios.props.onChange('intensive');
  const captured = f.run('codexMuxDraftMetadata(draftScopeA,"local")');
  radios.props.onChange('casual');
  assert.equal(captured.mode, 'intensive');
  assert.equal(captured.projectKey, '/project');
  assert.throws(() => f.run('codexMuxDraftMetadata(draftScopeA,"remote")'), /host changed/);
});

test('project defaults change only through the separate explicit action', async () => {
  const f = draftFixture();
  const first = f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeA,hostId:"local",projectKey:"/project"})');
  descend(first, (node) => node.type?.name === 'CodexMuxModeButtons').props.onChange('intensive');
  const second = f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeA,hostId:"local",projectKey:"/project"})');
  assert.equal(f.calls.length, 0);
  await descend(second, (node) => node.type === 'button' && node.props.children === 'Make project default').props.onClick();
  assert.equal(f.calls.length, 1);
  assert.deepEqual(JSON.parse(f.calls[0].options.body), { hostId: 'local', projectKey: '/project', mode: 'intensive' });
});

test('using a draft default does not mutate the project or global mode', () => {
  const f = draftFixture();
  const first = f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeA,hostId:"local",projectKey:"/project"})');
  descend(first, (node) => node.type?.name === 'CodexMuxModeButtons').props.onChange('intensive');
  const second = f.run('CodexMuxDraftWorkflowSelector({scope:draftScopeA,hostId:"local",projectKey:"/project"})');
  descend(second, (node) => node.type === 'button' && node.props.children === 'Use default').props.onClick();
  assert.equal(f.run('codexMuxDraftMetadata(draftScopeA,"local").mode'), 'casual');
  assert.equal(f.calls.length, 0);
});

test('remote selector transport picks up a bridge that initializes after mount', async () => {
  const f = fixture();
  const request = f.run('codexMuxHostRequest("remote")');
  await assert.rejects(() => request('personalWork/routing/read', {}), /Connecting to this host/);
  f.context.__codexPersonalWorkRequest = async (hostId, method) => ({ hostId, method });
  const result = await request('personalWork/routing/read', {});
  assert.equal(result.hostId, 'remote');
  assert.equal(f.calls.length, 0, 'a pending remote bridge never falls back to localhost');
});

test('unsupported router detection recognizes the verified official unknown-variant response', () => {
  const f = fixture();
  f.context.failure = { code: -32600, message: 'Invalid request: unknown variant `personalWork/routing/read`, expected one of `initialize`, `thread/start`' };
  assert.equal(f.run('codexMuxUnsupportedRouting(failure)'), true);
  f.context.failure = { code: -32601, message: 'Method not found: personalWork/routing/read' };
  assert.equal(f.run('codexMuxUnsupportedRouting(failure)'), true);
  f.context.failure = { cause: { code: -32600, message: 'Invalid request: unknown variant `personalWork/routing/read`, expected one of ...' } };
  assert.equal(f.run('codexMuxUnsupportedRouting(failure)'), true);
});

test('invalid params, unrelated unknown variants, and outages never imply unsupported routing', () => {
  const f = fixture();
  for (const failure of [
    { code: -32600, message: 'Invalid request: personalWork/routing/read expected hostId' },
    { code: -32600, message: 'Invalid request for personalWork/routing/read: unknown variant `remote`, expected `local`' },
    { code: -32601, message: 'Method not found' },
    { message: 'personalWork/routing/read timed out' },
    { message: 'Connection closed before personalWork/routing/read completed' },
    { message: 'Connecting to this host…' },
  ]) {
    f.context.failure = failure;
    assert.equal(f.run('codexMuxUnsupportedRouting(failure)'), false, failure.message);
  }
});

test('remote routing hook distinguishes an unsupported method from a later outage', async () => {
  const f = fixture();
  const states = [];
  let stateIndex = 0;
  f.context.kXc.useState = (initial) => {
    const index = stateIndex++;
    states[index] = initial;
    return [initial, (value) => { states[index] = value; }];
  };
  let failure = { code: -32600, message: 'Invalid request: unknown variant `personalWork/routing/read`, expected one of ...' };
  f.context.remoteRequest = async () => { throw failure; };
  const hook = f.run('useCodexMuxRouting({hostId:"remote",request:remoteRequest})');
  await hook.refresh();
  assert.equal(states[0].unsupported, true);
  assert.equal(states[0].hostId, 'remote');
  assert.equal(states[2], '');
  failure = new Error('Remote router timed out');
  await hook.refresh();
  assert.equal(states[0], null, 'a later outage must clear the earlier native-host fallback');
  assert.equal(states[2], 'Remote router timed out');
  assert.equal(f.calls.length, 0);
});

test('unconfigured remote drafts preserve native sending and disable workflow selection', () => {
  const f = fixture();
  f.run('draftScope={};useCodexMuxRouting=()=>({routing:{hostId:"remote",unsupported:true},accounts:[],error:"",refresh:async()=>{}})');
  const tree = f.run('CodexMuxDraftWorkflowSelector({scope:draftScope,hostId:"remote",projectKey:"/project"})');
  const radios = descend(tree, (node) => node.type?.name === 'CodexMuxModeButtons');
  assert.equal(radios.props.disabled, true);
  assert.equal(radios.props.mode, null);
  radios.props.onChange('intensive');
  assert.equal(f.run('codexMuxDraftMetadata(draftScope,"remote")'), null);
  assert.ok(descend(tree, (node) => node.props?.children === 'Uses this host’s current account'));
  assert.equal(f.calls.length, 0);
});

test('configured remote router outages still block sending instead of using an arbitrary account', () => {
  const f = fixture();
  f.run('draftScope={};useCodexMuxRouting=()=>({routing:null,accounts:[],error:"Remote router timed out",refresh:async()=>{}})');
  f.run('CodexMuxDraftWorkflowSelector({scope:draftScope,hostId:"remote",projectKey:"/project"})');
  assert.throws(() => f.run('codexMuxDraftMetadata(draftScope,"remote")'), /Remote router timed out/);
});

test('existing tasks on unconfigured hosts show their native account with no mode mutation', async () => {
  const f = fixture();
  f.run('useCodexMuxRouting=()=>({routing:{hostId:"remote",unsupported:true},accounts:[],error:"",refresh:async()=>{}})');
  const tree = f.run('CodexMuxWorkflowSelector({threadId:"existing",hostId:"remote"})');
  const radios = descend(tree, (node) => node.type?.name === 'CodexMuxModeButtons');
  assert.equal(radios.props.disabled, true);
  assert.equal(radios.props.mode, null);
  assert.ok(descend(tree, (node) => node.props?.children === 'Uses this host’s current account'));
  await radios.props.onChange('intensive');
  assert.equal(f.calls.length, 0);
});

const LOGIN_CODE = 'TEST-4821';
const LOGIN_URL = 'https://auth.openai.com/codex/device';
function menuEvent() {
  return {
    defaultPrevented: false, propagationStopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; },
  };
}

function menuFixture({ verificationUrl = LOGIN_URL, workEmail = 'work@example.test' } = {}) {
  const f = fixture();
  const states = [];
  const opened = [];
  let cursor = 0;
  f.context.kXc.useState = (initial) => {
    const index = cursor++;
    if (!(index in states)) states[index] = typeof initial === 'function' ? initial() : initial;
    return [states[index], (value) => { states[index] = typeof value === 'function' ? value(states[index]) : value; }];
  };
  f.context.window.open = (...args) => opened.push(args);
  f.context.workEmail = workEmail;
  f.context.fetch = async (url, options) => {
    f.calls.push({ url, options });
    const body = url.endsWith('/login')
      ? { login: { userCode: LOGIN_CODE, verificationUrl } }
      : { account: { id: 'pending-personal', label: 'Personal' } };
    return { ok: true, json: async () => body };
  };
  f.run('useCodexMuxRouting=()=>({routing:{defaultMode:"casual",roleAccounts:{personal:null,work:"work"}},accounts:[{id:"work",label:"Trajectory",email:workEmail,connected:true,enabled:true}],error:"",refresh:async()=>{}})');
  const render = () => { cursor = 0; return f.run('CodexMuxAccountMenu()'); };
  const signIn = async () => {
    const connect = descend(render(), (node) => node.type === 'button' && node.props['aria-label'] === 'Connect Personal account');
    assert.ok(connect, 'personal onboarding must be reachable from the compact menu');
    const event = menuEvent();
    await connect.props.onClick(event);
    assert.equal(event.defaultPrevented, true);
    return render();
  };
  return { ...f, render, signIn, opened };
}

test('copy uses the native clipboard and reports success only after it resolves', async () => {
  const f = menuFixture();
  const copied = [];
  const browserCopies = [];
  let resolveCopy;
  f.context.__codexPersonalWorkCopyText = (value) => {
    copied.push(value);
    return new Promise((resolve) => { resolveCopy = resolve; });
  };
  f.context.navigator = { clipboard: { writeText: async (value) => browserCopies.push(value) } };
  const tree = await f.signIn();
  const copy = descend(tree, (node) => node.type === 'button' && node.props['aria-label'] === 'Copy sign-in code');
  const event = menuEvent();
  const pending = copy.props.onClick(event);
  assert.equal(event.defaultPrevented, true, 'copy must not dismiss the surrounding menu');
  assert.equal(event.propagationStopped, true);
  assert.deepEqual(copied, [LOGIN_CODE]);
  assert.deepEqual(browserCopies, [], 'native clipboard has priority');
  assert.equal(descend(f.render(), (node) => node.props?.children === 'Code copied to clipboard'), null);
  assert.equal(f.opened.length, 0, 'copy must not open a browser or lose focus');
  resolveCopy();
  await pending;
  assert.ok(descend(f.render(), (node) => node.props?.children === 'Code copied to clipboard'));
});

test('clipboard failure keeps the code available and does not claim it was copied', async () => {
  const f = menuFixture();
  let fail = false;
  f.context.__codexPersonalWorkCopyText = async () => { if (fail) throw new Error('Native clipboard unavailable'); };
  const tree = await f.signIn();
  await descend(tree, (node) => node.type === 'button' && node.props['aria-label'] === 'Copy sign-in code').props.onClick(menuEvent());
  assert.ok(descend(f.render(), (node) => node.props?.children === 'Code copied to clipboard'));
  fail = true;
  await descend(f.render(), (node) => node.type === 'button' && node.props['aria-label'] === 'Copy sign-in code').props.onClick(menuEvent());
  const result = f.render();
  assert.equal(descend(result, (node) => node.props?.children === 'Code copied to clipboard'), null);
  assert.ok(descend(result, (node) => node.props.role === 'alert' && node.props.children === 'Select the code and press ⌘C to copy it.'));
  assert.equal(descend(result, (node) => node.type === 'input').props.value, LOGIN_CODE);
  assert.equal(f.opened.length, 0);
});

test('web clipboard is used only when the native bridge is absent', async () => {
  const copied = [];
  const f = fixture({ navigator: { clipboard: { writeText: async (value) => copied.push(value) } } });
  f.context.testCode = LOGIN_CODE;
  await f.run('codexMuxCopyText(testCode)');
  assert.deepEqual(copied, [LOGIN_CODE]);
  delete f.context.navigator;
  await assert.rejects(() => f.run('codexMuxCopyText(testCode)'), /Select the code and press/);
});

test('opening sign-in is separate from copying and never adds the code to the URL', async () => {
  const f = menuFixture();
  const copied = [];
  f.context.__codexPersonalWorkCopyText = async (value) => copied.push(value);
  const tree = await f.signIn();
  descend(tree, (node) => node.type === 'button' && node.props.children === 'Open sign-in page ↗').props.onClick(menuEvent());
  assert.deepEqual(copied, []);
  assert.deepEqual(f.opened, [[LOGIN_URL, '_blank', 'noopener,noreferrer']]);
  assert.equal(f.opened[0][0].includes(LOGIN_CODE), false);
  assert.equal(new URL(f.opened[0][0]).search, '');
});

test('a sign-in page outside the expected HTTPS hosts is rejected without copying', async () => {
  for (const verificationUrl of ['https://auth.openai.com.example.test/device', 'http://auth.openai.com/device']) {
    const f = menuFixture({ verificationUrl });
    const tree = await f.signIn();
    descend(tree, (node) => node.type === 'button' && node.props.children === 'Open sign-in page ↗').props.onClick(menuEvent());
    assert.equal(f.opened.length, 0);
    assert.ok(descend(f.render(), (node) => node.props?.role === 'alert'));
  }
});

test('login code is read-only, selectable, and has an accessible independent copy action', async () => {
  const f = menuFixture();
  const tree = await f.signIn();
  const input = descend(tree, (node) => node.type === 'input' && node.props['aria-label'] === 'Sign-in code');
  assert.equal(input.props.readOnly, true);
  assert.equal(input.props.value, LOGIN_CODE);
  assert.equal(input.props.style.userSelect, 'text');
  assert.equal(input.props.style.WebkitUserSelect, 'text');
  let selected = 0;
  const event = { currentTarget: { select: () => selected++ } };
  input.props.onFocus(event);
  input.props.onClick(event);
  assert.equal(selected, 2, 'both keyboard focus and clicking should select the entire code');
  assert.ok(descend(tree, (node) => node.type === 'button' && node.props['aria-label'] === 'Copy sign-in code'));
  assert.equal(descend(tree, (node) => node.type === 'select'), null, 'login should replace the settings panel');
  const keyboard = { key: 'c', metaKey: true, ...menuEvent() };
  tree.props.onKeyDown(keyboard);
  assert.equal(keyboard.propagationStopped, true);
  assert.equal(keyboard.defaultPrevented, false, 'Cmd+C must retain native browser copying');
});

test('long account identities stay inspectable while summary and assignment controls can shrink', () => {
  const workEmail = `${'long.account.'.repeat(18)}example@trajectory.example.test`;
  const f = menuFixture({ workEmail });
  const summary = f.render();
  const identity = descend(summary, (node) => node.props?.title === workEmail);
  assert.equal(identity.props.children, workEmail, 'the full identity remains available to assistive tools and hover');
  assert.equal(summary.props.style.minWidth, 0);
  assert.equal(summary.props.style.maxWidth, '100%');
  assert.match(identity.props.className, /truncate/);
  descend(summary, (node) => node.type === 'button' && node.props.children === 'Manage').props.onClick(menuEvent());
  const managing = f.render();
  const assignments = descend(managing, (node) => node.type?.name === 'CodexMuxAccountAssignments');
  assert.ok(assignments);
  assert.equal(descend(managing, (node) => node.props?.title === workEmail), null, 'expanded settings replace summary rows');
  const fields = assignments.type(assignments.props);
  const work = descend(fields, (node) => node.type === 'select' && node.props['aria-label'] === 'Work account');
  assert.equal(work.props.style.minWidth, 0);
  assert.equal(work.props.style.maxWidth, '100%');
  assert.equal(work.props.children[1].props.children, workEmail);
  assert.equal(work.props.children[1].props.value, 'work');
});
