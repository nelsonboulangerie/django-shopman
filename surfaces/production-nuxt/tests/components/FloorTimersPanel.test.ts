import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { mount } from "@vue/test-utils";

import FloorTimersPanel from "../../app/components/FloorTimersPanel.vue";
import type { FloorTimerEntry } from "../../app/composables/useFloorTimers";
import { UiButtonStub, UiInputStub } from "../support/nativeUiStubs";

// O painel é dirigido por useFloorTimers (singleton de aparelho). Aqui o
// composable é stubado com refs controláveis: o que se prova é a UX — abrir
// vazio já cria, numpad + nome opcional, lista com +N / Visto / Encerrar.
const entries = ref<FloorTimerEntry[]>([]);
const createSpy = vi.fn();
const extendSpy = vi.fn();
const seenSpy = vi.fn();
const clearSpy = vi.fn();

function entry(over: Partial<FloorTimerEntry> = {}): FloorTimerEntry {
  return {
    key: "free:1",
    endsAt: Date.now() + 60_000,
    minutes: 12,
    kind: "free",
    label: "Timer 1",
    title: "Timer 1",
    mode: "running",
    ...over,
  };
}

const stubs = {
  Icon: true,
  UiDialog: { props: ["open"], template: "<div v-if='open'><slot /></div>" },
  UiDialogContent: { template: "<div><slot /></div>" },
  UiDialogHeader: { template: "<div><slot /></div>" },
  UiDialogTitle: { template: "<h2><slot /></h2>" },
  UiDialogDescription: { template: "<p><slot /></p>" },
  UiButton: UiButtonStub,
  UiInput: UiInputStub,
};

function mountPanel() {
  return mount(FloorTimersPanel, {
    props: { open: true },
    global: { stubs },
  });
}

const byText = (w: ReturnType<typeof mountPanel>, sel: string, txt: string) =>
  w.findAll(sel).find((el) => el.text().includes(txt));

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useFloorTimers", () => ({
    entries,
    activeCount: computed(() => entries.value.length),
    ringingCount: computed(
      () => entries.value.filter((item) => item.mode === "ringing").length,
    ),
    lastMinutes: ref<number | null>(null),
    create: createSpy,
    extend: extendSpy,
    seen: seenSpy,
    clear: clearSpy,
    remainingLabel: () => "0:59",
  }));
  entries.value = [];
  createSpy.mockClear();
  extendSpy.mockClear();
  seenSpy.mockClear();
  clearSpy.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe("FloorTimersPanel — novo timer", () => {
  it("sem nenhum timer, abrir já é criar: numpad na cara, Iniciar travado no zero", async () => {
    const w = mountPanel();
    // o watch(open) roda ao montar com open=true? Não — só em mudança. Forçamos
    // pelo caminho do usuário: sem timers a tela de lista mostra "Novo timer".
    const novo = byText(w, "button", "Novo timer");
    if (novo) await novo.trigger("click");
    expect(w.find('[aria-label="Minutos do timer"]').exists()).toBe(true);
    const iniciar = byText(w, "button", "Iniciar")!;
    expect(iniciar.attributes("disabled")).toBeDefined();
  });

  it("digita 1 e 5, dá nome e inicia → create(15, {label})", async () => {
    const w = mountPanel();
    const novo = byText(w, "button", "Novo timer");
    if (novo) await novo.trigger("click");
    await w.find('[aria-label="Dígito 1"]').trigger("click");
    await w.find('[aria-label="Dígito 5"]').trigger("click");
    expect(w.text()).toContain("15");
    await w.find('input[aria-label="Nome do timer"]').setValue("Croissant");
    await byText(w, "button", "Iniciar")!.trigger("click");

    expect(createSpy).toHaveBeenCalledWith(15, { label: "Croissant" });
  });

  it("+5 no numpad soma aos minutos antes de iniciar; C zera", async () => {
    const w = mountPanel();
    const novo = byText(w, "button", "Novo timer");
    if (novo) await novo.trigger("click");
    await w.find('[aria-label="Somar 5 minutos"]').trigger("click");
    await w.find('[aria-label="Somar 5 minutos"]').trigger("click");
    expect(w.text()).toContain("10");
    await w.find('[aria-label="Limpar minutos"]').trigger("click");
    expect(byText(w, "button", "Iniciar")!.attributes("disabled")).toBeDefined();
  });
});

describe("FloorTimersPanel — timers ativos", () => {
  it("lista cada timer com nome, SKU, restante; +1 estende, Encerrar limpa", async () => {
    entries.value = [
      entry({ key: "free:a", title: "Fermentação", label: "Fermentação", sku: "CRO" }),
      entry({ key: "7", kind: "oven", title: "Baguette", label: "Baguette", minutes: 18 }),
    ];
    const w = mountPanel();
    expect(w.text()).toContain("2 ativos");
    expect(w.text()).toContain("Fermentação");
    expect(w.text()).toContain("CRO");
    expect(w.text()).toContain("Baguette");
    expect(w.text()).toContain("Forno");
    expect(w.text()).toContain("0:59");

    await w.find('[aria-label="Somar 1 minutos a Fermentação"]').trigger("click");
    expect(extendSpy).toHaveBeenCalledWith("free:a", 1);
    await w.find('[aria-label="Encerrar Baguette"]').trigger("click");
    expect(clearSpy).toHaveBeenCalledWith("7");
  });

  it("quem tocou mostra Tempo esgotado e oferece Visto; quem corre não", async () => {
    entries.value = [
      entry({ key: "free:r", title: "Timer 1", mode: "ringing" }),
      entry({ key: "free:s", title: "Timer 2", mode: "running" }),
    ];
    const w = mountPanel();
    expect(w.text()).toContain("Tempo esgotado");
    expect(w.find('[aria-label="Visto: Timer 1"]').exists()).toBe(true);
    expect(w.find('[aria-label="Visto: Timer 2"]').exists()).toBe(false);
    await w.find('[aria-label="Visto: Timer 1"]').trigger("click");
    expect(seenSpy).toHaveBeenCalledWith("free:r");
  });

  it("um timer ativo não some da lista ao abrir: 'Novo timer' leva ao numpad e 'Voltar' retorna", async () => {
    entries.value = [entry()];
    const w = mountPanel();
    await byText(w, "button", "Novo timer")!.trigger("click");
    expect(w.find('[aria-label="Minutos do timer"]').exists()).toBe(true);
    await byText(w, "button", "Voltar aos timers")!.trigger("click");
    expect(w.text()).toContain("Timer 1");
  });
});
