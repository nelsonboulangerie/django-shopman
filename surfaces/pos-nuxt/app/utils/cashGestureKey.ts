// A chave de replay de um gesto de dinheiro do caixa (sangria, devolução,
// estorno, troco, acerto, abrir e fechar o turno).
//
// ⚠️ O GESTO é o que se identifica, não a requisição. A chave nascia de
// `caminho + JSON(corpo)`, e o corpo carrega a assinatura do gerente: a Fran pede
// a saída de R$ 50, o servidor recusa sem gerente, a Joyce assina, e o reenvio
// com `manager_approval` já era "outra" tentativa. Com a rede cortada depois de o
// servidor gravar, o toque seguinte (com outra assinatura, ou sem ela) ganhava
// chave nova, e o livro-caixa aceitava a segunda saída.
//
// O servidor já tira a aprovação da impressão digital do conteúdo
// (`_local_idempotent` em `shopman/backstage/api/operations.py`): a mesma chave
// com outra assinatura é o mesmo lançamento. Aqui vale a mesma régua, campo a
// campo: o que fica fora da assinatura do gesto é exatamente o que o servidor
// deixa fora da dele.
//
// A regra que torna a chave correta nos dois casos:
//
//   * a MESMA chave volta enquanto a tentativa anterior do MESMO gesto não teve
//     resposta de sucesso: é o retry depois do estouro de tempo, em que o
//     servidor pode já ter gravado e a resposta se perdeu;
//   * a chave é DESCARTADA no sucesso: duas saídas deliberadamente iguais nascem
//     com chaves diferentes e viram dois lançamentos, que é o certo.

/** Os campos do corpo que NÃO mudam o gesto (o servidor também os ignora). */
export const CASH_GESTURE_IGNORED_FIELDS = ["manager_approval", "client_request_id"] as const;

/** O que identifica o gesto: o caminho e o conteúdo, sem a assinatura do gerente. */
export function cashGestureSignature(path: string, body: Record<string, unknown>): string {
  const content: Record<string, unknown> = {};
  for (const field of Object.keys(body).sort()) {
    if ((CASH_GESTURE_IGNORED_FIELDS as readonly string[]).includes(field)) continue;
    content[field] = body[field];
  }
  return `${path}:${JSON.stringify(content)}`;
}

function randomKey(): string {
  const random =
    globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `pos-cash:${random}`;
}

/**
 * O guardião da chave de UMA tela de caixa: lembra a última tentativa sem
 * sucesso e devolve a mesma chave enquanto o gesto for o mesmo.
 */
export function createCashGestureKeys(generate: () => string = randomKey) {
  let lastAttempt: { signature: string; key: string } | null = null;

  return {
    /** A chave do gesto: a mesma da tentativa anterior sem sucesso, ou uma nova. */
    keyFor(path: string, body: Record<string, unknown>): string {
      const signature = cashGestureSignature(path, body);
      if (lastAttempt?.signature === signature) return lastAttempt.key;
      lastAttempt = { signature, key: generate() };
      return lastAttempt.key;
    },
    /** O servidor aceitou: o próximo gesto igual é outro lançamento. */
    settled(): void {
      lastAttempt = null;
    },
  };
}
