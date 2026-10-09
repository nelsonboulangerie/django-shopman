// A ação na base no celular (`OperatorActionBar`, WP-FASE2-UX-OPERADOR K3).
//
// A ação é declarada como dados, no mesmo espírito do ⋯ único: rótulo com verbo e alvo
// ("Pronto para retirar", "Despachar M09"), nunca um "Confirmar" solto, e o motivo
// quando não pode.

import type { Instant } from "./timedAction";

/** O prazo de uma ação da base: o mesmo botão, no mesmo lugar, com o fundo que esvazia
 *  atrás do rótulo (`OperatorTimedButton`). O "Pronto 0131" tocado vira "Desfazer 0131"
 *  e nada mais muda na barra (dono, 09/10/2026). */
export interface OperatorActionBarTimed {
  /** Fim da janela (epoch em ms ou ISO). */
  until: Instant;
  /** Começo da janela (epoch em ms ou ISO). */
  since?: Instant;
  /** Tamanho da janela em ms, quando não há `since`. */
  duration?: number;
  /** O "agora" do servidor (ISO) que deu o prazo. */
  serverNow?: string;
  /** O prazo acabou (uma vez). A barra mantém o botão no lugar, desligado, até quem
   *  chama trocar a ação. */
  onExpire?: () => void;
}

export interface OperatorActionBarAction {
  /** Verbo e alvo: "Iniciar preparo", "Conferir o próximo". */
  label: string;
  icon?: string;
  to?: string;
  loading?: boolean;
  disabled?: boolean;
  /** Por que não pode agora (com `disabled`): aparece escrito sob a ação. */
  reason?: string;
  /** Nome para o leitor de tela, quando o rótulo visível é curto ("Desfazer 0131"). */
  ariaLabel?: string;
  /** A ação só vale até um prazo ("Desfazer"): mesmo botão, fundo que esvazia. */
  timed?: OperatorActionBarTimed;
  onSelect?: (event: Event) => void;
}
