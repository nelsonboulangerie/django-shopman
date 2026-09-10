import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import { workspaceProps } from "../support/paymentWorkspaceProps";

/**
 * No modal "Dividir conta", o NÚMERO do botão é a própria tecla: "3" escolhe
 * três pessoas e fecha, como o toque faria. O diálogo prende o foco em si e o
 * shell cala os atalhos globais enquanto ele está aberto, então a tecla não
 * tem outro dono — e as recusas são as mesmas do dedo (link lançado, nada a
 * desfazer).
 */
describe("PosPaymentWorkspace — no modal de dividir, o número é a tecla", () => {
  type Montado = Awaited<ReturnType<typeof mountSuspended>>;
  // O diálogo é teleportado para o `body`: quem responde "está aberto?" é o
  // documento, e o `afterEach` impede que um teste leia o modal do anterior.
  afterEach(() => { document.body.innerHTML = ""; });
  const exposto = (w: Montado) =>
    (w.vm as unknown as { $: { exposed: { openSplit: () => void } } }).$.exposed;
  // "Aberto" pela mesma régua do shell (`globalKeysBlocked`): o conteúdo do
  // reka-ui marca `data-state="open"`; fechado, ele ainda fica um instante no
  // DOM (presença/animação), então texto no `body` não basta.
  const dialogo = () => document.body.querySelector<HTMLElement>('[role="dialog"][data-state="open"]');
  const modalAberto = () => dialogo()?.textContent?.includes("Em quantas pessoas") ?? false;
  function tecla(key: string, init: KeyboardEventInit = {}) {
    dialogo()!.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init }));
  }
  async function abrir(w: Montado) {
    exposto(w).openSplit();
    await w.vm.$nextTick();
    expect(modalAberto()).toBe(true);
  }
  const comLink = {
    paymentMethods: [{ ref: "cash", label: "Dinheiro" }, { ref: "link", label: "Link de pagamento" }],
    paymentTenders: [{ method: "link", amount_q: 1000, collection: "terminal" as const }],
  };

  it("2 a 6 escolhem em quantas pessoas e fecham o modal", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps() });
    await abrir(w);
    tecla("3");
    await w.vm.$nextTick();
    expect(w.emitted("setSplitCount")).toEqual([[3]]);
    expect(modalAberto()).toBe(false);
  });

  it("dígito que não é preset não faz nada — o modal fica aberto", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps() });
    await abrir(w);
    for (const key of ["0", "7", "9", "a", "Enter"]) tecla(key);
    await w.vm.$nextTick();
    expect(w.emitted("setSplitCount")).toBeUndefined();
    expect(modalAberto()).toBe(true);
  });

  it("modificador não escolhe: Ctrl+3 e Alt+3 são do navegador", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps() });
    await abrir(w);
    tecla("3", { ctrlKey: true });
    tecla("3", { altKey: true });
    tecla("3", { metaKey: true });
    await w.vm.$nextTick();
    expect(w.emitted("setSplitCount")).toBeUndefined();
    expect(modalAberto()).toBe(true);
  });

  it("1 desfaz a divisão — uma pessoa é não dividir", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps({ splitCount: 3 }) });
    await abrir(w);
    tecla("1");
    await w.vm.$nextTick();
    expect(w.emitted("setSplitCount")).toEqual([[0]]);
    expect(modalAberto()).toBe(false);
  });

  it("1 sem divisão ativa não faz nada — não há o que desfazer", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps() });
    await abrir(w);
    tecla("1");
    await w.vm.$nextTick();
    expect(w.emitted("setSplitCount")).toBeUndefined();
    expect(modalAberto()).toBe(true);
  });

  it("com link lançado, a tecla recusa como o botão recusa — e só o desfazer responde", async () => {
    // O link cobra a venda inteira: os presets ficam desabilitados no modal
    // (que abre porque há divisão a desfazer). A tecla obedece à mesma verdade.
    const w = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps({ ...comLink, splitCount: 3 }) });
    await abrir(w);
    tecla("4");
    await w.vm.$nextTick();
    expect(w.emitted("setSplitCount")).toBeUndefined();
    expect(modalAberto()).toBe(true);
    tecla("1");
    await w.vm.$nextTick();
    expect(w.emitted("setSplitCount")).toEqual([[0]]);
  });

  it("o botão de desfazer mostra a própria tecla", async () => {
    const w = await mountSuspended(PosPaymentWorkspace, { props: workspaceProps({ splitCount: 3 }) });
    await abrir(w);
    const desfazer = Array.from(document.body.querySelectorAll("button")).find((b) => b.textContent?.includes("Não dividir"));
    expect(desfazer?.textContent?.replace(/\s+/g, " ").trim()).toBe("Não dividir 1");
  });
});
