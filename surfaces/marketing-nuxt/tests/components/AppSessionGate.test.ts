import { mount } from "@vue/test-utils";
import { computed, nextTick, ref, watch, type Slot } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MarketingApp from "../../app/app.vue";
import { useOperatorAppLink } from "../../../operator-kit/app/composables/useOperatorAppLink";

const lock = vi.fn();
const refreshSession = vi.fn();
let state = "anonymous";
let canIdentify = false;
let unavailable = false;

beforeEach(() => {
  state = "anonymous";
  canIdentify = false;
  unavailable = false;
  Object.assign(globalThis, {
    nextTick,
    useHead: vi.fn(),
    // O template de título do kit é auto-import do layer; aqui o app monta
    // com o vue-test-utils puro, então ele entra como os demais globais.
    useOperatorWindowTitle: vi.fn(() => ({ appName: "Marketing" })),
    useRuntimeConfig: () => ({ public: { operatorHubUrl: "/apps/" } }),
    // Implementação REAL do kit: é ela que decide se o "Voltar à Central" sai da
    // janela (app instalado) ou fica nela (aba). Mocká-la esconderia justamente o
    // que importa aqui.
    useOperatorAppLink,
    computed,
    useOperatorLock: () => ({
      canIdentify: ref(canIdentify),
      sessionState: ref(state),
      sessionUnavailable: ref(unavailable),
      operator: ref(null),
      lock,
      refresh: refreshSession,
      locked: ref(false),
      stationRef: ref(""),
    }),
    // A oferta de fixar o dispositivo num posto é do kit e tem teste próprio; aqui
    // ela fica fechada para o gate de sessão ser o único assunto.
    useStationSetupOffer: () => ({ offer: ref(false), dismiss: vi.fn(), done: vi.fn() }),
    watch,
    // O menu do operador do celular recebe o `lock` do shell por injeção.
    provideMarketingShell: vi.fn(),
  });
});

function mountApp() {
  const ProtectedPage = {
    template: '<div data-testid="protected-page">protegido</div>',
  };
  return mount(MarketingApp, {
    global: {
      stubs: {
        Icon: true,
        NuxtPage: {
          setup(_props: unknown, { slots }: { slots: { default?: Slot } }) {
            return () => slots.default?.({ Component: ProtectedPage });
          },
        },
        NuxtRouteAnnouncer: true,
        OfflineBanner: true,
        OperatorLock: true,
        OperatorLogin: true,
        MarketingNav: true,
        MarketingInboxLive: true,
        OperatorStationSetup: true,
        UiSonner: true,
      },
    },
  });
}

describe("Marketing app session gate", () => {
  it("does not mount the protected route for an anonymous operator", () => {
    const wrapper = mountApp();

    expect(wrapper.find('[data-testid="protected-page"]').exists()).toBe(false);
    expect(wrapper.findComponent({ name: "OperatorLogin" }).exists()).toBe(
      true,
    );
    // Sem sessão, nenhuma conexão da caixa pessoal.
    expect(wrapper.findComponent({ name: "MarketingInboxLive" }).exists()).toBe(false);
  });

  it("mounts the protected route only after capability authentication", () => {
    state = "authenticated";
    canIdentify = true;
    const wrapper = mountApp();

    expect(wrapper.find('[data-testid="protected-page"]').exists()).toBe(true);
    // A camada visual da suíte (V4-MKT) e a caixa pessoal, uma só, depois do gate.
    expect(wrapper.get("[data-marketing-app-root]").attributes("data-suite")).toBe("v3");
    expect(wrapper.findComponent({ name: "MarketingInboxLive" }).exists()).toBe(true);
  });

  it("keeps the route closed when the session endpoint is unavailable", () => {
    unavailable = true;
    const wrapper = mountApp();

    expect(wrapper.find('[data-testid="protected-page"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("nenhum dado de Marketing foi carregado");
  });
});
