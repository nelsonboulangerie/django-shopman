import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import OperatorPageHeader from "../../app/components/OperatorPageHeader.vue";
import OperatorScreenState from "../../app/components/OperatorScreenState.vue";
import { moreAlertsLabel, screenStateCopy } from "../../app/presentation/screenState";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

const state = () => document.querySelector<HTMLElement>("[data-operator-screen-state]")!;

describe("a frase de cada estado, uma só na suíte", () => {
  it("diz o que a tela mostra", () => {
    expect(screenStateCopy("loading", { what: "a fila" }).title).toBe("Carregando a fila");
    expect(screenStateCopy("error", { what: "os lotes do período" }).title).toBe(
      "Não foi possível carregar os lotes do período",
    );
    expect(screenStateCopy("offline", { since: "10:42" })).toEqual({
      title: "Sem conexão.",
      description: "O que está na tela é de 10:42.",
    });
    expect(moreAlertsLabel(1)).toBe("e mais 1 aviso");
    expect(moreAlertsLabel(3)).toBe("e mais 3 avisos");
  });

  it("nenhuma frase usa travessão", () => {
    for (const kind of ["loading", "empty", "error", "offline"] as const) {
      const copy = screenStateCopy(kind, { what: "a fila", since: "10:42" });
      expect(`${copy.title} ${copy.description}`).not.toMatch(/[—–]/);
    }
  });
});

describe("OperatorScreenState", () => {
  it("erro: aviso error com Tentar de novo na cor do aviso, do tamanho da suíte", async () => {
    mounted = await mountSuspended(OperatorScreenState, {
      attachTo: document.body,
      props: { state: "error", what: "a fila" },
    });
    expect(state().getAttribute("data-operator-screen-state")).toBe("error");
    expect(state().getAttribute("role")).toBe("alert");
    expect(state().textContent).toContain("Não foi possível carregar a fila");
    const retry = [...state().querySelectorAll("button")].find((button) =>
      button.textContent?.includes("Tentar de novo"),
    )!;
    expect(retry).toBeDefined();
    retry.click();
    expect(mounted.emitted("retry")).toHaveLength(1);
  });

  it("carregando e vazio: o NuxtEmpty oficial; dentro do cartão, sem moldura própria", async () => {
    mounted = await mountSuspended(OperatorScreenState, {
      attachTo: document.body,
      props: { state: "loading", what: "a fila", inCard: true },
    });
    expect(state().textContent).toContain("Carregando a fila");
    mounted.unmount();
    mounted = await mountSuspended(OperatorScreenState, {
      attachTo: document.body,
      props: { state: "empty", title: "Nenhum lote fechado no período" },
    });
    expect(state().getAttribute("data-operator-screen-state")).toBe("empty");
    expect(state().textContent).toContain("Nenhum lote fechado no período");
  });

  it("sem conexão: aviso warning com a hora do que está na tela", async () => {
    mounted = await mountSuspended(OperatorScreenState, {
      attachTo: document.body,
      props: { state: "offline", since: "10:42" },
    });
    expect(state().getAttribute("role")).toBe("status");
    expect(state().textContent).toContain("O que está na tela é de 10:42.");
  });
});

describe("OperatorPageHeader: o lugar do aviso da tela", () => {
  it("um aviso inteiro, o resto em \"e mais N\", que abre os outros", async () => {
    mounted = await mountSuspended(OperatorPageHeader, {
      attachTo: document.body,
      props: {
        title: "Pedidos",
        search: false,
        inbox: false,
        alerts: [
          { id: "a", color: "warning", title: "2 pedidos passaram do horário" },
          { id: "b", color: "info", title: "A impressora está sem papel" },
          { id: "c", color: "error", title: "O Pix não respondeu" },
        ],
      },
    });
    const shown = () => document.querySelectorAll("[data-page-header-alert]");
    expect(shown()).toHaveLength(1);
    expect(shown()[0]!.textContent).toContain("2 pedidos passaram do horário");
    const more = document.querySelector<HTMLButtonElement>("[data-page-header-alerts-more]")!;
    expect(more.textContent?.trim()).toBe("e mais 2 avisos");
    more.click();
    await nextTick();
    expect(shown()).toHaveLength(3);
    expect(document.querySelector("[data-page-header-alerts-more]")).toBeNull();
  });

  it("sem avisos, nenhuma faixa", async () => {
    mounted = await mountSuspended(OperatorPageHeader, {
      attachTo: document.body,
      props: { title: "Pedidos", search: false, inbox: false },
    });
    expect(document.querySelector("[data-page-header-alerts]")).toBeNull();
  });
});
