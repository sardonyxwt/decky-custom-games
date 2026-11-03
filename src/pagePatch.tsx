import { afterPatch, findInReactTree } from "@decky/ui";
import { routerHook } from "@decky/api";
import { cloneElement, ReactNode } from "react";
import { gameFor, usePluginState } from "./state";
import { isShortcut } from "./steam";
import { ActivityTab, CommunityTab, GameInfoTab, TabProps, YourStuffTab } from "./tabs";

const ROUTE = "/library/app/:appid";

// Steam's tab ids on the game page (stable across client updates so far; titles are localization tokens).
const TABS: Record<string, (p: TabProps) => any> = {
  WhatsNew: ActivityTab,
  YourStuff: YourStuffTab,
  Community: CommunityTab,
  GameInfo: GameInfoTab,
};

/** Shows our content when the shortcut is linked to a Steam game, else Steam's own (empty) tab. */
function TabHost({ appid, tab, native }: { appid: number; tab: string; native: ReactNode }) {
  usePluginState(); // re-render when the link to a Steam game changes
  const game = gameFor(appid);
  const Comp = TABS[tab];
  if (!game || !Comp) return <>{native}</>;
  return <Comp appid={appid} game={game} native={tab === "GameInfo" ? null : native} />;
}

function patchTabs(props: any, ret: any) {
  try {
    const appid: number = (props?.details?.unAppID ?? props?.overview?.appid) >>> 0;
    const tabs = ret?.props?.tabs;
    if (!isShortcut(appid) || !Array.isArray(tabs)) return ret;
    ret.props.tabs = tabs.map((t: any) => {
      if (!TABS[t?.id] || !t.content?.props || t.content.props.children?.type === TabHost) return t;
      const native = t.content.props.children;
      return {
        ...t,
        content: cloneElement(t.content, undefined, <TabHost key={`cg-${t.id}`} appid={appid} tab={t.id} native={native} />),
      };
    });
  } catch (e) {
    console.error("[Custom Games] tab patch failed", e);
  }
  return ret;
}

// One wrapper per original component, so React sees a stable type and never remounts the page.
const wrappers = new WeakMap<Function, Function>();

function wrap(orig: Function, after: (props: any, ret: any) => any): Function {
  let w = wrappers.get(orig);
  if (!w) {
    w = function (this: any, props: any, ...rest: any[]) {
      return after(props, orig.call(this, props, ...rest));
    };
    Object.assign(w, orig);
    wrappers.set(orig, w);
    wrappers.set(w, w);
  }
  return w;
}

/**
 * The route renders `<Provider value={TabSection}><AppPage overview details/></Provider>`: the app page (a MobX
 * observer class, so patching its render does not stick) takes the tab section component from that context.
 * We swap the context value for a wrapper of the section, which in turn wraps the component that builds the
 * tabs array (found by its props, not by minified names) and replaces the contents of the four tabs.
 * If Steam changes this shape, nothing matches and the page stays exactly as Steam draws it.
 */
export function patchLibraryApp() {
  return routerHook.addPatch(ROUTE, (tree: any) => {
    try {
      const routeProps = findInReactTree(tree, (x: any) => x?.renderFunc);
      if (!routeProps) return tree;
      afterPatch(routeProps, "renderFunc", (_: any[], ret: any) => {
        try {
          const provider = findInReactTree(ret, (x: any) =>
            x?.props?.children?.props?.overview && typeof x?.props?.value === "function");
          if (!provider) return ret;
          provider.props.value = wrap(provider.props.value, (_props: any, out: any) => {
            const builder = findInReactTree(out, (x: any) =>
              x?.props?.fnOnCancelFromTabHeader !== undefined && x?.props?.details && typeof x?.type === "function");
            if (builder) builder.type = wrap(builder.type, patchTabs);
            return out;
          });
        } catch (e) {
          console.error("[Custom Games] page patch failed", e);
        }
        return ret;
      });
    } catch (e) {
      console.error("[Custom Games] library patch failed", e);
    }
    return tree;
  });
}

export function unpatchLibraryApp(patch: any) {
  routerHook.removePatch(ROUTE, patch);
}
