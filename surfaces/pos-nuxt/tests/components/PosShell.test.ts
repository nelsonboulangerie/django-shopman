// A raiz do PDV escolhe UM shell por rota — e a tela do cliente nunca sobe no
// shell de operador.
//
// O display já foi uma tela de operador com N condicionais para não se
// comportar como tal (`v-if="!isCustomerDisplay"` em cima de lock, login,
// auto-lock, SSE), e ainda disparava os fetches autenticados que não lhe
// serviam. Bastou isso para a janela que ninguém toca derrubar a sessão da
// estação no meio da venda. Aqui a prova é estrutural: em `/display` NENHUM
// composable de operador é chamado — não é "desligado", é ausente.
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import App from "~/app.vue";

const { calls } = vi.hoisted(() => ({
  calls: { terminal: 0, operatorLock: 0, autoLock: 0, events: 0 },
}));

// Os composables de operador viram contadores: a pergunta deste arquivo é SE
// eles rodam, não o que fazem (isso cada um prova no próprio teste).
mockNuxtImport("usePosTerminal", () => async () => {
  calls.terminal += 1;
  return { pos: ref(null), refresh: vi.fn() };
});
mockNuxtImport("useOperatorLock", () => () => {
  calls.operatorLock += 1;
  // Dispositivo que ainda não é estação (antessala respondeu 403): a tela de
  // senha é o que o shell de operador mostra.
  return {
    locked: ref(false),
    canIdentify: ref(false),
    stationRef: ref(""),
    mustChange: ref(false),
    lock: vi.fn(),
  };
});
mockNuxtImport("usePosAutoLock", () => () => {
  calls.autoLock += 1;
});
mockNuxtImport("usePosEvents", () => () => {
  calls.events += 1;
  return { realtime: ref("polling") };
});
mockNuxtImport("useConnectivity", () => () => ({ isOnline: ref(true), onReconnect: vi.fn() }));

const OPERATOR_CHROME = { OperatorLock: true, OperatorStationSetup: true, OfflineBanner: true, UiSonner: true };
const PAGE_STUB = { NuxtPage: { template: '<div data-testid="page" />' } };

// O wrapper de um caso não morre sozinho no fim dele: fica montado (solto do
// documento, mas reativo) e re-renderiza a página REAL quando o caso seguinte
// troca a rota — foi assim que `index.vue` subiu no meio do teste da rota de
// operador. Cada caso desmonta o que montou.
const mounted: VueWrapper[] = [];
async function open(route: string, stubs: Record<string, unknown>) {
  const wrapper = await mountSuspended(App, { route, global: { stubs } });
  mounted.push(wrapper as unknown as VueWrapper);
  // O shell de operador tem setup assíncrono (`await usePosTerminal()`): o
  // mount resolve com o filho ainda no Suspense. Dois ciclos de microtasks
  // bastam para o mock resolver e a árvore assentar.
  await flushPromises();
  await flushPromises();
  return wrapper;
}

describe("app.vue — um shell por rota", () => {
  beforeEach(() => {
    calls.terminal = 0;
    calls.operatorLock = 0;
    calls.autoLock = 0;
    calls.events = 0;
  });
  afterEach(() => {
    for (const wrapper of mounted.splice(0)) wrapper.unmount();
  });

  it("/display sobe no shell kiosk: sem Projection, sem lock, sem auto-lock, sem SSE, sem senha", async () => {
    const wrapper = await open("/display", { ...OPERATOR_CHROME, ...PAGE_STUB });

    expect(wrapper.find('[data-pos-shell="customer-display"]').exists()).toBe(true);
    expect(wrapper.find('[data-pos-shell="operator"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="page"]').exists()).toBe(true);

    expect(calls).toEqual({ terminal: 0, operatorLock: 0, autoLock: 0, events: 0 });
    // Nada de tela de senha na parede.
    expect(wrapper.find("form").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Entre para operar o caixa");
  });

  it("/display renderiza a própria página do cliente dentro do shell kiosk", async () => {
    // Sem estação falando no canal, a parede fica nas boas-vindas — e continua
    // sem nenhum chrome de operador em volta.
    const wrapper = await open("/display", OPERATOR_CHROME);

    expect(wrapper.find('[data-pos-shell="customer-display"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Que bom ter você aqui.");
    expect(calls.terminal).toBe(0);
    expect(calls.operatorLock).toBe(0);
  });

  it("rota de operador sobe no shell de operador: Projection, lock, auto-lock e SSE ligados", async () => {
    const wrapper = await open("/", { ...OPERATOR_CHROME, ...PAGE_STUB });

    expect(wrapper.find('[data-pos-shell="operator"]').exists()).toBe(true);
    expect(wrapper.find('[data-pos-shell="customer-display"]').exists()).toBe(false);

    expect(calls.terminal).toBe(1);
    expect(calls.operatorLock).toBe(1);
    expect(calls.autoLock).toBe(1);
    expect(calls.events).toBe(1);
    // Dispositivo sem estação reconhecida: a tela de senha, no lugar da página.
    expect(wrapper.text()).toContain("Entre para operar o caixa");
    expect(wrapper.find('[data-testid="page"]').exists()).toBe(false);
  });
});
