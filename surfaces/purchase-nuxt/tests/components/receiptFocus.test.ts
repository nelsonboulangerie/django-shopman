// "Ir até lá" — o caminho que liga a pendência ao campo.
//
// Com o formulário dentro da gaveta, o campo deixou de morar embaixo da linha
// da lista: ele nasce num portal, no fim do `<body>`, alguns quadros DEPOIS do
// clique. Procurar no mesmo gesto devolve `null`, e o operador que clica na
// pendência vê a tela não fazer nada. É a regressão que estes testes guardam.
import { afterEach, describe, expect, it } from "vitest";

import { receiptFieldSelector, waitForElement } from "../../app/utils/receiptFocus";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("receiptFieldSelector — o endereço do campo dentro da gaveta", () => {
  it("procura o campo DENTRO da gaveta do item, e não embaixo da linha da lista", () => {
    expect(receiptFieldSelector("line-7", "expiry")).toBe(
      '[data-receipt-sheet="line-7"] [data-receipt-field="expiry"]',
    );
  });

  it("sem campo, o alvo é a própria gaveta", () => {
    expect(receiptFieldSelector("line-7", null)).toBe('[data-receipt-sheet="line-7"]');
  });
});

describe("waitForElement — a gaveta monta depois do quadro", () => {
  it("acha o campo que já está na tela", async () => {
    document.body.innerHTML = '<div data-receipt-sheet="line-1"><input data-receipt-field="expiry" /></div>';

    const found = await waitForElement(receiptFieldSelector("line-1", "expiry"));

    expect(found).not.toBeNull();
    expect(found!.getAttribute("data-receipt-field")).toBe("expiry");
  });

  it("ESPERA o campo que ainda vai aparecer — era aqui que o clique morria", async () => {
    // O portal escreve no documento DEPOIS do clique. Um quadro basta para
    // provar o ponto: a busca sincrona do gesto acha `null`.
    setTimeout(() => {
      document.body.innerHTML = '<div data-receipt-sheet="line-2"><input data-receipt-field="material" /></div>';
    }, 0);
    expect(document.querySelector(receiptFieldSelector("line-2", "material"))).toBeNull();

    const found = await waitForElement(receiptFieldSelector("line-2", "material"));

    expect(found).not.toBeNull();
  });

  it("desiste quando o campo não existe, em vez de prender a tela", async () => {
    expect(await waitForElement(receiptFieldSelector("line-3", "qty"), 2)).toBeNull();
  });
});
