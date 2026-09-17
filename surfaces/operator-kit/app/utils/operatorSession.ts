/**
 * Política comum das superfícies de operador para recusa do servidor num `useFetch`.
 *
 * NEM TODO 403 PEDE SENHA. Três recusas chegam com o mesmo status e querem coisas
 * opostas, e o backstage já as separa por CÓDIGO (`shopman/backstage/api/permissions.py`):
 *
 *   - **401**, ou 403 `not_authenticated` — a sessão do operador acabou no meio do
 *     turno. Entrar de novo resolve: marca `expired` e o shell sobe o login.
 *   - **403 `station_locked`** — a estação é reconhecida e ninguém está identificado
 *     (o balcão de manhã). O PIN ali mesmo resolve: levanta a bandeira do cadeado na
 *     hora, sem esperar o próximo poll, senão a tela segue desenhando um quadro vazio
 *     que o balcão lê como "as comandas sumiram".
 *   - **403 de permissão** — o operador está identificado e aquela ação não é dele.
 *     Senha NÃO resolve, e era exatamente o que esta função fazia: qualquer 403
 *     refazia a sessão e mandava para a tela de senha alguém que já estava logado.
 *
 * O `httpError.ts` deste mesmo diretório já dizia isto por escrito ("aceitar 'todo
 * 403' mandaria o operador digitar senha para uma recusa que senha não conserta") e
 * expunha os dois matchers tipados; quem não os usava era esta função, e ela é a que
 * está no `onResponseError` de todo board.
 *
 * O Marketing tem a sua (`marketing-nuxt/app/utils/marketingSession.ts`): a política é
 * a mesma, e ele acrescenta o que é só dele — guardar a decisão pendente (aprovar ou
 * rejeitar um anúncio, com chave de idempotência) antes de reautenticar.
 */
export type OperatorSessionRefusal = "expired" | "locked" | null;

/**
 * Classifica a recusa, levanta a bandeira correspondente e devolve QUAL foi — para
 * quem precisa reagir ao ramo, e não só ao efeito. O Marketing é o caso: na sessão
 * expirada ele guarda a decisão pendente antes de reautenticar.
 *
 * Devolve `null` quando a recusa não é de sessão (permissão negada, 500, rede): nada
 * é reaberto e a tela mostra a mensagem do servidor.
 */
export function flagOperatorSessionRefusal(error: unknown): OperatorSessionRefusal {
  if (useOperatorSession().flagIfUnauthenticated(error)) return "expired";
  if (useStationLock().flagIfStationLocked(error)) return "locked";
  return null;
}

export function operatorSessionOnError(ctx: {
  response: { status: number; _data?: unknown };
}): void {
  // O código que separa as três recusas vive no CORPO da resposta, não no status:
  // sem `_data` os matchers não têm o que ler.
  if (flagOperatorSessionRefusal({ status: ctx.response.status, data: ctx.response._data })) {
    void refreshNuxtData("operator-session");
  }
}
