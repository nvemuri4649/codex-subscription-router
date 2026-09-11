"""Port the upstream Subscription Router renderer to official build 8576.

Keep the upstream components in ui/ as the design and behavior source. Only
their native module bindings and the reviewed insertion points differ here.
"""

from pathlib import Path
import json
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRIMARY_BUNDLE = "app-primary-defe25a79fce.js"
THREAD_BUNDLE = "local-conversation-thread-9210b06f69b1.js"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"build 8576 {label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)


def _component(name: str, token: str, port: int) -> str:
    source = (PROJECT_ROOT / "ui" / name).read_text(encoding="utf-8")
    source = source.replace("__CODEX_MUX_CONTROL_PORT__", str(port))
    return source.replace('"__CODEX_MUX_CONTROL_TOKEN__"', json.dumps(token))


def patch_renderer_8576(extracted: Path, token: str, port: int) -> None:
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
        ("e7", "xK"),
        ("kXc", "Obn"),
        ("_H", "Zy"),
        ("CH", "Rd"),
        ("BW", "Hv"),
        ("QLs", "tfn"),
        ("S2", "iG"),
    ):
        account_component = re.sub(rf"\b{re.escape(old)}\b", new, account_component)
    for old, new, label in (
        ("const modalScope = Lo(Q);", "const modalScope = Oe(zb);", "modal scope"),
        (
            "const resolvedImageUrl = jLa(imageUrl || null);",
            "const resolvedImageUrl = Qz(imageUrl || null);",
            "profile image resolver",
        ),
        ("const queryClient = lt();", "const queryClient = Ai();", "query client"),
        (
            "navigator.clipboard.writeText(userCode)",
            "globalThis.__codexMuxCopyText(userCode)",
            "native sign-in clipboard",
        ),
    ):
        account_component = _replace_once(account_component, old, new, label)

    # These exports are also used by lazy native screens before the profile
    # menu renders. Initialize its native module bindings on first use.
    for old, new in (
        (
            "globalThis.CodexMuxAccountAvatar = CodexMuxAccountAvatar;",
            "globalThis.CodexMuxAccountAvatar = (props) => { Abn(); return (0,xK.jsx)(CodexMuxAccountAvatar,props); };",
        ),
        (
            "globalThis.CodexMuxProfileAvatarStack = (props) =>\n  (0, xK.jsx)(CodexMuxProfileAvatarStack, props || {});",
            "globalThis.CodexMuxProfileAvatarStack = (props) => { Abn(); return (0,xK.jsx)(CodexMuxProfileAvatarStack,props || {}); };",
        ),
        (
            "globalThis.CodexMuxPluginScope = () =>\n  (0, xK.jsx)(CodexMuxPluginScope, {});",
            "globalThis.CodexMuxPluginScope = () => { Abn(); return (0,xK.jsx)(CodexMuxPluginScope,{}); };",
        ),
    ):
        account_component = _replace_once(account_component, old, new, "shared native bindings")

    # The native host clipboard remains usable after Continue opens the browser.
    # Closures defer reading host services until app initialization has finished.
    account_component += """
globalThis.__codexMuxCopyText = (text) => Dw.clipboard.writeText(text);
globalThis.CodexMuxUseResetAccountState = () => { Abn(); return CodexMuxUseResetAccountState(); };
globalThis.codexMuxRateLimitResets = codexMuxRateLimitResets;
globalThis.codexMuxConsumeRateLimitReset = codexMuxConsumeRateLimitReset;
globalThis.codexMuxScopePluginRequest = codexMuxScopePluginRequest;
"""
    primary = _replace_once(
        primary, "function Sbn(e){", account_component + "\nfunction Sbn(e){", "profile component"
    )
    for old, new, label in (
        (
            "align:`start`,contentStyle:y,open:s,side:`top`,sideOffset:6,triggerButton:Ot",
            "align:`start`,contentStyle:{...y,width:`380px`,maxWidth:`calc(100vw - 24px)`,minWidth:0,overflowX:`hidden`},open:s,side:`top`,sideOffset:6,triggerButton:Ot",
            "sidebar popup width",
        ),
        (
            "usageItems:wt,workspaceSettingsRightIcon:P",
            "usageItems:(0,xK.jsx)(CodexMuxAccountMenu,{}),workspaceSettingsRightIcon:P",
            "sidebar account menu",
        ),
        (
            "triggerButton:Ot,onOpenChange:c,children:[F,null]",
            "triggerButton:Ot,onOpenChange:CodexMuxProfileMenuOpenChange(c),children:[F,null]",
            "sidebar sign-in dismissal",
        ),
        (
            "children:[bt,kt,Nt,null,Pt,null,Ft,Lt,wt,Rt]",
            "children:[bt,kt,Nt,null,Pt,null,Ft,Lt,(0,xK.jsx)(CodexMuxAccountMenu,{}),Rt]",
            "compact account menu",
        ),
        (
            "open:s,onOpenChange:c,contentWidth:`panel`,triggerButton:Ot,children:zt",
            "open:s,onOpenChange:CodexMuxProfileMenuOpenChange(c),contentWidth:`panel`,contentStyle:{width:`380px`,maxWidth:`calc(100vw - 24px)`,minWidth:0,overflowX:`hidden`},triggerButton:Ot,children:zt",
            "compact sign-in dismissal",
        ),
    ):
        primary = _replace_once(primary, old, new, label)

    thread_component = _component("thread-subscription.js", token, port)
    thread_component = re.sub(r"\bzE\b", "cE", thread_component)
    thread_component = re.sub(r"\bTE\b", "CodexMuxThreadReact", thread_component)
    thread_component = _replace_once(thread_component, "$n(sr)", "s(ps)", "task route")
    thread_component = _replace_once(thread_component, "K.Section", "Z.Section", "task section")
    # y() is the shared React module import in this lazy-loaded native bundle.
    thread_component = "const CodexMuxThreadReact=t(y(),1);\n" + thread_component
    thread = _replace_once(
        thread, "function aE(){", thread_component + "\nfunction aE(){", "task summary component"
    )
    thread = _replace_once(
        thread,
        "children:[T,m,E,D,w,O]",
        "children:[T,m,(0,cE.jsx)(CodexMuxThreadSubscription,{}),E,D,w,O]",
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
