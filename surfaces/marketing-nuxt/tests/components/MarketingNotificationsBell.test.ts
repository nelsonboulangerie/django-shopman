import { enableAutoUnmount, mount, RouterLinkStub } from "@vue/test-utils";
import { computed, reactive, ref } from "vue";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import MarketingNotificationsBell from "~/components/MarketingNotificationsBell.vue";

// Decisão do dono (03/10/2026): o sino abre a fila de decisões e não tem lista
// própria. Camada visual da suíte (V4-MKT): ele mora na barra de 56px do celular, com
// o ponto âmbar quando algo espera; o número vai por extenso no nome acessível. A
// caixa pessoal (SSE, poll e "visto") saiu dele para o `MarketingInboxLive`, que tem
// teste próprio.
const decisionCount = ref(3);
const route = reactive({ path: "/history" });
const decisionOptions: unknown[] = [];

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    useRoute: () => route,
    useMarketingDecisions: (options: unknown) => {
      decisionOptions.push(options);
      return { decisionCount };
    },
  });
});

enableAutoUnmount(afterEach);

beforeEach(() => {
  decisionCount.value = 3;
  route.path = "/history";
  decisionOptions.length = 0;
});

function bell() {
  return mount(MarketingNotificationsBell, {
    global: { stubs: { Icon: true, NuxtLink: RouterLinkStub } },
  });
}

describe("MarketingNotificationsBell", () => {
  it("leva à fila de decisões e diz quantas esperam", () => {
    const wrapper = bell();
    const link = wrapper.getComponent(RouterLinkStub);

    expect(link.props("to")).toBe("/");
    expect(link.attributes("aria-label")).toBe("Decisões: 3 esperando você");
    expect(wrapper.find("[data-marketing-bell-dot]").exists()).toBe(true);
    // O sino só lê a fila: quem escuta o SSE é o `MarketingInboxLive` (um só).
    expect(decisionOptions).toEqual([undefined]);
  });

  it("não mostra o ponto quando nada espera, e diz isso a quem não vê", () => {
    decisionCount.value = 0;
    const wrapper = bell();

    expect(wrapper.find("[data-marketing-bell-dot]").exists()).toBe(false);
    expect(wrapper.getComponent(RouterLinkStub).attributes("aria-label")).toBe(
      "Decisões: nada esperando você",
    );
  });

  it("marca a fila como a página atual quando ela está na tela", () => {
    route.path = "/";
    expect(
      bell().getComponent(RouterLinkStub).attributes("aria-current"),
    ).toBe("page");
  });
});
