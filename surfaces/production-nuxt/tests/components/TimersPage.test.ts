import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";

import TimersPage from "../../app/pages/timers.vue";
// O card entra DE VERDADE: é a integração página↔card que importa aqui (o
// gesto em si tem teste próprio em FloorTimerCard.test.ts). Componente
// auto-importado pelo Nuxt não se resolve sozinho no ambiente de componente.
import FloorTimerCard from "../../app/components/FloorTimerCard.vue";
import type { FloorTimerEntry } from "../../app/composables/useFloorTimers";

// A página é dirigida por dois composables: a fileira de etiquetas (servidor) e
// os timers (dispositivo). Ambos são stubados com refs controláveis; o que se prova
// é a UX pedida: UM toque na etiqueta dispara, "Novo timer" abre o caminho
// livre, e os ativos aparecem como cards.
const entries = ref<FloorTimerEntry[]>([]);
const tags = ref([
  { ref: "estufa", label: "Estufa", minutes: 60, origin: "admin" as const },
  { ref: "pausa-cafe", label: "Pausa-café", minutes: 15, origin: "admin" as const },
]);
const createSpy = vi.fn();
const seenSpy = vi.fn();
const clearSpy = vi.fn();
const extendSpy = vi.fn();
const createTagSpy = vi.fn();
const sonnerSuccess = vi.fn();

const stubs = {
  Icon: true,
  ProductionHeader: {
    props: ["title", "count", "countLabel", "pending", "query"],
    template: '<header><h1>{{ title }}</h1><span data-count>{{ count }}</span></header>',
  },
  FloorTimerCreateDialog: {
    props: ["open", "lastMinutes", "tags", "savingTag"],
    template: '<div v-if="open" data-create-dialog />',
  },
};

function entry(overrides: Partial<FloorTimerEntry> = {}): FloorTimerEntry {
  return {
    key: "free:abc",
    endsAt: 0,
    minutes: 20,
    mode: "running",
    title: "Descanso",
    kind: "free",
    ...overrides,
  } as FloorTimerEntry;
}

let wrapper: VueWrapper | null = null;

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onMounted", onMounted);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useHead", () => {});
  vi.stubGlobal("useSonner", { success: sonnerSuccess, error: vi.fn() });
  vi.stubGlobal("useFloorTimers", () => ({
    entries,
    activeCount: computed(() => entries.value.length),
    ringingCount: computed(
      () => entries.value.filter((item) => item.mode === "ringing").length,
    ),
    lastMinutes: ref<number | null>(null),
    create: createSpy,
    seen: seenSpy,
    clear: clearSpy,
    extend: extendSpy,
    remainingLabel: () => "12:34",
  }));
  vi.stubGlobal("useTimerTags", () => ({
    tags,
    pending: ref(false),
    error: ref(null),
    forbidden: computed(() => false),
    refresh: vi.fn(),
    createTag: createTagSpy,
    saving: ref(false),
  }));
  entries.value = [];
  createSpy.mockClear();
  createTagSpy.mockClear();
  createTagSpy.mockResolvedValue({ ok: true, created: true, tag: tags.value[0] });
  sonnerSuccess.mockClear();
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
  vi.unstubAllGlobals();
});

async function mountPage() {
  wrapper = mount(TimersPage, {
    global: { stubs, components: { FloorTimerCard } },
    attachTo: document.body,
  });
  await nextTick();
  return wrapper;
}

const byLabel = (w: VueWrapper, label: string) =>
  w.findAll("button").find((button) => button.attributes("aria-label") === label);

describe("Página /timers — disparo de um toque", () => {
  it("cada etiqueta vira um botão que já mostra o tempo dela", async () => {
    const page = await mountPage();

    expect(byLabel(page, "Disparar Estufa, 1 h")?.exists()).toBe(true);
    expect(byLabel(page, "Disparar Pausa-café, 15 min")?.exists()).toBe(true);
  });

  it("um toque na etiqueta ARMA o timer, sem diálogo e sem confirmação", async () => {
    const page = await mountPage();

    await byLabel(page, "Disparar Estufa, 1 h")!.trigger("click");

    expect(createSpy).toHaveBeenCalledWith(60, { label: "Estufa" });
    expect(page.find("[data-create-dialog]").exists()).toBe(false);
  });

  it('"Novo timer" abre o caminho livre', async () => {
    const page = await mountPage();
    expect(page.find("[data-create-dialog]").exists()).toBe(false);

    const novo = page.findAll("button").find((b) => b.text().includes("Novo timer"));
    await novo!.trigger("click");

    expect(page.find("[data-create-dialog]").exists()).toBe(true);
  });
});

describe("Página /timers — os ativos como cards", () => {
  it("sem timer correndo, a tela convida em vez de ficar vazia", async () => {
    const page = await mountPage();
    expect(page.text()).toContain("Nenhum timer correndo");
  });

  it("cada timer ativo vira um card, e o cabeçalho conta os ativos", async () => {
    entries.value = [
      entry({ key: "a", title: "Descanso" }),
      entry({ key: "b", title: "Estufa", mode: "ringing" }),
    ];
    const page = await mountPage();

    expect(page.findAll("li")).toHaveLength(2);
    expect(page.find("[data-count]").text()).toBe("2");
    expect(page.text()).toContain("Descanso");
    expect(page.text()).toContain("Estufa");
  });

  it("o card repassa Visto, Encerrar e +5 para o mecanismo do dispositivo", async () => {
    entries.value = [entry({ key: "a", title: "Estufa", mode: "ringing" })];
    const page = await mountPage();

    const card = page.find("li");
    await card.findAll("button")[0]!.trigger("click");
    expect(seenSpy).toHaveBeenCalledWith("a");

    const explicit = card.findAll("button");
    await explicit.find((b) => b.text() === "+5 min")!.trigger("click");
    expect(extendSpy).toHaveBeenCalledWith("a", 5);

    await explicit.find((b) => b.text() === "Encerrar")!.trigger("click");
    expect(clearSpy).toHaveBeenCalledWith("a");
  });
});

describe("Página /timers — a fileira vazia diz o que fazer", () => {
  it("sem etiqueta nenhuma, a tela aponta para o caminho de criar", async () => {
    tags.value = [];
    const page = await mountPage();

    expect(page.text()).toContain("Nenhuma etiqueta cadastrada ainda");
    tags.value = [
      { ref: "estufa", label: "Estufa", minutes: 60, origin: "admin" },
      { ref: "pausa-cafe", label: "Pausa-café", minutes: 15, origin: "admin" },
    ];
  });
});
