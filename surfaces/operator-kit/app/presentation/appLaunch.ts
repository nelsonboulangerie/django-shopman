// Como um app de operador MANDA o operador para outro app.
//
// O problema, relatado em 17/09/2026 com os oito apps já instaláveis: sair do PDV para
// a Central abria "uma tarja grande em cima", como se o navegador tivesse entrado em
// outro site, e o título e a cor da barra da janela continuavam sendo os do PRIMEIRO
// app aberto, qualquer que fosse ele.
//
// Não é bug de estilo, é o contrato do PWA instalado. Cada app é um HOST próprio
// (`pdv.`, `central.`, `cozinha.`…), e o `scope` do manifesto é por origem. Navegar no
// MESMO frame para outra origem é sair do escopo: o Chrome mantém a janela — que
// pertence ao app que a abriu, com o `name` e o `theme_color` DELE — e desenha por cima
// a barra de "você saiu do app". Daí os dois sintomas de uma vez.
//
// A saída não é esconder a barra; é não fazer essa navegação. O app de destino tem
// janela própria, e é nela que ele deve abrir.
//
// Para o Chrome CAPTURAR a navegação e abri-la na janela do app de destino, ela precisa
// ser "capturável": criar um frame novo e NÃO ser um contexto auxiliar (a definição da
// documentação de navigation capturing, ligada por padrão desde o Chrome 139). Um
// `target="_blank"` comum guarda `opener` e é auxiliar; com `rel="noopener"` o contexto
// nasce sem opener e é capturável. Ou seja: aqui o `noopener` não é só higiene de
// segurança — é a condição de o link abrir no app certo.

export interface CrossAppLinkAttrs {
  target: "_self" | "_blank";
  rel?: string;
}

const SAME_WINDOW: CrossAppLinkAttrs = { target: "_self" };
/** Ver acima: sem `noopener` o contexto é auxiliar e o Chrome não captura. */
const OTHER_APP_WINDOW: CrossAppLinkAttrs = { target: "_blank", rel: "noopener" };

/** `href` aponta para a MESMA origem? Relativo conta como mesma; inválido, também. */
export function sameOrigin(href: string, currentOrigin: string): boolean {
  try {
    return new URL(href, currentOrigin || "http://localhost").origin === new URL(currentOrigin).origin;
  } catch {
    return true;
  }
}

/**
 * Atributos do link de um app de operador para OUTRO app de operador.
 *
 * Instalado, a outra origem ganha janela própria. NÃO instalado (aba comum do
 * navegador), nada muda: continuar na mesma aba é o que o operador espera do
 * navegador, e `_blank` ali só empilharia aba a cada troca de app.
 */
export function crossAppLinkAttrs(options: {
  installed: boolean;
  href: string;
  currentOrigin: string;
}): CrossAppLinkAttrs {
  if (!options.href) return SAME_WINDOW;
  if (sameOrigin(options.href, options.currentOrigin)) return SAME_WINDOW;
  return options.installed ? OTHER_APP_WINDOW : SAME_WINDOW;
}

/** Link para fora da casa (a loja do cliente): sempre em outra janela, instalado ou não. */
export const EXTERNAL_LINK_ATTRS: CrossAppLinkAttrs = OTHER_APP_WINDOW;
