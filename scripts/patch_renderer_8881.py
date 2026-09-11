"""Port the upstream Subscription Router renderer to official build 8881.

Keep the upstream components in ui/ as the design and behavior source. Only
their native module bindings and the reviewed insertion points differ here.
"""

from pathlib import Path
import json
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRIMARY_BUNDLE = "app-primary-44ec287874b7.js"
THREAD_BUNDLE = "local-conversation-thread-d531b243ea4e.js"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"build 8881 {label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)


def _component(name: str, token: str, port: int) -> str:
    source = (PROJECT_ROOT / "ui" / name).read_text(encoding="utf-8")
    source = source.replace("__CODEX_MUX_CONTROL_PORT__", str(port))
    return source.replace('"__CODEX_MUX_CONTROL_TOKEN__"', json.dumps(token))


def patch_renderer_8881(extracted: Path, token: str, port: int) -> None:
    """Patch account menus and task subscription controls; reject bundle drift."""
    if not 1 <= port <= 65535:
        raise ValueError("control port must be between 1 and 65535")
    assets = extracted / "webview" / "assets"
    primary_path = assets / PRIMARY_BUNDLE
    thread_path = assets / THREAD_BUNDLE
    index_path = extracted / "webview" / "index.html"
    primary = primary_path.read_text(encoding="utf-8")
    thread = thread_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")
    if "function CodexMuxAccountMenu(" in primary:
        raise RuntimeError("source renderer already contains Subscription Router")
    if "function CodexMuxThreadSubscription(" in thread:
        raise RuntimeError("source task renderer already contains Subscription Router")

    account_component = _component("account-menu.js", token, port)
    for old, new in (
        ("e7", "Gz"),
        ("kXc", "vGt"),
        ("_H", "kg"),
        ("CH", "tS"),
        ("BW", "ud"),
        ("QLs", "NL"),
    ):
        account_component = re.sub(rf"\b{re.escape(old)}\b", new, account_component)
    # Native menu icons moved from components to assets in this build.
    if account_component.count("LeftIcon: S2,") != 2:
        raise RuntimeError("build 8881 usage icon: expected two upstream menu rows")
    account_component = account_component.replace("LeftIcon: S2,", "leftIconAsset: eZe,")
    for old, new, label in (
        ("const modalScope = Lo(Q);", "const modalScope = Of(o_);", "modal scope"),
        (
            "const resolvedImageUrl = jLa(imageUrl || null);",
            "const resolvedImageUrl = $N(imageUrl || null);",
            "profile image resolver",
        ),
        ("const queryClient = lt();", "const queryClient = rf();", "query client"),
        (
            "navigator.clipboard.writeText(userCode)",
            "globalThis.__codexMuxCopyText(userCode)",
            "native sign-in clipboard",
        ),
    ):
        account_component = _replace_once(account_component, old, new, label)

    # Native self-updates are disabled in this independently patched app.
    # State who manages updates without inventing a check or download result.
    account_component = _replace_once(
        account_component,
        '  rows.push((0, Gz.jsx)(tS.Separator, {}, "codex-mux-separator"));',
        '  rows.push((0, Gz.jsx)(kg, { variant: "label", children: "Router-managed updates" }, "codex-mux-updates"));\n'
        '  rows.push((0, Gz.jsx)(tS.Separator, {}, "codex-mux-separator"));',
        "router update status",
    )

    # These exports are also used by lazy native screens before the profile
    # menu renders. Initialize its native module bindings on first use.
    for old, new in (
        (
            "globalThis.CodexMuxAccountAvatar = CodexMuxAccountAvatar;",
            "globalThis.CodexMuxAccountAvatar = (props) => { xGt(); return (0,Gz.jsx)(CodexMuxAccountAvatar,props); };",
        ),
        (
            "globalThis.CodexMuxProfileAvatarStack = (props) =>\n  (0, Gz.jsx)(CodexMuxProfileAvatarStack, props || {});",
            "globalThis.CodexMuxProfileAvatarStack = (props) => { xGt(); return (0,Gz.jsx)(CodexMuxProfileAvatarStack,props || {}); };",
        ),
        (
            "globalThis.CodexMuxPluginScope = () =>\n  (0, Gz.jsx)(CodexMuxPluginScope, {});",
            "globalThis.CodexMuxPluginScope = () => { xGt(); return (0,Gz.jsx)(CodexMuxPluginScope,{}); };",
        ),
    ):
        account_component = _replace_once(account_component, old, new, "shared native bindings")

    # The native host clipboard remains usable after Continue opens the browser.
    # Closures defer reading host services until app initialization has finished.
    account_component += """
globalThis.__codexMuxCopyText = (text) => jf.clipboard.writeText(text);
globalThis.CodexMuxUseResetAccountState = () => { xGt(); return CodexMuxUseResetAccountState(); };
globalThis.codexMuxRateLimitResets = codexMuxRateLimitResets;
globalThis.codexMuxConsumeRateLimitReset = codexMuxConsumeRateLimitReset;
globalThis.codexMuxScopePluginRequest = codexMuxScopePluginRequest;
"""
    primary = _replace_once(
        primary, "function fGt(e){", account_component + "\nfunction fGt(e){", "profile component"
    )
    for old, new, label in (
        (
            "align:`start`,contentStyle:v,open:s,side:`top`,sideOffset:6,triggerButton:Nt",
            "align:`start`,contentStyle:{...v,width:`380px`,maxWidth:`calc(100vw - 24px)`,minWidth:0,overflowX:`hidden`},open:s,side:`top`,sideOffset:6,triggerButton:Nt",
            "sidebar popup width",
        ),
        (
            "usageItems:kt})",
            "usageItems:(0,Gz.jsx)(CodexMuxAccountMenu,{})})",
            "sidebar account menu",
        ),
        (
            "triggerButton:Nt,onOpenChange:c,children:[j,null]",
            "triggerButton:Nt,onOpenChange:CodexMuxProfileMenuOpenChange(c),children:[j,null]",
            "sidebar sign-in dismissal",
        ),
        (
            "children:[wt,Pt,zt,null,Bt,null,Vt,Ut,kt,Wt]",
            "children:[wt,Pt,zt,null,Bt,null,Vt,Ut,(0,Gz.jsx)(CodexMuxAccountMenu,{}),Wt]",
            "compact account menu",
        ),
        (
            "open:s,onOpenChange:c,contentWidth:`panel`,triggerButton:Nt,children:Gt",
            "open:s,onOpenChange:CodexMuxProfileMenuOpenChange(c),contentWidth:`panel`,contentStyle:{width:`380px`,maxWidth:`calc(100vw - 24px)`,minWidth:0,overflowX:`hidden`},triggerButton:Nt,children:Gt",
            "compact sign-in dismissal",
        ),
    ):
        primary = _replace_once(primary, old, new, label)

    thread_component = _component("thread-subscription.js", token, port)
    thread_component = re.sub(r"\bzE\b", "oO", thread_component)
    thread_component = re.sub(r"\bTE\b", "CodexMuxThreadReact", thread_component)
    thread_component = _replace_once(thread_component, "$n(sr)", "vi(S)", "task route")
    thread_component = _replace_once(thread_component, "K.Section", "Z.Section", "task section")
    # r() is the shared React module import in this lazy-loaded native bundle.
    thread_component = "const CodexMuxThreadReact=t(r(),1);\n" + thread_component
    thread = _replace_once(
        thread, "function rO(){", thread_component + "\nfunction rO(){", "task summary component"
    )
    thread = _replace_once(
        thread,
        "children:[T,p,E,D,w,O]",
        "children:[T,p,(0,oO.jsx)(CodexMuxThreadSubscription,{}),E,D,w,O]",
        "task summary section list",
    )
    index = _replace_once(
        index,
        "connect-src &#39;self&#39;",
        f"connect-src &#39;self&#39; http://127.0.0.1:{port}",
        "renderer control API CSP",
    )

    # Validate every source anchor before writing any bundle.
    primary_path.write_text(primary, encoding="utf-8")
    thread_path.write_text(thread, encoding="utf-8")
    index_path.write_text(index, encoding="utf-8")
