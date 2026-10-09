import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { h, nextTick } from "vue";

import OperatorMoreMenu from "../../app/components/OperatorMoreMenu.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

async function openMenu() {
  const trigger = document.querySelector<HTMLElement>("[data-operator-more-menu]")!;
  trigger.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
  trigger.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await nextTick();
}

const menuItems = () => [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')];

describe("OperatorMoreMenu, o ⋯ único", () => {
  it("o botão é um só: reticências, ghost, quadrado, com o nome do que guarda", async () => {
    mounted = await mountSuspended(OperatorMoreMenu, {
      attachTo: document.body,
      props: { items: [{ label: "Atualizar" }], label: "Mais ações do pedido 1048" },
      attrs: { "data-card-menu": "", class: "-my-1" },
    });
    const trigger = document.querySelector<HTMLElement>("[data-operator-more-menu]")!;
    expect(trigger.tagName).toBe("BUTTON");
    expect(trigger.getAttribute("aria-label")).toBe("Mais ações do pedido 1048");
    expect(trigger.getAttribute("title")).toBe("Mais ações do pedido 1048");
    // Os atributos de quem usa chegam ao botão.
    expect(trigger.hasAttribute("data-card-menu")).toBe(true);
    expect(trigger.className).toContain("-my-1");
  });

  it("abre os grupos, chama a ação e escreve o motivo da que não pode", async () => {
    const onSelect = vi.fn();
    mounted = await mountSuspended(OperatorMoreMenu, {
      attachTo: document.body,
      props: {
        label: "Mais ações",
        items: [
          [
            { label: "Atender este pedido", icon: "i-lucide-user-plus", onSelect },
            { label: "Voltar para a Cozinha", disabled: true, reason: "A Cozinha já fechou o pedido 1048." },
          ],
          [{ label: "Cancelar pedido", color: "error" }],
        ],
      },
    });
    await openMenu();
    const labels = menuItems().map((node) => node.textContent?.trim());
    expect(labels).toEqual([
      "Atender este pedido",
      "Voltar para a CozinhaA Cozinha já fechou o pedido 1048.",
      "Cancelar pedido",
    ]);
    expect(menuItems()[1]!.hasAttribute("data-disabled")).toBe(true);
    menuItems()[0]!.click();
    await nextTick();
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("texto da casa não se corta: rótulo e motivo quebram linha", async () => {
    mounted = await mountSuspended(OperatorMoreMenu, {
      attachTo: document.body,
      props: {
        items: [{ label: "Pausar em todos os canais", disabled: true, reason: "Sem canal ativo." }],
      },
    });
    await openMenu();
    const label = document.querySelector<HTMLElement>('[data-slot="itemLabel"]')!;
    const description = document.querySelector<HTMLElement>('[data-slot="itemDescription"]')!;
    for (const node of [label, description]) {
      expect(node.className).toContain("whitespace-normal");
      expect(node.className).not.toMatch(/\btruncate\b/);
    }
  });

  it("os slots de item passam direto (a leitura dentro do ⋯ da fila)", async () => {
    mounted = await mountSuspended(OperatorMoreMenu, {
      attachTo: document.body,
      props: { items: [[{ type: "label", slot: "freshness", label: "Leitura" }], [{ label: "Atualizar" }]] },
      slots: { freshness: () => h("span", { "data-test-freshness": "" }, "Lido às 10:42") },
    });
    await openMenu();
    expect(document.querySelector("[data-test-freshness]")?.textContent).toBe("Lido às 10:42");
  });
});
