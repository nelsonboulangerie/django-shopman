import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";

import OperatorActionBar from "../../app/components/OperatorActionBar.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

const bar = () => document.querySelector<HTMLElement>("[data-operator-action-bar]")!;

describe("OperatorActionBar, a ação do momento na base do celular", () => {
  it("é rodapé em fluxo, marcado como obstrução, só abaixo de lg e fora com o teclado", async () => {
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: { action: { label: "Pronto para retirar" } },
    });
    const root = bar();
    expect(root.tagName).toBe("FOOTER");
    expect(root.hasAttribute("data-focus-obstruction")).toBe(true);
    expect(root.getAttribute("aria-label")).toBe("Ação do momento");
    expect(root.className).toContain("lg:hidden");
    expect(root.className).toContain("in-data-[keyboard=open]:hidden");
    // Em fluxo: nunca grudada à mão.
    expect(root.className).not.toMatch(/(?:^|\s)(?:fixed|sticky)(?:\s|$)/);
    // O cartão flutua em superfície invertida (escura no claro, creme no escuro).
    const surface = root.querySelector<HTMLElement>("[data-operator-action-bar-surface]")!;
    expect(surface.className).toContain("bg-inverted");
    expect(surface.className).toContain("text-inverted");
    expect(surface.className).toContain("shadow-lg");
  });

  it("linha de contexto, uma ação larga xl que age", async () => {
    const onSelect = vi.fn();
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: {
        action: { label: "Pronto para retirar", onSelect },
        contextLabel: "Pedido 1048 · Ana Souza",
        contextValue: "R$ 48,70",
      },
    });
    expect(document.querySelector("[data-operator-action-bar-context]")!.textContent).toContain("Pedido 1048 · Ana Souza");
    expect(document.querySelector("[data-operator-action-bar-context]")!.textContent).toContain("R$ 48,70");
    const action = document.querySelector<HTMLButtonElement>("[data-operator-action-bar-action]")!;
    expect(action.textContent?.trim()).toBe("Pronto para retirar");
    action.click();
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(document.querySelector("[data-operator-action-bar-secondary]")).toBeNull();
  });

  it("os ganchos data-* da ação chegam ao botão (e só eles)", async () => {
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: {
        action: { label: "Despachar M09", "data-orders-dispatch": "M09" },
        secondary: { label: "Voltar", "data-orders-back": "" },
      },
    });
    const action = document.querySelector<HTMLElement>("[data-operator-action-bar-action]")!;
    expect(action.getAttribute("data-orders-dispatch")).toBe("M09");
    expect(action.hasAttribute("label")).toBe(false);
    expect(document.querySelector("[data-operator-action-bar-secondary]")!.hasAttribute("data-orders-back")).toBe(true);
  });

  it("quando não pode, diz por quê, e o toque não age", async () => {
    const onSelect = vi.fn();
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: {
        action: {
          label: "Iniciar preparo",
          disabled: true,
          reason: "O Pix ainda não caiu.",
          onSelect,
        },
      },
    });
    const action = document.querySelector<HTMLButtonElement>("[data-operator-action-bar-action]")!;
    const reason = document.querySelector<HTMLElement>("[data-operator-action-bar-reason]")!;
    expect(reason.textContent?.trim()).toBe("O Pix ainda não caiu.");
    expect(reason.getAttribute("role")).toBe("status");
    expect(action.getAttribute("aria-describedby")).toBe(reason.id);
    action.click();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("a principal é o dourado sem anel (solid canônico); a segunda é contorno, não ghost", async () => {
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: { action: { label: "Aceitar" }, secondary: { label: "Limpar" } },
    });
    const action = document.querySelector<HTMLElement>("[data-operator-action-bar-action]")!;
    const secondary = document.querySelector<HTMLElement>("[data-operator-action-bar-secondary]")!;
    expect(action.className).toContain("bg-primary");
    expect(action.className).not.toMatch(/(?:^|\s)ring-/);
    expect(secondary.className).toContain("ring-(--ui-text-inverted)");
    expect(secondary.className).toContain("text-inverted");
    expect(secondary.className).not.toMatch(/(?:^|\s)bg-default(?:\s|$)/);
  });

  it("a segunda ação é outline, de peso menor", async () => {
    const reject = vi.fn();
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: {
        action: { label: "Aceitar" },
        secondary: { label: "Recusar", onSelect: reject },
      },
    });
    const secondary = document.querySelector<HTMLButtonElement>("[data-operator-action-bar-secondary]")!;
    expect(secondary.textContent?.trim()).toBe("Recusar");
    secondary.click();
    expect(reject).toHaveBeenCalledTimes(1);
  });
});

