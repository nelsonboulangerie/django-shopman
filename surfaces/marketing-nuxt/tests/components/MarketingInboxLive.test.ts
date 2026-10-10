import { enableAutoUnmount, mount } from "@vue/test-utils";
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import MarketingInboxLive from "~/components/MarketingInboxLive.vue";

// O dono da caixa pessoal, montado UMA vez no shell (V4-MKT). Era o sino, quando o
// sino estava em toda tela; agora o sino só existe no celular, e o que a caixa faz
// não pode depender da largura da tela. O que este teste segura: ele é a instância
// que escuta o SSE pela fila (uma só, para não duplicar fetch), e ver a fila registra
// os avisos como vistos (sem isso o aviso continua "novo" para sempre depois de lido).
const markVisible = vi.fn();
const notifications = ref([{ pk: 1 }]);
const route = reactive({ path: "/history" });
const decisionOptions: unknown[] = [];

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    onMounted,
    watch,
    useRoute: () => route,
    useMarketingNotificationInbox: () => ({ notifications, markVisible }),
    useMarketingDecisions: (options: unknown) => {
      decisionOptions.push(options);
      return { decisionCount: ref(0) };
    },
  });
});

enableAutoUnmount(afterEach);

beforeEach(() => {
  markVisible.mockReset().mockResolvedValue(true);
  notifications.value = [{ pk: 1 }];
  route.path = "/history";
  decisionOptions.length = 0;
});

function live() {
  return mount(MarketingInboxLive);
}

describe("MarketingInboxLive", () => {
  it("é a única instância que escuta a revisão da caixa pela fila", () => {
    live();
    expect(decisionOptions).toEqual([{ live: true }]);
  });

  it("registra os avisos como vistos ao abrir já na fila", () => {
    route.path = "/";
    live();
    expect(markVisible).toHaveBeenCalledTimes(1);
  });

  it("registra os avisos como vistos só quando a fila está na tela", async () => {
    live();
    expect(markVisible).not.toHaveBeenCalled();

    route.path = "/";
    await nextTick();
    expect(markVisible).toHaveBeenCalledTimes(1);

    notifications.value = [{ pk: 1 }, { pk: 2 }];
    await nextTick();
    expect(markVisible).toHaveBeenCalledTimes(2);
  });
});
