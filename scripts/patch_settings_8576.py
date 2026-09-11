"""Port the upstream profile, Plugins, and Usage patches to desktop build 8576.

The original components are injected by patch_renderer_8576.  These reviewed
anchors connect them to the current split renderer bundles; unsupported bundle
changes fail before any settings bundle is written.
"""

from pathlib import Path


def _replace(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"could not verify build 8576 {label}")
    return source.replace(old, new, 1)


def patch_settings_8576(extracted: Path, token: str, port: int) -> None:
    # The shared account component owns the control URL and token. Lazy bundles
    # use its exports, so there is only one authenticated control API client.
    assets = extracted / "webview" / "assets"
    paths = {
        "initial": assets / "app-initial-a9514281e192.js",
        "primary": assets / "app-primary-defe25a79fce.js",
        "profile": assets / "profile-ee018db6e64a.js",
        "plugins": assets / "plugins-settings-7783b7611c76.js",
    }
    source = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
    initial = source["initial"]

    # The current manager receives app-server method names rather than the old
    # renderer message names used by the upstream scoping helper. Remote hosts
    # retain their native account: this router controls local subscriptions.
    plugin_method = (
        '({"app/list":"list-apps","app/installed":"list-installed-apps",'
        '"app/read":"read-apps","mcpServerStatus/list":"list-mcp-server-status",'
        '"mcpServer/oauth/login":"login-mcp-server"})[e]??e'
    )
    initial = _replace(
        initial,
        "async sendRequest(e,t,n){return this.assertActive(),this.requestClient.sendRequest(e,t,n)}",
        "async sendRequest(e,t,n){return this.assertActive(),"
        "this.requestClient.sendRequest(e,this.hostId===`local`?"
        f"(globalThis.codexMuxScopePluginRequest?.({plugin_method},t)??t):t,n)}}",
        "Plugins request bridge",
    )
    # Scope before the native in-flight cache key is computed as well, so a
    # request for one subscription cannot reuse another subscription's result.
    initial = _replace(
        initial,
        "listMcpServers(e,t){let n=JSON.stringify({options:t,params:e})",
        "listMcpServers(e,t){e=this.hostId===`local`?"
        "(globalThis.codexMuxScopePluginRequest?.(`list-mcp-server-status`,e)??e):e;"
        "let n=JSON.stringify({options:t,params:e})",
        "MCP account cache key",
    )
    initial = _replace(
        initial,
        "let e=await _O.safeGet(`/wham/profiles/me`)",
        "let e=await globalThis.codexMuxProfileData("
        "globalThis.__codexMuxSelectedProfileAccountId??null)",
        "profile stats request",
    )
    initial = _replace(
        initial,
        "function j5i(){let e=(0,lq.c)(1);dz(),ob(null);let t;return "
        "e[0]===Symbol.for(`react.memo_cache_sentinel`)?"
        "(t={queryKey:[`rate-limit-reset-credits`],queryFn:N5i,select:M5i,"
        "refetchInterval:tD.ONE_MINUTE,staleTime:tD.FIVE_SECONDS},e[0]=t):t=e[0],hb(t)}",
        "function j5i(){dz(),ob(null);let e=window.__codexMuxResetAccountId;return hb({"
        "queryKey:[`rate-limit-reset-credits`,e??`primary`],"
        "queryFn:e?()=>globalThis.codexMuxRateLimitResets(e):N5i,select:M5i,"
        "refetchInterval:tD.ONE_MINUTE,staleTime:tD.FIVE_SECONDS})}",
        "reset-credit query",
    )
    initial = _replace(
        initial,
        "function P5i(){let e=(0,lq.c)(3),t=db(),n=$E(),r;return "
        "e[0]!==n||e[1]!==t?(r={mutationFn:F5i,onSuccess:(e,r)=>{"
        "let{creditId:i}=r,a=e.code;if(a===`reset`||a===`already_redeemed`){"
        "let n=e.code===`reset`?e.credit?.id??i:i;"
        "t.setQueryData([`rate-limit-reset-credits`],e=>_8i(e,a,n))}"
        "Promise.all([n([`rate-limit-status`]),n([`rate-limit-reset-credits`])])}},"
        "e[0]=n,e[1]=t,e[2]=r):r=e[2],vb(r)}",
        "function P5i(){let e=db(),t=$E(),n=window.__codexMuxResetAccountId,"
        "r=[`rate-limit-reset-credits`,n??`primary`];return vb({"
        "mutationFn:n?i=>globalThis.codexMuxConsumeRateLimitReset(n,i):F5i,"
        "onSuccess:(n,i)=>{let{creditId:a}=i,o=n.code;"
        "if(o===`reset`||o===`already_redeemed`){let t=o===`reset`?"
        "n.credit?.id??a:a;e.setQueryData(r,e=>_8i(e,o,t))}"
        "Promise.all([t([`rate-limit-status`]),t(r)])}})}",
        "reset-credit mutation",
    )
    # The old profile's avatar/name wrappers moved into a shared header in this
    # build. Hide empty wrappers only for the combined-profile call below.
    initial = _replace(
        initial,
        "c=(0,tJ.jsx)(`div`,{className:`relative mb-4 size-20`,children:r})",
        "c=(0,tJ.jsx)(`div`,{className:e.codexMuxProfile&&r==null?"
        "`hidden`:`relative mb-4 size-20`,children:r})",
        "profile avatar wrapper",
    )
    initial = _replace(
        initial,
        "l=(0,tJ.jsx)(`div`,{className:`flex w-full justify-center`,"
        "children:(0,tJ.jsx)(`h1`,",
        "l=(0,tJ.jsx)(`div`,{className:e.codexMuxProfile&&i==null?"
        "`hidden`:`flex w-full justify-center`,children:(0,tJ.jsx)(`h1`,",
        "profile name wrapper",
    )

    primary = _replace(
        source["primary"],
        "function tfn(e){",
        "function tfn(e){globalThis.CodexMuxUseResetAccountState();",
        "Usage modal hook",
    )
    primary = _replace(
        primary,
        "let v=_,y;return t[13]!==n||t[14]!==d||t[15]!==g||t[16]!==v||"
        "t[17]!==r||t[18]!==m?(y=(0,ifn.jsx)(qdn,{defaultResetCreditsOpen:n,"
        "errorMessage:d,initialAvailableCount:r,isResetting:m,onClose:g,onResetCredit:v}),"
        "t[13]=n,t[14]=d,t[15]=g,t[16]=v,t[17]=r,t[18]=m,t[19]=y):y=t[19],y}",
        "let v=_;return(0,ifn.jsx)(qdn,{defaultResetCreditsOpen:n,errorMessage:d,"
        "initialAvailableCount:r,isResetting:m,onClose:g,onResetCredit:v})}",
        "Usage subscription render propagation",
    )
    primary = _replace(
        primary,
        "let y=v;if(g!=null){",
        "let y=window.__codexMuxSelectedUsageWindows??v;if(g!=null){",
        "selected usage windows",
    )
    primary = _replace(
        primary,
        "let ge;t[46]===me?ge=t[47]:"
        "(ge=(0,VW.jsxs)(bb,{children:[me,he]}),t[46]=me,t[47]=ge);",
        "let ge=(0,VW.jsxs)(bb,{children:[me,he,"
        "window.__codexMuxResetAccountSelector??null]});",
        "Usage sheet subscription selector",
    )
    # Keep native mixed Codex/Work depletion copy: cloud Work is billed to the
    # controller and can be depleted while another coding subscription is free.

    profile = source["profile"]
    # The new native profile uses a header component instead of the former
    # inline avatar/name DOM. Keep the upstream stack outside that header so it
    # can show all avatars, and show native identity only for a selected account.
    # Drop just this compiler memo: its dependency list cannot observe the
    # selected-account global or the query's fetching state.
    profile = _replace(
        profile,
        "let yt=K||void 0,bt;t[79]!==Je||t[80]!==He||t[81]!==c||t[82]!==Ae||"
        "t[83]!==K||t[84]!==je||t[85]!==i||t[86]!==H||t[87]!==Me||"
        "t[88]!==V||t[89]!==Ve?(bt=K?",
        "let codexMuxProfilePlan=globalThis.__codexMuxCombinedProfileAccounts?.find(e=>"
        "e.id===globalThis.__codexMuxSelectedProfileAccountId)?.planLabel??null;"
        "let yt=K||void 0,bt=K?",
        "profile header memo start",
    )
    profile = _replace(
        profile,
        "}),t[79]=Je,t[80]=He,t[81]=c,t[82]=Ae,t[83]=K,t[84]=je,"
        "t[85]=i,t[86]=H,t[87]=Me,t[88]=V,t[89]=Ve,t[90]=bt):bt=t[90];",
        "});",
        "profile header memo end",
    )
    profile = _replace(
        profile,
        "(0,$.jsx)(O,{account:Je==null?null:",
        "(0,$.jsx)(O,{codexMuxProfile:!0,account:Je==null?null:",
        "combined profile header",
    )
    profile = _replace(
        profile,
        "account:Je==null?null:(0,$.jsx)(ua,{accountLabel:Je}),"
        "avatar:(0,$.jsxs)($.Fragment,{children:[",
        "account:globalThis.__codexMuxSelectedProfileAccountId&&!N.isFetching&&codexMuxProfilePlan?"
        "(0,$.jsx)(ua,{accountLabel:codexMuxProfilePlan}):null,"
        "avatar:globalThis.CodexMuxProfileAvatarStack?null:(0,$.jsxs)($.Fragment,{children:[",
        "profile native avatar and identity",
    )
    profile = _replace(
        profile,
        "displayName:He??(0,$.jsx)(h,{id:`profile.nameFallback`,"
        "defaultMessage:`ChatGPT user`,description:`Fallback profile display name`}),"
        "username:Ve==null?null:",
        "displayName:globalThis.__codexMuxSelectedProfileAccountId&&!N.isFetching?"
        "He??(0,$.jsx)(h,{id:`profile.nameFallback`,defaultMessage:`ChatGPT user`,"
        "description:`Fallback profile display name`}):null,"
        "username:!globalThis.__codexMuxSelectedProfileAccountId||N.isFetching||Ve==null?null:",
        "profile name and username",
    )
    profile = _replace(
        profile,
        "let xt;t[91]!==yt||t[92]!==bt?(xt=(0,$.jsx)(`section`,"
        '{"aria-busy":yt,className:`flex flex-col items-center`,children:bt}),'
        "t[91]=yt,t[92]=bt,t[93]=xt):xt=t[93];",
        "let xt=(0,$.jsxs)(`section`,{\"aria-busy\":yt,"
        "className:`flex flex-col items-center`,children:["
        "globalThis.CodexMuxProfileAvatarStack?.({onSelect:()=>N.refetch()})??null,bt]});",
        "combined profile avatar stack",
    )
    # Current native profile editing always changes the controller account. The
    # selected subscription's stats must never imply that it changes another.
    profile = _replace(
        profile,
        "let vt;t[76]!==ct||t[77]!==_t?",
        "_t=globalThis.__codexMuxCombinedProfileAccounts?.some(e=>"
        "e.id===globalThis.__codexMuxSelectedProfileAccountId&&e.controller===!0)?_t:null;"
        "let vt;t[76]!==ct||t[77]!==_t?",
        "controller profile edit control",
    )

    plugins = _replace(
        source["plugins"],
        "action:F,children:w})",
        "action:F,children:[f===`local`?"
        "(globalThis.CodexMuxPluginScope?.()??null):null,w]})",
        "Plugins subscription scope",
    )
    result = {"initial": initial, "primary": primary, "profile": profile, "plugins": plugins}
    for name, content in result.items():
        paths[name].write_text(content, encoding="utf-8")
