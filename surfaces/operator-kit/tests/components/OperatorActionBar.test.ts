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
    // O cartão flutua em superfície invertida (tema escuro só dentro dele).
    const surface = root.querySelector<HTMLElement>("[data-operator-action-bar-surface]")!;
    expect(surface.classList.contains("dark")).toBe(true);
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

  it("a segunda ação é outline, de peso menor", async () => {
    const reject = vi.fn();
    mounted = await mountSuspended(OperatorActionBar, {
      attachTo: document.body,
      props: {
        action: { label: "Aceitar" },
        secondary: { label: "Recusar", color: "error", onSelect: reject },
      },
    });
    const secondary = document.querySelector<HTMLButtonElement>("[data-operator-action-bar-secondary]")!;
    expect(secondary.textContent?.trim()).toBe("Recusar");
    secondary.click();
    expect(reject).toHaveBeenCalledTimes(1);
  });
});