// As classes que a peça acrescenta ao botão com prazo (a camada atrás do rótulo). Tudo
// o mais é o botão de origem, classe por classe.
const TIMED_EXTRA = new Set(["relative", "isolate", "overflow-hidden", "tabular-nums"]);
const tokens = (el: Element) => new Set(el.className.split(/\s+/).filter(Boolean));

describe("OperatorActionBar com prazo: a barra não muda, só o texto do botão (dono, 09/10/2026)", () => {
  it("entrar no prazo mantém cartão, contexto, segunda ação e a aparência do botão", async () => {
    const T0 = Date.now();
    const done = vi.fn();
    const undo = vi.fn();
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: {
        action: { label: "Pronto 0131", icon: "i-lucide-check", onSelect: done },
        secondary: { label: "Bloquear" },
        contextLabel: "Pedido 0131 · Balcão",
        contextValue: "3 itens",
      },
    });
    const surface = document.querySelector("[data-operator-action-bar-surface]");
    const context = document.querySelector("[data-operator-action-bar-context]");
    const secondary = document.querySelector("[data-operator-action-bar-secondary]");
    const before = document.querySelector<HTMLElement>("[data-operator-action-bar-action]")!;
    const beforeTokens = tokens(before);

    await mounted.setProps({
      action: {
        label: "Desfazer 0131",
        icon: "i-lucide-undo-2",
        ariaLabel: "Desfazer o Pronto do pedido 0131",
        timed: { until: T0 + 5000, duration: 5000 },
        onSelect: undo,
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 0));

    // A mesma barra: os mesmos nós, o mesmo contexto, a mesma segunda ação.
    expect(document.querySelectorAll("[data-operator-action-bar]")).toHaveLength(1);
    expect(document.querySelector("[data-operator-action-bar-surface]")).toBe(surface);
    expect(document.querySelector("[data-operator-action-bar-context]")).toBe(context);
    expect(context!.textContent).toContain("Pedido 0131 · Balcão");
    expect(document.querySelector("[data-operator-action-bar-secondary]")).toBe(secondary);

    // O botão: mesma cor, variante e tamanho. Só o texto muda, e o fundo esvazia atrás.
    const after = document.querySelector<HTMLElement>("[data-operator-action-bar-action]")!;
    expect(after.hasAttribute("data-operator-action-bar-timed")).toBe(true);
    expect(after.textContent?.trim()).toBe("Desfazer 0131");
    expect(after.getAttribute("aria-label")).toBe("Desfazer o Pronto do pedido 0131");
    const afterTokens = tokens(after);
    for (const token of beforeTokens) expect(afterTokens, `classe ${token}`).toContain(token);
    for (const token of afterTokens) {
      if (!beforeTokens.has(token)) expect(TIMED_EXTRA, `classe nova ${token}`).toContain(token);
    }
    expect(after.querySelector("[data-timed-fill]")).not.toBeNull();

    after.click();
    expect(undo).toHaveBeenCalledTimes(1);
    expect(done).not.toHaveBeenCalled();
  });

  it("ao fim do prazo, o botão fica no lugar, desligado, e avisa uma vez", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ["Date", "setTimeout", "clearTimeout"] });
    try {
      const onExpire = vi.fn();
      const onSelect = vi.fn();
      mounted = await mountSuspended(OperatorActionBar, {
        attachTo: document.body,
        props: {
          action: {
            label: "Desfazer 0131",
            timed: { until: Date.now() + 5000, duration: 5000, onExpire },
            onSelect,
          },
        },
      });
      vi.advanceTimersByTime(5100);
      await mounted.vm.$nextTick();
      const action = document.querySelector<HTMLButtonElement>("[data-operator-action-bar-action]")!;
      expect(action).not.toBeNull();
      expect(action.disabled).toBe(true);
      expect(onExpire).toHaveBeenCalledTimes(1);
      action.click();
      expect(onSelect).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});
