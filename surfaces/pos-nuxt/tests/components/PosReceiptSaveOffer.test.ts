// A PERGUNTA junto do campo — a metade que a regra pura não alcança.
//
// Prova-se aqui o que o dono pediu como "um tipo de tooltip bem elegante" e que
// tooltip não pode ser: abre ao DIGITAR (não por hover, porque o balcão é tela
// de toque), não rouba o foco do campo (quem digita rápido não pode perder a
// próxima tecla), sai por portal (não empurra o layout nem é recortado pelo
// `overflow-x-auto` da coluna) e deixa a linha de desmarcar SEMPRE à vista.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";

import PosReceiptSaveOffer from "~/components/PosReceiptSaveOffer.vue";
import { receiptContactOffer } from "~/presentation/receiptContact";

const MUDA = receiptContactOffer({
  field: "email",
  typed: "ana@example.org",
  customer: { name: "Ana Prado", email: "ana@example.org" },
});
const SALVAR = receiptContactOffer({
  field: "email",
  typed: "ana@example.org",
  customer: { name: "Ana Prado" },
});
const ANONIMA = receiptContactOffer({ field: "email", typed: "novo@example.org", customer: null });

function popover(): HTMLElement | null {
  return document.querySelector('[role="dialog"]');
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("PosReceiptSaveOffer", () => {
  it("oferta muda não desenha nada — nem popover, nem linha", async () => {
    const wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: MUDA, checked: false },
    });

    expect(popover()).toBeNull();
    expect(wrapper.find("label").exists()).toBe(false);
  });

  it("abre ao DIGITAR: com valor perguntável, o popover já está aberto", async () => {
    await mountSuspended(PosReceiptSaveOffer, { props: { offer: SALVAR, checked: false } });

    const panel = popover();
    expect(panel).not.toBeNull();
    expect(panel!.textContent).toContain("Salvar este e-mail no cadastro de Ana?");
    // Nenhum hover envolvido: o painel existe porque o valor ficou perguntável.
    expect(panel!.textContent).toContain("que hoje não tem e-mail");
  });

  it("não rouba o foco do campo: o input segue com o foco depois de abrir", async () => {
    const wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: SALVAR, checked: false },
      slots: { default: () => h("input", { "aria-label": "E-mail que recebe a nota" }) },
      attachTo: document.body,
    });

    const input = wrapper.find("input").element as HTMLInputElement;
    input.focus();
    await nextTick();

    expect(popover()).not.toBeNull();
    expect(document.activeElement).toBe(input);
  });

  it("sai por PORTAL — fora da árvore do campo, para não empurrar nem ser recortado", async () => {
    const wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: SALVAR, checked: false },
    });

    expect(popover()).not.toBeNull();
    expect(wrapper.element.contains(popover())).toBe(false);
  });

  it("confirmar manda salvar e a pergunta se aquieta", async () => {
    const wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: SALVAR, checked: false },
    });

    const button = [...document.querySelectorAll("button")].find(
      (b) => b.textContent?.includes("Salvar no cadastro"),
    );
    button!.click();
    await nextTick();
    await nextTick();

    expect(wrapper.emitted("update:checked")?.[0]).toEqual([true]);
    // A pergunta se aquieta: respondida, ela não volta a abrir pelo mesmo valor.
    expect(popover()?.dataset.state).not.toBe("open");
  });

  it("dispensar manda NÃO salvar", async () => {
    const wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: ANONIMA, checked: true },
    });

    const button = [...document.querySelectorAll("button")].find(
      (b) => b.textContent?.includes("Não salvar"),
    );
    button!.click();
    await nextTick();

    expect(wrapper.emitted("update:checked")?.[0]).toEqual([false]);
  });

  it("o LADO do balão é escolhido por quem sabe o que ele tapa", async () => {
    // Na coluna do fechamento `bottom` cobria o Validar e as perguntas
    // seguintes; a coluna encosta na borda e o miolo ao lado está vazio.
    await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: SALVAR, checked: false, side: "left" },
    });

    expect(popover()!.getAttribute("data-side")).toBe("left");
  });

  it("QUIET cala o balão e mantém a linha — o modal por cima o tornaria fantasma", async () => {
    // Com o modal do cliente aberto, o balão da coluna abriria atrás do
    // overlay: pergunta sem ninguém para respondê-la, que é pior que nenhuma.
    const wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: ANONIMA, checked: true, quiet: true },
    });

    expect(popover()).toBeNull();
    expect(wrapper.find('[role="switch"]').exists()).toBe(true);
  });

  it("a linha de desmarcar fica À VISTA — nunca atrás de um avançado", async () => {
    // É o que segura a promessa do "já marcado" da venda anônima: o padrão é
    // do dono, a visibilidade é a contrapartida.
    const wrapper = await mountSuspended(PosReceiptSaveOffer, {
      props: { offer: ANONIMA, checked: true },
    });

    const toggle = wrapper.find('[role="switch"]');
    expect(toggle.exists()).toBe(true);
    expect(toggle.attributes("aria-checked")).toBe("true");
    expect(wrapper.find("label").text()).toContain("Salvar como cliente?");

    await toggle.trigger("click");
    expect(wrapper.emitted("update:checked")?.[0]).toEqual([false]);
  });
});
