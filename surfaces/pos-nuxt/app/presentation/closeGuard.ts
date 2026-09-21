/**
 * O aviso da trava contra cobrança duplicada — o que a faixa vermelha no topo
 * do PDV diz, e se ela aparece.
 *
 * A trava (`usePosSale`) grava um marcador no navegador ANTES de pedir o
 * fechamento ao servidor e o apaga quando a resposta prova que o pedido
 * nasceu. Enquanto ESTA aba espera essa resposta, o marcador existe e a venda
 * está correndo normalmente: isso não é aviso, é o botão "Finalizando…". Antes
 * a faixa acendia em toda venda, durante o POST, com o título "Cobrança em
 * processamento ou interrompida" e um botão para liberar — alarme falso no
 * caminho feliz, e um convite a liberar a trava no meio da própria cobrança.
 *
 * Os estados em que a faixa tem algo verdadeiro a dizer são quatro, e cada um
 * diz o que houve e o que fazer — nunca "processamento OU interrompida", que
 * obriga o operador a adivinhar qual das duas.
 */

export type CloseGuardSituation =
  /** Nada a avisar: sem marcador, ou a cobrança em voo é desta aba. */
  | "none"
  /** Outra aba deste navegador segura a trava agora: está cobrando. */
  | "other_tab_charging"
  /** Marcador "em andamento" sem ninguém segurando a trava: a aba que
   *  cobrava fechou ou recarregou antes da resposta. */
  | "interrupted"
  /** O servidor respondeu sem provar o pedido, ou a rede caiu no meio. */
  | "uncertain"
  /** O navegador não consegue gravar/ler a trava ou coordenar abas. */
  | "browser_unavailable";

export interface CloseGuardInput {
  /** Há trava ativa (marcador gravado ou falha do navegador). */
  blocked: boolean;
  /** A cobrança em voo pertence a ESTA aba (ela segura a trava agora). */
  inFlightHere: boolean;
  /** O marcador está em "pending" (cobrança iniciada, sem resposta gravada). */
  pending: boolean;
  /** Outra aba segura a trava neste instante. */
  heldElsewhere: boolean;
  /** Mensagem de falha do próprio navegador (storage/locks), se houver. */
  browserFailure: string;
}

export interface CloseGuardNotice {
  situation: Exclude<CloseGuardSituation, "none">;
  title: string;
  body: string;
  /** Liberar só faz sentido quando ninguém está cobrando agora. */
  canRelease: boolean;
}

export function closeGuardSituation(input: CloseGuardInput): CloseGuardSituation {
  if (!input.blocked || input.inFlightHere) return "none";
  if (input.heldElsewhere) return "other_tab_charging";
  if (input.browserFailure) return "browser_unavailable";
  if (input.pending) return "interrupted";
  return "uncertain";
}

export function closeGuardNotice(input: CloseGuardInput): CloseGuardNotice | null {
  const situation = closeGuardSituation(input);
  switch (situation) {
    case "none":
      return null;
    case "other_tab_charging":
      return {
        situation,
        title: "Outra aba deste PDV está finalizando uma venda",
        body: "Aguarde o resultado naquela aba. Esta aba volta a cobrar sozinha quando aquela venda terminar.",
        canRelease: false,
      };
    case "interrupted":
      return {
        situation,
        title: "A última venda foi interrompida antes da resposta",
        body: "A página fechou ou recarregou enquanto a venda era finalizada, e não sabemos se o pedido e o pagamento foram criados. Confira em Últimas vendas antes de cobrar de novo.",
        canRelease: true,
      };
    case "uncertain":
      return {
        situation,
        title: "Resultado da cobrança não confirmado",
        body: "Antes de cobrar novamente, confira em Últimas vendas ou no Gestor se o pedido e o pagamento foram criados. Este bloqueio permanece mesmo se a página for recarregada.",
        canRelease: true,
      };
    case "browser_unavailable":
      return {
        situation,
        title: "Cobrança bloqueada neste navegador",
        body: input.browserFailure,
        canRelease: true,
      };
  }
}
