import { describe, expect, it } from "vitest";
import { operatorOfflineShellCaching } from "../pwa.config";

// O casco sem conexão vira TEXTO no `sw.js` (o workbox-build serializa as funções por
// `toString()`). Cada função aqui é reidratada a partir do próprio texto antes de
// rodar: é o que prova que nada depende de variável deste módulo.
const BUILD = "0f3c2a9e-build-atual";

function revive<T>(fn: unknown): T {
   
  return new Function(`return (${String(fn)})`)() as T;
}

type Plugin = {
  cacheKeyWillBeUsed: (context: { request: Request }) => Promise<string>;
  cacheWillUpdate: (context: { request: Request; response: Response }) => Promise<Response | null>;
  cachedResponseWillBeUsed: (context: { cachedResponse?: Response }) => Promise<Response | null>;
};

function shell(paths = ["/"]) {
  const route = operatorOfflineShellCaching("pos", paths, BUILD);
  const raw = route.options!.plugins![0]! as unknown as Record<keyof Plugin, unknown>;
  const plugin: Plugin = {
    cacheKeyWillBeUsed: revive(raw.cacheKeyWillBeUsed),
    cacheWillUpdate: revive(raw.cacheWillUpdate),
    cachedResponseWillBeUsed: revive(raw.cachedResponseWillBeUsed),
  };
  const matches = revive<(context: { request: { mode: string }; url: URL }) => boolean>(route.urlPattern);
  return { route, plugin, matches };
}

const html = (build: string) => `<html><script>window.__NUXT__.config={app:{buildId:"${build}"}}</script></html>`;
const page = (body: string, init: ResponseInit = { status: 200 }) => new Response(body, { ...init, headers: { "content-type": "text/html" } });

describe("casco sem conexão (offlineShellPaths)", () => {
  it("só a navegação das rotas declaradas abre de cache; o resto segue NetworkOnly", () => {
    const { route, matches } = shell(["/"]);
    expect(route.handler).toBe("NetworkFirst");
    expect(route.options!.cacheName).toBe("pos-shell");
    expect(route.options!.precacheFallback).toEqual({ fallbackURL: "/offline.html" });
    expect(matches({ request: { mode: "navigate" }, url: new URL("https://pdv.example/") })).toBe(true);
    expect(matches({ request: { mode: "navigate" }, url: new URL("https://pdv.example/?source=pwa") })).toBe(true);
    expect(matches({ request: { mode: "navigate" }, url: new URL("https://pdv.example/session") })).toBe(false);
    expect(matches({ request: { mode: "cors" }, url: new URL("https://pdv.example/") })).toBe(false);
  });

  it("guarda só o HTML 200 da MESMA build, sem redirecionamento e sem query que muda a tela", async () => {
    const { plugin } = shell();
    const root = new Request("https://pdv.example/");
    expect(await plugin.cacheWillUpdate({ request: root, response: page(html(BUILD)) })).not.toBeNull();
    expect(await plugin.cacheWillUpdate({ request: new Request("https://pdv.example/?source=pwa"), response: page(html(BUILD)) })).not.toBeNull();
    // Outra build (HTML servido por um deploy diferente do service worker).
    expect(await plugin.cacheWillUpdate({ request: root, response: page(html("build-anterior")) })).toBeNull();
    // Erro do servidor, ou a tela de editar uma encomenda (`?edit=`): não é o casco.
    expect(await plugin.cacheWillUpdate({ request: root, response: page(html(BUILD), { status: 503 }) })).toBeNull();
    expect(await plugin.cacheWillUpdate({ request: new Request("https://pdv.example/?edit=NB-1"), response: page(html(BUILD)) })).toBeNull();
  });

  it("o HTML guardado de outra build NÃO abre: cai no offline.html", async () => {
    const { plugin } = shell();
    expect(await plugin.cachedResponseWillBeUsed({ cachedResponse: page(html(BUILD)) })).not.toBeNull();
    expect(await plugin.cachedResponseWillBeUsed({ cachedResponse: page(html("build-anterior")) })).toBeNull();
    expect(await plugin.cachedResponseWillBeUsed({})).toBeNull();
  });

  it("guarda sob o caminho limpo: o ícone instalado (`?source=pwa`) e o reload abrem o mesmo casco", async () => {
    const { plugin } = shell();
    expect(await plugin.cacheKeyWillBeUsed({ request: new Request("https://pdv.example/?source=pwa") })).toBe("https://pdv.example/");
    expect(await plugin.cacheKeyWillBeUsed({ request: new Request("https://pdv.example/") })).toBe("https://pdv.example/");
  });

  it("recusa configuração sem buildId ou com caminho relativo", () => {
    expect(() => operatorOfflineShellCaching("pos", ["/"], "")).toThrow(/buildId/);
    expect(() => operatorOfflineShellCaching("pos", ["venda"], BUILD)).toThrow(/absolutos/);
    expect(() => operatorOfflineShellCaching("pos", [], BUILD)).toThrow(/absolutos/);
  });
});
