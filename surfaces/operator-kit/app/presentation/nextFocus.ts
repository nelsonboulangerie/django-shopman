// Próximo foco — a regra pura de "onde a página deve estar agora".
//
// A tela declara qual é o foco do momento (uma chave); os blocos se marcam com
// `data-focus-target="<chave>"`. Quando a chave muda, o bloco correspondente vai
// para a LINHA DE FOCO: o topo da área visível, logo abaixo do chrome fixo (o
// próprio bloco declara a folga via `scroll-margin-top`, que o `scrollIntoView`
// nativo respeita). Acima da linha, o que já foi feito; na linha, o que se faz
// agora; abaixo, o que vem depois. Sempre a mesma posição, para o olho nunca
// precisar procurar.
//
// Esta camada não toca o DOM — só decide. A escuta e a rolagem vivem em
// `composables/useNextFocus`. Espelhado em `storefront-nuxt/app/presentation/nextFocus.ts`.

export const FOCUS_TARGET_ATTRIBUTE = "data-focus-target";
export const FOCUS_CONTROL_ATTRIBUTE = "data-focus-control";

export type FocusAlign = "start" | "center";

export interface RevealOptions {
  // `start` = linha de foco (padrão: "comece a trabalhar aqui"). `center` = só
  // mostrar (um erro, um item de lista) sem reorganizar a página em torno dele.
  align?: FocusAlign;
  // Move o foco de teclado/leitor de tela junto com a rolagem (padrão: sim).
  focus?: boolean;
}

export interface RevealPlan {
  align: FocusAlign;
  behavior: ScrollBehavior;
  focus: boolean;
}

export function focusTargetSelector(key: string): string {
  return `[${FOCUS_TARGET_ATTRIBUTE}="${key.replace(/["\\]/g, "\\$&")}"]`;
}

// Quem pediu menos movimento recebe o salto direto; o destino é o mesmo.
export function revealBehavior(reducedMotion: boolean): ScrollBehavior {
  return reducedMotion ? "auto" : "smooth";
}

export function revealPlan(options: RevealOptions = {}, reducedMotion = false): RevealPlan {
  return {
    align: options.align ?? "start",
    behavior: revealBehavior(reducedMotion),
    focus: options.focus ?? true,
  };
}

export interface VisibleBox {
  top: number;
  bottom: number;
  viewportHeight: number;
}

// Na primeira pintura a página não salta à toa: quem chega e já vê o bloco de
// foco inteiro fica onde está (o título da página é contexto). Só sai do lugar
// se o foco está fora (ou parcialmente fora) da área visível — o caso de quem
// volta a um rascunho salvo na etapa final, lá embaixo.
export function needsInitialReveal({ top, bottom, viewportHeight }: VisibleBox): boolean {
  if (viewportHeight <= 0) return false;
  return top < 0 || bottom > viewportHeight;
}
