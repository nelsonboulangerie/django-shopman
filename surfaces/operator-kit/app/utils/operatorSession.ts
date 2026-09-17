// Política comum das superfícies de operador: ao expirar a sessão do operador no meio
// do turno, o poll passa a 401/403. Reabre o gate re-buscando a sessão
// (refreshNuxtData) em vez de deixar "reconectando…" para sempre. Um só dono — os
// useFetch dos boards apontam para cá em vez de copiar o bloco.
//
// O Marketing NÃO usa esta função: a política dele distingue 401 de `station_locked`
// e guarda o intent de decisão pendente antes de reautenticar, e vive em
// `marketing-nuxt/app/utils/operatorSession.ts` como `marketingSessionOnError`.
export function operatorSessionOnError(ctx: { response: { status: number } }): void {
  if (ctx.response.status === 401 || ctx.response.status === 403) {
    refreshNuxtData("operator-session");
  }
}
