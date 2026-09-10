/**
 * Dinheiro na tela do operador — uma implementação, todas as superfícies.
 *
 * Formatar centavos em BRL é invariante entre PDV, Gestor, Compras e caixa: é o
 * mesmo `Intl.NumberFormat("pt-BR")` sobre o mesmo inteiro em centavos (`_q`, a
 * convenção da casa). Morava só no `posIntent.ts` do PDV, e foi o que travou a
 * mudança do diálogo de autorização do gerente para este layer — a peça
 * compartilhada dependia de um util de um app.
 *
 * ⚠️ O argumento é SEMPRE centavos (inteiro), nunca reais. Passar `15.5` aqui
 * imprime R$ 0,16 — o erro de 100× que já apareceu duas vezes nas superfícies.
 */
export function formatBRL(amountQ: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format((Number.isFinite(amountQ) ? amountQ : 0) / 100);
}
