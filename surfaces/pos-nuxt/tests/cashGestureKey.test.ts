import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { cashGestureSignature, createCashGestureKeys } from "../app/utils/cashGestureKey";

// P1-5 do plano de excelência do PDV (WP-E6): repetir um gesto de caixa depois da
// rede cortada, com a assinatura do gerente mudada, gravava duas vezes. A chave
// do gesto ignora a aprovação, como o servidor já ignora na impressão digital.

function counter() {
  let n = 0;
  return () => `pos-cash:k${++n}`;
}

const MOVEMENT = "/api/v1/backstage/pos/cash/movement/";
const saida = { kind: "sangria", amount: "50,00", reason: "Depósito" };

describe("chave do gesto de caixa", () => {
  it("o reenvio com o PIN do gerente usa a MESMA chave da tentativa sem gerente", () => {
    const keys = createCashGestureKeys(counter());
    const first = keys.keyFor(MOVEMENT, saida);
    const signed = keys.keyFor(MOVEMENT, { ...saida, manager_approval: { username: "joyce", pin: "1234" } });
    expect(signed).toBe(first);
  });

  it("rede cortada depois da assinatura: repetir com outra assinatura, ou sem ela, é o mesmo lançamento", () => {
    const keys = createCashGestureKeys(counter());
    const signedByJoyce = keys.keyFor(MOVEMENT, { ...saida, manager_approval: { username: "joyce", pin: "1234" } });
    // A resposta se perdeu: nada de `settled()`. O toque seguinte vem com o crachá.
    const byBadge = keys.keyFor(MOVEMENT, { ...saida, manager_approval: { badge: "tok" } });
    const bare = keys.keyFor(MOVEMENT, saida);
    expect(byBadge).toBe(signedByJoyce);
    expect(bare).toBe(signedByJoyce);
  });

  it("outro valor, outro motivo ou outro caminho é outro gesto", () => {
    const keys = createCashGestureKeys(counter());
    const first = keys.keyFor(MOVEMENT, saida);
    expect(keys.keyFor(MOVEMENT, { ...saida, amount: "500,00" })).not.toBe(first);
    const other = keys.keyFor("/api/v1/backstage/pos/cash/close/", saida);
    expect(other).not.toBe(first);
  });

  it("depois do sucesso, a mesma saída de novo é OUTRO lançamento", () => {
    const keys = createCashGestureKeys(counter());
    const first = keys.keyFor(MOVEMENT, saida);
    keys.settled();
    expect(keys.keyFor(MOVEMENT, saida)).not.toBe(first);
  });

  it("a ordem dos campos não muda o gesto, e a chave anterior nunca entra na assinatura", () => {
    expect(cashGestureSignature(MOVEMENT, { reason: "Depósito", amount: "50,00", kind: "sangria" })).toBe(
      cashGestureSignature(MOVEMENT, { ...saida, client_request_id: "pos-cash:velha" }),
    );
  });

  it("o caixa usa esta régua (e não mais caminho + JSON do corpo inteiro)", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(resolve(here, "../app/composables/usePosCashSession.ts"), "utf8");
    expect(source).toContain("createCashGestureKeys()");
    expect(source).not.toMatch(/JSON\.stringify\(body\)/);
  });
});
