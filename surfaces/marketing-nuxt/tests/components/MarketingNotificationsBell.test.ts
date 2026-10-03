import { enableAutoUnmount, mount, RouterLinkStub } from "@vue/test-utils";
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import MarketingNotificationsBell from "~/components/MarketingNotificationsBell.vue";

// Decisão do dono (03/10/2026): o sino abre a fila de decisões e não tem lista
// própria. O que este teste segura: o número é o das decisões, o gesto leva à
// casa, e ver a fila registra os avisos como vistos (sem isso o aviso continua
// "novo" para sempre depois de lido).
const markVisible = vi.fn();
const notifications = ref([{ pk: 1 }]);
const decisionCount = ref(3);
const route = reactive({ path: "/history" });
const decisionOptions: unknown[] = [];

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    onMounted,
    ref,
    watch,
    useRoute: () => route,
    useMarketingNotificationInbox: () => ({ notifications, markVisible }),
    useMarketingDecisions: (options: unknown) => {
      decisionOptions.push(options);
      return { decisionCount };
    },
  });
});

enableAutoUnmount(afterEach);

beforeEach(() => {
  markVisible.mockReset().mockResolvedValue(true);
  notifications.value = [{ pk: 1 }];
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
  it("leva à fila de decisões e mostra o número de decisões", () => {
    const wrapper = bell();
    const link = wrapper.getComponent(RouterLinkStub);

    expect(link.props("to")).toBe("/");
    expect(link.attributes("aria-label")).toBe("Decisões: 3 esperando você");
    expect(wrapper.text()).toContain("3");
    // O sino é a instância que escuta o SSE pela fila (uma só, para não duplicar fetch).
    expect(decisionOptions).toEqual([{ live: true }]);
  });

  it("não mostra número quando nada espera, e diz isso a quem não vê", () => {
    decisionCount.value = 0;
    const wrapper = bell();

    expect(wrapper.find("span[aria-hidden='true']").exists()).toBe(false);
    expect(wrapper.getComponent(RouterLinkStub).attributes("aria-label")).toBe(
      "Decisões: nada esperando você",
    );
  });

  it("registra os avisos como vistos ao abrir já na fila", () => {
    route.path = "/";
    bell();
    expect(markVisible).toHaveBeenCalledTimes(1);
  });

  it("registra os avisos como vistos só quando a fila está na tela", async () => {
    bell();
    expect(markVisible).not.toHaveBeenCalled();

    route.path = "/";
    await nextTick();
    expect(markVisible).toHaveBeenCalledTimes(1);

    notifications.value = [{ pk: 1 }, { pk: 2 }];
    await nextTick();
    expect(markVisible).toHaveBeenCalledTimes(2);
  });
});
