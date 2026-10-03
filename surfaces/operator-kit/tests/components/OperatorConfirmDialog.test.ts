import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DialogContent, DialogPortal, DialogRoot, DialogTitle } from "reka-ui";
import { defineComponent, h, nextTick } from "vue";

import OperatorConfirmDialog from "../../app/components/OperatorConfirmDialog.vue";
import { answerConfirm, useConfirm } from "../../app/composables/useConfirm";

// A pergunta antes de descartar, testada na fonte: o reka-ui de verdade (sem stub),
// porque o contrato é justamente o que o AlertDialog faz com Esc, foco e toque fora.

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
const mount = async () => (mounted = await mountSuspended(OperatorConfirmDialog, { attachTo: document.body }));
const settle = async () => {
  await nextTick();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await nextTick();
};
const box = () => document.body.querySelector<HTMLElement>("[data-operator-confirm]");

afterEach(() => {
  answerConfirm(false);
  mounted?.unmount();
  mounted = null;
});

const PRICE = {
  title: "Descartar o preço digitado?",
  description: "O novo preço não foi salvo. O produto continua com o preço atual.",
};

describe("useConfirm + OperatorConfirmDialog", () => {
  it("abre a caixa da casa com a pergunta, o que se perde e os dois atos; nunca a do navegador", async () => {
    const prior = window.confirm;
    const native = vi.fn(() => true);
    window.confirm = native;
    await mount();
    expect(box()).toBeNull();
    void useConfirm()(PRICE);
    await settle();
    expect(box()?.getAttribute("role")).toBe("alertdialog");
    expect(box()?.textContent).toContain("Descartar o preço digitado?");
    expect(box()?.textContent).toContain("O produto continua com o preço atual.");
    expect(box()?.querySelector("[data-operator-confirm-keep]")?.textContent?.trim()).toBe("Continuar editando");
    expect(box()?.querySelector("[data-operator-confirm-discard]")?.textContent?.trim()).toBe("Descartar");
    expect(native).not.toHaveBeenCalled();
    window.confirm = prior;
  });

  it("Descartar responde true e fecha", async () => {
    await mount();
    const answer = useConfirm()({ ...PRICE, confirmLabel: "Descartar e sair" });
    await settle();
    const discard = box()!.querySelector<HTMLButtonElement>("[data-operator-confirm-discard]")!;
    expect(discard.textContent?.trim()).toBe("Descartar e sair");
    discard.click();
    await expect(answer).resolves.toBe(true);
    await settle();
    expect(box()).toBeNull();
  });

  it("Continuar editando responde false (e é o foco inicial: Enter por reflexo não perde nada)", async () => {
    await mount();
    const answer = useConfirm()({ ...PRICE, cancelLabel: "Continuar escrevendo" });
    await settle();
    const keep = box()!.querySelector<HTMLButtonElement>("[data-operator-confirm-keep]")!;
    expect(keep.textContent?.trim()).toBe("Continuar escrevendo");
    expect(document.activeElement).toBe(keep);
    keep.click();
    await expect(answer).resolves.toBe(false);
  });

  it("Esc responde false", async () => {
    await mount();
    const answer = useConfirm()(PRICE);
    await settle();
    box()!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await expect(answer).resolves.toBe(false);
  });

  it("aberta sobre um diálogo do app, é a camada de cima: o toque e o Esc nela não fecham o de baixo", async () => {
    const outerClosed = vi.fn();
    const Host = defineComponent({
      setup() {
        return () => [
          h(DialogRoot, { open: true, "onUpdate:open": (value: boolean) => { if (!value) outerClosed(); } }, () =>
            h(DialogPortal, () => h(DialogContent, { "data-outer": "" }, () => [h(DialogTitle, () => "Recusar pedido"), "motivo"]))),
          h(OperatorConfirmDialog),
        ];
      },
    });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    await settle();
    const answer = useConfirm()(PRICE);
    await settle();
    const keep = box()!.querySelector<HTMLButtonElement>("[data-operator-confirm-keep]")!;
    keep.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    box()!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await expect(answer).resolves.toBe(false);
    await settle();
    expect(outerClosed).not.toHaveBeenCalled();
    expect(document.body.querySelector("[data-outer]")).not.toBeNull();
  });

  it("uma pergunta por vez: a segunda responde false sem abrir outra caixa", async () => {
    await mount();
    const first = useConfirm()(PRICE);
    await settle();
    await expect(useConfirm()({ title: "Outra?", description: "Outra coisa." })).resolves.toBe(false);
    await settle();
    expect(document.body.querySelectorAll("[data-operator-confirm]")).toHaveLength(1);
    expect(box()?.textContent).toContain("Descartar o preço digitado?");
    box()!.querySelector<HTMLButtonElement>("[data-operator-confirm-discard]")!.click();
    await expect(first).resolves.toBe(true);
  });
});
