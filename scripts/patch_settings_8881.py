"""Port the upstream profile, Plugins, and Usage patches to desktop build 8881.

The original components are injected by patch_renderer_8881.  These reviewed
anchors connect them to the current split renderer bundles; unsupported bundle
changes fail before any settings bundle is written.
"""

from pathlib import Path


def _replace(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"could not verify build 8881 {label}")
    return source.replace(old, new, 1)


def patch_settings_8881(extracted: Path, token: str, port: int) -> None:
    # The shared account component owns the control URL and token. Lazy bundles
    # use its exports, so there is only one authenticated control API client.
    assets = extracted / "webview" / "assets"
    paths = {
        "initial": assets / "app-initial-9b95fa538c62.js",
        "primary": assets / "app-primary-44ec287874b7.js",
        "profile": assets / "profile-9e1aa6f4c439.js",
        "plugins": assets / "plugins-settings-35478bddfc40.js",
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
        "let e=await DS.safeGet(`/wham/profiles/me`)",
        "let e=await globalThis.codexMuxProfileData("
        "globalThis.__codexMuxSelectedProfileAccountId??null)",
        "profile stats request",
    )
    initial = _replace(
        initial,
        "function iji(){let e=(0,cG.c)(1);KD(),fm(null);let t;return "
        "e[0]===Symbol.for(`react.memo_cache_sentinel`)?"
        "(t={queryKey:[`rate-limit-reset-credits`],queryFn:oji,select:aji,"
        "refetchInterval:Qx.ONE_MINUTE,staleTime:Qx.FIVE_SECONDS},e[0]=t):t=e[0],xm(t)}",
        "function iji(){KD(),fm(null);let e=window.__codexMuxResetAccountId;return xm({"
        "queryKey:[`rate-limit-reset-credits`,e??`primary`],"
        "queryFn:e?()=>globalThis.codexMuxRateLimitResets(e):oji,select:aji,"
        "refetchInterval:Qx.ONE_MINUTE,staleTime:Qx.FIVE_SECONDS})}",
        "reset-credit query",
    )
    initial = _replace(
        initial,
        "function sji(){let e=(0,cG.c)(3),t=_m(),n=Xx(),r;return "
        "e[0]!==n||e[1]!==t?(r={mutationFn:cji,onSuccess:(e,r)=>{"
        "let{creditId:i}=r,a=e.code;if(a===`reset`||a===`already_redeemed`){"
        "let n=e.code===`reset`?e.credit?.id??i:i;"
        "t.setQueryData([`rate-limit-reset-credits`],e=>Wki(e,a,n))}"
        "Promise.all([n([`rate-limit-status`]),n([`rate-limit-reset-credits`])])}},"
        "e[0]=n,e[1]=t,e[2]=r):r=e[2],wm(r)}",
        "function sji(){let e=_m(),t=Xx(),n=window.__codexMuxResetAccountId,"
        "r=[`rate-limit-reset-credits`,n??`primary`];return wm({"
        "mutationFn:n?i=>globalThis.codexMuxConsumeRateLimitReset(n,i):cji,"
        "onSuccess:(n,i)=>{let{creditId:a}=i,o=n.code;"
        "if(o===`reset`||o===`already_redeemed`){let t=o===`reset`?"
        "n.credit?.id??a:a;e.setQueryData(r,e=>Wki(e,o,t))}"
        "Promise.all([t([`rate-limit-status`]),t(r)])}})}",
        "reset-credit mutation",
    )
    # The old profile's avatar/name wrappers moved into a shared header in this
    # build. Hide empty wrappers only for the combined-profile call below.
    initial = _replace(
        initial,
        "c=(0,$G.jsx)(`div`,{className:`relative mb-4`,children:r})",
        "c=(0,$G.jsx)(`div`,{className:e.codexMuxProfile&&r==null?"
        "`hidden`:`relative mb-4`,children:r})",
        "profile avatar wrapper",
    )
    initial = _replace(
        initial,
        "l=(0,$G.jsx)(`div`,{className:`flex w-full justify-center`,"
        "children:(0,$G.jsx)(`h1`,",
        "l=(0,$G.jsx)(`div`,{className:e.codexMuxProfile&&i==null?"
        "`hidden`:`flex w-full justify-center`,children:(0,$G.jsx)(`h1`,",
        "profile name wrapper",
    )

    primary = _replace(
        source["primary"],
        "function NL(e){",
        "function NL(e){globalThis.CodexMuxUseResetAccountState();",
        "Usage modal hook",
    )
    primary = _replace(
        primary,
        "let v=_,y;return t[13]!==n||t[14]!==d||t[15]!==g||t[16]!==v||"
        "t[17]!==r||t[18]!==m?(y=(0,yIt.jsx)(lIt,{defaultResetCreditsOpen:n,"
        "errorMessage:d,initialAvailableCount:r,isResetting:m,onClose:g,onResetCredit:v}),"
        "t[13]=n,t[14]=d,t[15]=g,t[16]=v,t[17]=r,t[18]=m,t[19]=y):y=t[19],y}",
        "let v=_;return(0,yIt.jsx)(lIt,{defaultResetCreditsOpen:n,errorMessage:d,"
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
        'let ge;t[41]===Symbol.for(`react.memo_cache_sentinel`)?(ge=(0,ML.jsx)(dC,{children:(0,ML.jsx)(Sh,{title:(0,ML.jsx)(MC,{asChild:!0,children:(0,ML.jsx)(`h2`,{className:`m-0`,children:(0,ML.jsx)(Z,{id:`codex.rateLimitResetPromptModal.usageTrackingHeading`,defaultMessage:`Usage`,description:`Heading for the Codex usage limit modal`})})})})}),t[41]=ge):ge=t[41];',
        'let ge=(0,ML.jsxs)(dC,{children:[(0,ML.jsx)(Sh,{title:(0,ML.jsx)(MC,{asChild:!0,children:(0,ML.jsx)(`h2`,{className:`m-0`,children:(0,ML.jsx)(Z,{id:`codex.rateLimitResetPromptModal.usageTrackingHeading`,defaultMessage:`Usage`,description:`Heading for the Codex usage limit modal`})})})}),window.__codexMuxResetAccountSelector??null]});',
        "Usage sheet subscription selector",
    )
    primary = _replace(
        primary,
        'let Te;t[77]!==he||t[78]!==Se||t[79]!==Ce||t[80]!==we?(Te=(0,ML.jsxs)(Fv,{className:`overflow-y-auto text-default`,style:he,children:[ge,Se,Ce,we]}),t[77]=he,t[78]=Se,t[79]=Ce,t[80]=we,t[81]=Te):Te=t[81];',
        'let Te=(0,ML.jsxs)(Fv,{className:`overflow-y-auto text-default`,style:he,children:[ge,Se,Ce,we]});',
        "Usage selector render propagation",
    )
    # Keep native mixed Codex/Work depletion copy: cloud Work is billed to the
    # controller and can be depleted while another coding subscription is free.

    profile = source["profile"]
    profile = _replace(
        profile,
        "function _c(e){let t=(0,Vc.c)(215)",
        "function _c(e){let codexMuxProfileAccount="
        "globalThis.__codexMuxCombinedProfileAccounts?.find(e=>"
        "e.id===globalThis.__codexMuxSelectedProfileAccountId),"
        "codexMuxProfileController=codexMuxProfileAccount?.controller===!0,"
        "codexMuxProfilePlan=codexMuxProfileAccount?.planLabel??null;"
        "let t=(0,Vc.c)(215)",
        "selected profile account",
    )
    # Native compiler dependencies cannot observe the subscription global or
    # the profile query's fetching state. Recompute only the affected header.
    profile = _replace(
        profile,
        "let ln=q||void 0,un;t[107]!==Ft||t[108]!==Ot||t[109]!==p||t[110]!==ut||"
        "t[111]!==tt||t[112]!==q||t[113]!==r||t[114]!==He.petId||t[115]!==$e||"
        "t[116]!==gt||t[117]!==Qe||t[118]!==l||t[119]!==xe||t[120]!==K||"
        "t[121]!==Me||t[122]!==ft||t[123]!==vt||t[124]!==Et?(un=q?",
        "let ln=q||void 0,un=q?",
        "profile header memo start",
    )
    profile = _replace(
        profile,
        "}),t[107]=Ft,t[108]=Ot,t[109]=p,t[110]=ut,t[111]=tt,t[112]=q,t[113]=r,"
        "t[114]=He.petId,t[115]=$e,t[116]=gt,t[117]=Qe,t[118]=l,t[119]=xe,t[120]=K,"
        "t[121]=Me,t[122]=ft,t[123]=vt,t[124]=Et,t[125]=un):un=t[125];",
        "});",
        "profile header memo end",
    )
    profile = _replace(
        profile,
        "(0,$.jsx)($t,{account:Ft==null?null:(0,$.jsx)(Sc,{accountLabel:Ft}),"
        "avatar:(0,$.jsxs)($.Fragment,{children:[",
        "(0,$.jsx)($t,{codexMuxProfile:!0,account:"
        "globalThis.__codexMuxSelectedProfileAccountId&&!W.isFetching&&codexMuxProfilePlan?"
        "(0,$.jsx)(Sc,{accountLabel:codexMuxProfilePlan}):null,"
        "avatar:globalThis.CodexMuxProfileAvatarStack?null:(0,$.jsxs)($.Fragment,{children:[",
        "profile native avatar and selected plan",
    )
    profile = _replace(
        profile,
        "displayName:Ot??(0,$.jsx)(J,{id:`profile.nameFallback`,"
        "defaultMessage:`ChatGPT user`,description:`Fallback profile display name`}),"
        "username:Et==null?null:",
        "displayName:globalThis.__codexMuxSelectedProfileAccountId&&!W.isFetching?"
        "Ot??(0,$.jsx)(J,{id:`profile.nameFallback`,defaultMessage:`ChatGPT user`,"
        "description:`Fallback profile display name`}):null,"
        "username:!globalThis.__codexMuxSelectedProfileAccountId||W.isFetching||Et==null?null:",
        "profile name and username",
    )
    profile = _replace(
        profile,
        "let dn;t[126]!==ln||t[127]!==un?(dn=(0,$.jsx)(`section`,"
        '{"aria-busy":ln,className:`flex flex-col items-center`,children:un}),'
        "t[126]=ln,t[127]=un,t[128]=dn):dn=t[128];",
        "let dn=(0,$.jsxs)(`section`,{\"aria-busy\":ln,"
        "className:`flex flex-col items-center`,children:["
        "globalThis.CodexMuxProfileAvatarStack?.({onSelect:()=>{Fe(null);W.refetch()}})??null,un]});",
        "combined profile avatar stack",
    )
    profile = _replace(
        profile,
        "let nn;t[102]!==Kt||t[103]!==tn?",
        "tn=codexMuxProfileController?tn:null;let nn;t[102]!==Kt||t[103]!==tn?",
        "controller profile edit control",
    )
    # Profile V2 adds a locally stored bio and a cloud showcase for the desktop
    # controller. Neither belongs to an aggregate or another selected account.
    profile = _replace(
        profile,
        "kt=Ie?.bio??se,At=k?.structure",
        "kt=codexMuxProfileController?Ie?.bio??se:``,At=k?.structure",
        "controller profile bio",
    )
    profile = _replace(
        profile,
        "showcase:(0,$.jsx)(ec,{accountId:V,userId:H,projects:T,isLoading:E,isError:D},JSON.stringify([H,V])),",
        "showcase:codexMuxProfileController?(0,$.jsx)(ec,"
        "{accountId:V,userId:H,projects:T,isLoading:E,isError:D},JSON.stringify([H,V])):null,",
        "controller profile showcase",
    )
    profile = _replace(
        profile,
        "let mn;t[133]!==Te||t[134]!==Rt||t[135]!==Be.showActivityGraph||"
        "t[136]!==Be.showUsageStatistics||t[137]!==p||t[138]!==O||t[139]!==q||"
        "t[140]!==ct||t[141]!==r||t[142]!==D||t[143]!==E||t[144]!==Lt||t[145]!==V||"
        "t[146]!==H||t[147]!==Ee||t[148]!==T||t[149]!==L||t[150]!==R||t[151]!==te||"
        "t[152]!==It||t[153]!==Oe?(mn=r",
        "let mn=r",
        "profile showcase memo start",
    )
    profile = _replace(
        profile,
        "]}),t[133]=Te,t[134]=Rt,t[135]=Be.showActivityGraph,t[136]=Be.showUsageStatistics,"
        "t[137]=p,t[138]=O,t[139]=q,t[140]=ct,t[141]=r,t[142]=D,t[143]=E,t[144]=Lt,"
        "t[145]=V,t[146]=H,t[147]=Ee,t[148]=T,t[149]=L,t[150]=R,t[151]=te,t[152]=It,"
        "t[153]=Oe,t[154]=mn):mn=t[154];",
        "]});",
        "profile showcase memo end",
    )
    plugins = _replace(
        source["plugins"],
        "action:F,children:w})",
        "action:F,children:[l===`local`?"
        "(globalThis.CodexMuxPluginScope?.()??null):null,w]})",
        "Plugins subscription scope",
    )
    result = {"initial": initial, "primary": primary, "profile": profile, "plugins": plugins}
    for name, content in result.items():
        paths[name].write_text(content, encoding="utf-8")
