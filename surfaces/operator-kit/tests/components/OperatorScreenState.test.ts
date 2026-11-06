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
    for (const kind of ["loading", "empty", "error", "offline", "forbidden"] as const) {
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
    expect(state().getAttribute("data-orientation")).toBe("vertical");
    expect(state().textContent).toContain("Não foi possível carregar a fila");
    const retry = [...state().querySelectorAll("button")].find((button) =>
      button.textContent?.includes("Tentar de novo"),
    )!;
    expect(retry).toBeDefined();
    expect(state().className).toContain("max-sm:flex-wrap");
    expect(state().querySelector<HTMLElement>('[data-slot="actions"]')?.className).toContain(
      "max-sm:basis-full",
    );
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

  it("sem permissão: diz de quem é, e não oferece Tentar de novo (beta 05/11, CEN-05)", async () => {
    expect(screenStateCopy("forbidden", { what: "o Catálogo" })).toEqual({
      title: "Sua conta não abre o Catálogo",
      description: "Peça o acesso a um gerente.",
    });
    mounted = await mountSuspended(OperatorScreenState, {
      attachTo: document.body,
      props: { state: "forbidden", what: "o Catálogo" },
    });
    expect(state().getAttribute("data-operator-screen-state")).toBe("forbidden");
    expect(state().textContent).toContain("Sua conta não abre o Catálogo");
    expect(state().textContent).not.toContain("Sem conexão");
    expect(state().querySelector("button")).toBeNull();
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
    expect(shown()[0]!.getAttribute("data-orientation")).toBe("vertical");
    expect(shown()[0]!.textContent).toContain("2 pedidos passaram do horário");
    const more = document.querySelector<HTMLButtonElement>("[data-page-header-alerts-more]")!;
    expect(more.textContent?.trim()).toBe("e mais 2 avisos");
    more.click();
    await nextTick();
    expect(shown()).toHaveLength(3);
    expect(document.querySelector("[data-page-header-alerts-more]")).toBeNull();
  });

  it("o selo do posto vira ícone abaixo de xl e não quebra em duas linhas (beta 05/11, PDV2-17)", async () => {
    useNuxtData("operator-session").data.value = {
      workstation: { context_label: "Posto PDV principal" },
    };
    try {
      mounted = await mountSuspended(OperatorPageHeader, {
        attachTo: document.body,
        props: { title: "Encomendas", search: false, inbox: false },
      });
      const full = document.querySelector<HTMLElement>("[data-page-header-eyebrow]")!;
      // O selo leva iniciais maiúsculas (NuxtBadge, #2130); o nome lido não.
      expect(full.textContent).toContain("Posto PDV Principal · Este Dispositivo");
      expect(full.className).toContain("max-xl:hidden");
      expect(full.className).toContain("whitespace-nowrap");
      const icon = document.querySelector<HTMLElement>("[data-page-header-eyebrow-icon]")!;
      expect(icon.className).toContain("xl:hidden");
      expect(icon.getAttribute("aria-label")).toBe("Posto PDV principal · este dispositivo");
    } finally {
      useNuxtData("operator-session").data.value = undefined;
    }
  });

  it("o eyebrow que a tela declara fica escrito (é o assunto dela)", async () => {
    mounted = await mountSuspended(OperatorPageHeader, {
      attachTo: document.body,
      props: { title: "Croissant", eyebrow: "Rascunho · Versão 3", search: false, inbox: false },
    });
    expect(document.querySelector("[data-page-header-eyebrow]")?.className).toContain("max-sm:hidden");
    expect(document.querySelector("[data-page-header-eyebrow-icon]")).toBeNull();
  });

  it("sem avisos, nenhuma faixa", async () => {
    mounted = await mountSuspended(OperatorPageHeader, {
      attachTo: document.body,
      props: { title: "Pedidos", search: false, inbox: false },
    });
    expect(document.querySelector("[data-page-header-alerts]")).toBeNull();
  });

  it("dispensa sem resolver: libera a tela agora e volta numa nova montagem", async () => {
    const props = {
      title: "Pedidos",
      search: false,
      inbox: false,
      alerts: [{ id: "late", color: "warning" as const, title: "2 pedidos passaram do horário" }],
    };
    mounted = await mountSuspended(OperatorPageHeader, {
      attachTo: document.body,
      props,
    });

    const close = document.querySelector<HTMLButtonElement>('[data-slot="close"]')!;
    expect(close).toBeDefined();
    close.click();
    await nextTick();
    expect(document.querySelector("[data-page-header-alerts]")).toBeNull();

    mounted.unmount();
    document.body.innerHTML = "";
    mounted = await mountSuspended(OperatorPageHeader, {
      attachTo: document.body,
      props,
    });
    expect(document.querySelector("[data-page-header-alert]")?.textContent).toContain(
      "2 pedidos passaram do horário",
    );
  });
});
