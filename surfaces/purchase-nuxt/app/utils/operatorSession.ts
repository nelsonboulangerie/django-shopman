// Sessão do operador expirada ou gate sem permissão: revalida o estado compartilhado
// para a UI abrir o fluxo correto, sem manter a tela presa em erro técnico.
export function operatorSessionOnError(ctx: { response: { status: number } }): void {
  if (ctx.response.status === 401 || ctx.response.status === 403) {
    refreshNuxtData("operator-session");
  }
}
