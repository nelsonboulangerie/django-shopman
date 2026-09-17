// Indicador de capacidade no rail: neutro abaixo da atenção, âmbar acima, vermelho
// acima do crítico — e SEMPRE com texto (rótulo acessível e detalhe em pt-BR).
// Sem operador autorizado, não aparece.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";

import OperatorCapacityStatus from "../../app/components/OperatorCapacityStatus.vue";
import type { CapacityResponse } from "../../app/types/capacity";

const THRESHOLDS = { attention_percent: 75, critical_percent: 90, sustain_minutes: 5 };

const reading = ref<CapacityResponse | null>(null);
const authorized = ref(false);
const stale = ref(false);

vi.mock("../../app/composables/useOperatorCapacity", () => ({
  useOperatorCapacity: () => ({ reading, authorized, stale, refresh: vi.fn() }),
}));

function sample(memory: number, cpu: number, overrides: Partial<CapacityResponse> = {}): CapacityResponse {
  return {
    service: "pos",
    available: true,
    source: "cgroup-v2",
    memory: { used_bytes: 1, limit_bytes: 2, percent: memory },
    cpu: { percent: cpu, limit_cores: 1, window_ms: 30_000 },
    measured_at: new Date(Date.now() - 20_000).toISOString(),
    level: "normal",
    thresholds: THRESHOLDS,
    ...overrides,
  };
}

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
const mount = async () =>
  (mounted = await mountSuspended(OperatorCapacityStatus, {
    global: { stubs: { Icon: true } },
    attachTo: document.body,
  }));

beforeEach(() => {
  reading.value = null;
  authorized.value = false;
  stale.value = false;
  useRailState().set("compact");
});
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("OperatorCapacityStatus", () => {
  it("sem operador autorizado não renderiza nada", async () => {
    reading.value = sample(50, 10);
    authorized.value = false;
    const wrapper = await mount();

    expect(wrapper.find("[data-capacity-trigger]").exists()).toBe(false);
  });

  it.each([
    [62, 18, "normal", "bg-rail-foreground/45", "Capacidade do serviço: Normal — Memória 62% · CPU 18%"],
    [80, 18, "attention", "bg-warning", "Capacidade do serviço: Atenção — Memória 80% · CPU 18%"],
    [40, 95, "critical", "bg-destructive", "Capacidade do serviço: Crítica — Memória 40% · CPU 95%"],
  ])("memória %s%% · CPU %s%% → %s", async (memory, cpu, level, dot, label) => {
    reading.value = sample(memory, cpu);
    authorized.value = true;
    const wrapper = await mount();

    const trigger = wrapper.get("[data-capacity-trigger]");
    expect(trigger.attributes("data-capacity-level")).toBe(level);
    expect(trigger.attributes("aria-label")).toBe(label);
    // No compacto, o mesmo texto vira tooltip nativo.
    expect(trigger.attributes("title")).toBe(label);
    expect(wrapper.get("[data-capacity-dot]").classes()).toContain(dot);
  });

  it("sem leitura (dev local): neutro, dito em texto", async () => {
    reading.value = sample(0, 0, { available: false, memory: null, cpu: null });
    authorized.value = true;
    const wrapper = await mount();

    const trigger = wrapper.get("[data-capacity-trigger]");
    expect(trigger.attributes("data-capacity-level")).toBe("unknown");
    expect(trigger.attributes("aria-label")).toBe("Capacidade do serviço: Sem leitura");
  });

  it("rail estendido mostra o rótulo com o estado", async () => {
    useRailState().set("extended");
    reading.value = sample(80, 10);
    authorized.value = true;
    const wrapper = await mount();

    expect(wrapper.get("[data-capacity-trigger]").text()).toContain("Capacidade · Atenção");
    expect(wrapper.get("[data-capacity-trigger]").attributes("title")).toBeUndefined();
  });

  it("ao abrir, o detalhe diz os números, há quanto tempo e os limites", async () => {
    reading.value = sample(93, 18);
    authorized.value = true;
    const wrapper = await mount();

    await wrapper.get("[data-capacity-trigger]").trigger("click");
    await nextTick();
    await nextTick();

    const detail = document.body.querySelector("[data-capacity-detail]");
    expect(detail).not.toBeNull();
    const text = detail!.textContent || "";
    expect(text).toContain("Capacidade do serviço");
    expect(text).toContain("Crítica");
    expect(text).toContain("Memória 93% · CPU 18%");
    expect(text).toMatch(/atualizado há 2\d s/);
    expect(text).toContain("Se continuar por 5 min, o gestor é avisado.");
    expect(text).toContain("Atenção a partir de 75% · crítico a partir de 90%");
  });

  it.each([
    ["cgroup-v2", "Medido pelo sistema do contêiner."],
    ["cgroup-v1", "Medido pelo sistema do contêiner."],
    ["proc", "Estimado pelos processos do serviço."],
  ] as const)("o detalhe diz de onde veio o número (%s), sem jargão", async (source, text) => {
    reading.value = sample(40, 10, { source });
    authorized.value = true;
    const wrapper = await mount();

    await wrapper.get("[data-capacity-trigger]").trigger("click");
    await nextTick();
    await nextTick();

    const line = document.body.querySelector("[data-capacity-source]");
    expect(line?.textContent?.trim()).toBe(text);
    expect(document.body.querySelector("[data-capacity-detail]")?.textContent).not.toMatch(/cgroup|proc\b/);
  });

  it("sem leitura nenhuma: a frase de ambiente, e nenhuma linha de fonte", async () => {
    reading.value = sample(0, 0, { available: false, source: "none", memory: null, cpu: null });
    authorized.value = true;
    const wrapper = await mount();

    await wrapper.get("[data-capacity-trigger]").trigger("click");
    await nextTick();
    await nextTick();

    const detail = document.body.querySelector("[data-capacity-detail]");
    expect(detail?.textContent).toContain("Este ambiente não informa a capacidade do serviço.");
    expect(document.body.querySelector("[data-capacity-source]")).toBeNull();
  });

  it("falha na última tentativa fica dita, sem apagar a leitura anterior", async () => {
    reading.value = sample(50, 10);
    authorized.value = true;
    stale.value = true;
    const wrapper = await mount();

    await wrapper.get("[data-capacity-trigger]").trigger("click");
    await nextTick();
    await nextTick();

    expect(document.body.querySelector("[data-capacity-updated]")?.textContent).toContain(
      "sem resposta na última tentativa",
    );
  });
});
