// O estado da tela, um só na suíte (WP-FASE2-UX-OPERADOR, A13 e peça K7), e o aviso da
// tela no cabeçalho (A12, K6).
//
// Uma redação por estado: quem monta a tela diz O QUE carrega ("a fila", "os lotes do
// período") e a peça escreve a frase inteira, igual em todo app. O tom é o do dono
// (09/10/2026): erro "Não foi possível carregar a fila"; vazio dito pela tela, no
// presente e sobre a pessoa ("Nenhum pedido precisa de você agora."). Antes havia o
// `BiPageState` no B.I., `NuxtAlert` solto em outras telas, faixas à mão no Marketing e
// no Compras, e o carregando ora `naked`, ora não.
//
// Funções puras: o componente só desenha o que elas decidem.

export type OperatorScreenStateKind = "loading" | "empty" | "error" | "offline";

export interface OperatorScreenStateCopy {
  title: string;
  description: string;
}

/**
 * A frase de cada estado. `what` é o que a tela mostra, com artigo ("a fila", "os lotes
 * do período"); `since` é a hora da última leitura que está na tela ("10:42").
 */
export function screenStateCopy(
  kind: OperatorScreenStateKind,
  options: { what?: string; since?: string } = {},
): OperatorScreenStateCopy {
  const what = options.what?.trim() || "";
  switch (kind) {
    case "loading":
      return { title: what ? `Carregando ${what}` : "Carregando", description: "" };
    case "empty":
      return { title: "Nada para mostrar agora.", description: "" };
    case "error":
      return {
        title: what ? `Não foi possível carregar ${what}` : "Não foi possível carregar esta tela",
        description: "",
      };
    case "offline":
      return {
        title: "Sem conexão.",
        description: options.since
          ? `O que está na tela é de ${options.since}.`
          : "O que está na tela pode estar desatualizado.",
      };
  }
}

/** O rótulo do botão de recuperar o erro, o mesmo em todo app. */
export const SCREEN_STATE_RETRY_LABEL = "Tentar de novo";

/** Um aviso da tela (`alerts` do `OperatorPageHeader`). */
export interface OperatorScreenAlert {
  /** Identidade estável (para o Vue não remontar o aviso). Padrão: o título. */
  id?: string;
  title: string;
  description?: string;
  /** O conjunto mínimo do aviso: `info`, `success`, `warning`, `error`. */
  color: "info" | "success" | "warning" | "error";
  icon?: string;
  /** A saída do aviso, na cor dele (exceção declarada do conjunto mínimo). */
  action?: { label: string; to?: string; onSelect?: (event: Event) => void };
}

/** Quantos avisos aparecem inteiros; o resto fica em "e mais N". */
export const SCREEN_ALERTS_VISIBLE = 1;

/** "e mais 1 aviso", "e mais 3 avisos". */
export function moreAlertsLabel(hidden: number): string {
  return hidden === 1 ? "e mais 1 aviso" : `e mais ${hidden} avisos`;
}

/** O ícone do aviso pela cor, quando a tela não escolhe um. */
export function screenAlertIcon(color: OperatorScreenAlert["color"]): string {
  switch (color) {
    case "error":
      return "i-lucide-circle-alert";
    case "warning":
      return "i-lucide-triangle-alert";
    case "success":
      return "i-lucide-circle-check";
    default:
      return "i-lucide-info";
  }
}
