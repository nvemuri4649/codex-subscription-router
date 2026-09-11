// The task details chunk supplies route ($n/sr), JSX (zE), and native Section (K).
// The account controls live in the main renderer so all surfaces stay identical.
function CodexMuxThreadSubscription() {
  const route = $n(sr).value;
  const Selector = globalThis.CodexMuxWorkflowSelector;
  if (!Selector || route.routeKind !== "local-thread") return null;
  return (0, zE.jsx)(K.Section, {
    sectionKey: "codex-personal-work",
    title: "Workflow",
    children: (0, zE.jsx)(Selector, {
      threadId: route.conversationId,
      projectKey: route.projectPath || route.cwd || undefined,
      hostId: route.hostId || "local",
    }),
  });
}
