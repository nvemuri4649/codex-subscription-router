"""Reviewed composer patch for Codex macOS 26.903.71938 (8576).

Only small anchors are stored here; no proprietary renderer source is copied.
A draft mode is captured from that composer's scope before asynchronous work,
then travels on the task's own creation request. Project defaults change only
through the UI's explicit Make project default action.
"""
from pathlib import Path

PRIMARY = "app-primary-defe25a79fce.js"
INITIAL = "app-initial-a9514281e192.js"

PRIMARY_PATCHES = [
    (
        "freeze draft at the send action before preparation awaits",
        "if(oe==null&&u&&F.maybeShow())return;let ge=S&&p?.type===`local`?y8r(le):null",
        "if(oe==null&&u&&F.maybeShow())return;let codexPersonalWork=null;try{codexPersonalWork=c==null&&K.type!==`cloud`?globalThis.__codexPersonalWorkDraftMetadata?.(e,K.executionOptions?.hostId??b):null}catch(codexPersonalWorkError){_(codexPersonalWorkError);return}let ge=S&&p?.type===`local`?y8r(le):null",
    ),
    (
        "carry frozen draft through context preparation",
        "Ee={...t,threadReferences:n,...re==null?{}:{navigation:re}",
        "Ee={...t,...codexPersonalWork?{_codexWorkflow:codexPersonalWork}:{},threadReferences:n,...re==null?{}:{navigation:re}",
    ),
    (
        "new task workflow control",
        "Xc=(0,P9.jsxs)(P9.Fragment,{children:[null,(0,P9.jsxs)(`div`,{className:`contents`,inert:Yc",
        "Xc=(0,P9.jsxs)(P9.Fragment,{children:[q.value.kind===`new`&&qe!==`cloud`&&globalThis.CodexMuxDraftWorkflowSelector?(0,P9.jsx)(globalThis.CodexMuxDraftWorkflowSelector,{scope:q,projectKey:Un||Et?void 0:qe===`worktree`?Yr:xi,hostId:Lr,busy:Ns||hn||!Jr}):null,(0,P9.jsxs)(`div`,{className:`contents`,inert:Yc",
    ),
    (
        "capture local draft before async preparation",
        "P=async(n,r,i,a,c,l)=>{let{context:u,memoryPreferences:d}=await N(n)",
        "P=async(n,r,i,a,c,l)=>{const codexPersonalWork=n._codexWorkflow??globalThis.__codexPersonalWorkDraftMetadata?.(e,a?.hostId??w);let{context:u,memoryPreferences:d}=await N(n)",
    ),
    (
        "preserve local draft on start params",
        "O.clientUserMessageId=c,S.threadStartKind!=null&&(O.threadStartKind=S.threadStartKind)",
        "codexPersonalWork&&(O._codexWorkflow=codexPersonalWork),O.clientUserMessageId=c,S.threadStartKind!=null&&(O.threadStartKind=S.threadStartKind)",
    ),
    (
        "capture worktree draft before async preparation",
        "F=async(n,r,i,l,u,d)=>{let f=u?.workspaceRoots??n.workspaceRoots??[r],p=u?.hostId??w",
        "F=async(n,r,i,l,u,d)=>{const codexPersonalWork=n._codexWorkflow??globalThis.__codexPersonalWorkDraftMetadata?.(e,u?.hostId??w);let f=u?.workspaceRoots??n.workspaceRoots??[r],p=u?.hostId??w",
    ),
    (
        "persist draft with pending worktree",
        "g.threadStartKind!=null&&(x.threadStartKind=g.threadStartKind),g.mode!=null&&(x.mode=g.mode);let S=[],C=null",
        "codexPersonalWork&&(x._codexWorkflow=codexPersonalWork),g.threadStartKind!=null&&(x.threadStartKind=g.threadStartKind),g.mode!=null&&(x.mode=g.mode);let S=[],C=null",
    ),
]

INITIAL_PATCHES = [
    (
        "accept persisted worktree workflow in request normalizer",
        "requiresThreadReferences:k},{allowProjectlessWithoutOutputDirectory:A=!1}={})",
        "requiresThreadReferences:k,_codexWorkflow:codexPersonalWork},{allowProjectlessWithoutOutputDirectory:A=!1}={})",
    ),
    (
        "preserve persisted worktree workflow after normalization",
        "requiresThreadReferences:k}}var elo=",
        "requiresThreadReferences:k,...codexPersonalWork?{_codexWorkflow:codexPersonalWork}:{}}}var elo=",
    ),
    (
        "pass workflow into task creation",
        "this.threadCreation.createConversation({clientUserMessageId:_,cloudThreadPrototype:e.cloudThreadPrototype",
        "this.threadCreation.createConversation({_codexWorkflow:e._codexWorkflow,clientUserMessageId:_,cloudThreadPrototype:e.cloudThreadPrototype",
    ),
    (
        "avoid prewarmed tasks belonging to another account",
        "try{u.canUsePrewarmedThread&&u.permissionsConfig!=null&&this.params.prewarmedThreadManager.hasPrewarmedThread",
        "try{!e._codexWorkflow&&u.canUsePrewarmedThread&&u.permissionsConfig!=null&&this.params.prewarmedThreadManager.hasPrewarmedThread",
    ),
    (
        "attach private workflow metadata to the exact thread start",
        "this.params.requestClient.sendRequest(p.method,p.request,{...p.options,onOutcomeUnknown:n})",
        "this.params.requestClient.sendRequest(p.method,e._codexWorkflow?{...p.request,_codexWorkflow:e._codexWorkflow}:p.request,{...p.options,onOutcomeUnknown:n})",
    ),
]


def _patched(text: str, patches: list[tuple[str, str, str]]) -> str:
    for label, old, new in patches:
        count = text.count(old)
        if count != 1:
            raise RuntimeError(f"Composer patch {label}: expected one reviewed anchor, found {count}")
        text = text.replace(old, new, 1)
    return text


def patch_composer(extracted: Path) -> None:
    """Patch the reviewed extracted app; reject drift before writing any file."""
    assets = extracted / "webview" / "assets"
    primary, initial = assets / PRIMARY, assets / INITIAL
    if not primary.is_file() or not initial.is_file():
        raise RuntimeError("Composer controls require the reviewed Codex build 8576 renderer")
    new_primary = _patched(primary.read_text(), PRIMARY_PATCHES)
    new_initial = _patched(initial.read_text(), INITIAL_PATCHES)
    primary.write_text(new_primary)
    initial.write_text(new_initial)
