// WP-G08, o diálogo "Resolver" da promessa em risco: o que a tela faz com a leitura do
// servidor (`GET orders/<ref>/promise-resolution/`). Nenhuma régua de estoque, de
// dinheiro ou de permissão mora na tela, e nenhuma frase do servidor é reescrita.
import { describe, expect, it } from "vitest";

import {
  CALL_ON_WHATSAPP_LABEL,
  CANCEL_HASH,
  COPY_MESSAGE_LABEL,
  MESSAGE_COPIED,
  PICK_FIRST_LABEL,
  WHAT_TO_DO_LABEL,
  choiceItems,
  concludeButton,
  messageHeading,
  needsManager,
  pickedChoice,
  removedSentence,
  resolutionTitle,
} from "../app/presentation/promiseResolution";
import {
  cancelChoice,
  closed,
  concludeOf,
  removeChoice,
  rescheduleChoice,
  resolution,
  swapChoice,
} from "./support/promiseResolution";

describe("os nomes fechados do diálogo", () => {
  it("são os que o dono fechou, sem travessão", () => {
    expect(WHAT_TO_DO_LABEL).toBe("O que fazer");
    expect(COPY_MESSAGE_LABEL).toBe("Copiar mensagem");
    expect(CALL_ON_WHATSAPP_LABEL).toBe("Chamar no WhatsApp");
    expect(MESSAGE_COPIED).toBe("Mensagem copiada.");
    expect(PICK_FIRST_LABEL).toBe("Escolha o que fazer");
    expect(CANCEL_HASH).toBe("#cancel");
  });

  it("o título é o do aviso de página: o estado e o pedido", () => {
    expect(resolutionTitle("N75")).toBe("Promessa em risco no pedido N75");
    expect(resolutionTitle("")).toBe("Promessa em risco");
  });

  it("a mensagem diz de quem é", () => {
    expect(messageHeading("Nelson Dias")).toBe("Mensagem para Nelson Dias");
    expect(messageHeading("  ")).toBe("Mensagem para o cliente");
  });
});

describe("choiceItems: uma escolha por linha, na ordem do servidor", () => {
  it("trocas primeiro, depois remarcar, tirar e cancelar, com o nome e o detalhe do servidor", () => {
    expect(choiceItems(resolution().choices).map((item) => [item.label, item.description])).toEqual([
      ["Trocar por Campagne Passas & Castanhas", "6 disponíveis hoje"],
      ["Remarcar para outro dia ou lote", undefined],
      ["Tirar só o item que falta e devolver a diferença", "R$ 44,00 serão estornados ao Pix do cliente."],
      ["Cancelar o pedido inteiro", "R$ 62,00 serão estornados ao Pix do cliente."],
    ]);
  });

  it("cada linha leva a chave e a família, para a tela achar", () => {
    expect(choiceItems(resolution().choices).map((item) => [item.value, item["data-resolve-choice-kind"]])).toEqual([
      ["swap:FOCACCIA-CBT:CAMPAGNE-PC", "swap"], ["reschedule", "reschedule"], ["remove", "remove"], ["cancel", "cancel"],
    ]);
  });

  it("escolha fechada continua na lista, não se marca e escreve o motivo no lugar do detalhe", () => {
    const items = choiceItems([
      closed(swapChoice(), "Pedido em preparo não pode ser editado."),
      closed(rescheduleChoice(), "Pedido em preparo não pode ser remarcado."),
      closed(removeChoice(), "É o único item do pedido: cancele o pedido."),
      cancelChoice(),
    ]);
    expect(items.map((item) => [item.disabled, item.description])).toEqual([
      [true, "Pedido em preparo não pode ser editado."],
      [true, "Pedido em preparo não pode ser remarcado."],
      [true, "É o único item do pedido: cancele o pedido."],
      [false, "R$ 62,00 serão estornados ao Pix do cliente."],
    ]);
  });

  it("sem sugestão do servidor, não há linha de troca: a tela não inventa escolha", () => {
    const items = choiceItems(resolution({ choices: [rescheduleChoice(), cancelChoice()] }).choices);
    expect(items.map((item) => item["data-resolve-choice-kind"])).toEqual(["reschedule", "cancel"]);
  });
});

describe("pickedChoice: quem decide é a pessoa", () => {
  it("nada vem marcado sozinho", () => {
    expect(pickedChoice(resolution(), "")).toBeNull();
    expect(pickedChoice(null, "remove")).toBeNull();
  });

  it("a escolha marcada é a da chave; a travada nunca conta", () => {
    expect(pickedChoice(resolution(), "reschedule")?.label).toBe("Remarcar para outro dia ou lote");
    const locked = resolution({ choices: [closed(removeChoice(), "x")] });
    expect(pickedChoice(locked, "remove")).toBeNull();
    expect(pickedChoice(resolution(), "nao-existe")).toBeNull();
  });
});

describe("concludeButton: o botão com o nome do que a escolha faz", () => {
  it("sem escolha fica travado e diz o que falta", () => {
    expect(concludeButton(null, false)).toMatchObject({ label: "Escolha o que fazer", disabled: true, href: "" });
  });

  it("trocar e remarcar levam ao PDV, com o endereço que o servidor mandou", () => {
    expect(concludeButton(swapChoice(), false)).toMatchObject({
      label: "Trocar no PDV", color: "primary", disabled: false,
      href: "https://pdv.example.test/preorders/WEB-2611-G8G-N75?swap=FOCACCIA-CBT",
    });
    expect(concludeButton(rescheduleChoice(), false)).toMatchObject({
      label: "Remarcar no PDV", href: "https://pdv.example.test/preorders/WEB-2611-G8G-N75",
    });
  });

  it("tirar o item grava daqui: não é link, e espera enquanto grava", () => {
    expect(concludeButton(removeChoice(), false)).toMatchObject({ label: "Tirar o item", color: "primary", href: "", disabled: false });
    expect(concludeButton(removeChoice(), true).disabled).toBe(true);
  });

  it("cancelar é vermelho, como no menu do pedido, e não é link", () => {
    expect(concludeButton(cancelChoice(), false)).toMatchObject({ label: "Cancelar pedido", color: "error", href: "" });
  });

  it("atalho sem endereço não é botão que se toca", () => {
    const broken = rescheduleChoice({ conclude: concludeOf({ kind: "link", label: "Remarcar no PDV" }) });
    expect(concludeButton(broken, false)).toMatchObject({ disabled: true, href: "" });
  });
});

describe("o gerente e a frase do que foi feito", () => {
  it("só a edição grava daqui: é ela que pode pedir gerente", () => {
    expect(needsManager(removeChoice())).toBe(true);
    expect(needsManager(removeChoice({ requires_manager_approval: false }))).toBe(false);
    // Cancelar pedido pago vem marcado, mas quem pede o gerente é o diálogo de cancelar.
    expect(cancelChoice().requires_manager_approval).toBe(true);
    expect(needsManager(cancelChoice())).toBe(false);
    expect(needsManager(null)).toBe(false);
  });

  it("depois de tirar o item: o que foi feito e a frase do dinheiro do servidor", () => {
    expect(removedSentence(removeChoice())).toBe("O que faltava saiu do pedido. R$ 44,00 serão estornados ao Pix do cliente.");
    expect(removedSentence(removeChoice({ detail: "" }))).toBe("O que faltava saiu do pedido.");
  });
});
