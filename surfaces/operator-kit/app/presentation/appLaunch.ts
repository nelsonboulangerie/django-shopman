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
/** Link para fora da casa (a loja do cliente, o Portal, o WhatsApp): sempre em outra janela. */
export const EXTERNAL_LINK_ATTRS: CrossAppLinkAttrs = OTHER_APP_WINDOW;

/** `href` aponta para a MESMA origem? Relativo conta como mesma; inválido, também. */
export function sameOrigin(href: string, currentOrigin: string): boolean {
  try {
    return new URL(href, currentOrigin || "http://localhost").origin === new URL(currentOrigin).origin;
  } catch {
    return true;
  }
}

/**
 * Sufixos públicos que nunca são "o domínio da casa": sem esta guarda, um app em
 * `x.com.br` acharia que todo `*.com.br` é dele.
 */
const PUBLIC_SUFFIXES = new Set(["com", "net", "org", "br", "app", "dev", "io", "com.br", "net.br", "org.br", "gov.br"]);
const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;
/** Os nomes desta máquina: em dev, `localhost` e `127.0.0.1` são o mesmo lugar. */
const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

/**
 * O `href` é de um app DA CASA (o mesmo host, ou um irmão sob o mesmo domínio), e não
 * um site de fora (Portal do iFood, ManyChat, Google, WhatsApp, a loja do cliente)?
 *
 * Os apps de operador são subdomínios do domínio da loja (`surfaces/registry.json`,
 * `subdomain`: `pdv.` → `pdv.boulangerie.com.br`; no local, `pdv.boulangerie`), e em
 * dev mudam só de porta no mesmo host. Então: mesmo host é da casa; host sob o mesmo
 * domínio-pai do app atual também. Relativo ou inválido conta como da casa (não vira
 * navegação para fora).
 */
export function houseHref(href: string, currentOrigin: string): boolean {
  let target: URL;
  let current: URL;
  try {
    current = new URL(currentOrigin);
    target = new URL(href, current);
  } catch {
    return true;
  }
  if (target.hostname === current.hostname) return true;
  if (LOOPBACK.has(target.hostname) && LOOPBACK.has(current.hostname)) return true;
  if (IPV4.test(current.hostname)) return false;
  const parent = current.hostname.split(".").slice(1).join(".");
  if (!parent || PUBLIC_SUFFIXES.has(parent)) return false;
  return target.hostname === parent || target.hostname.endsWith(`.${parent}`);
}

/**
 * Atributos do link de um app de operador para OUTRO lugar.
 *
 * Site de FORA da casa (Portal do iFood, ManyChat, Google, WhatsApp): nova aba,
 * SEMPRE, instalado ou não (coordenação, 21/11/2026). O operador não pode perder o
 * Gestor para ir ao Portal.
 *
 * Outro app DA CASA: instalado, a outra origem ganha janela própria. NÃO instalado
 * (aba comum do navegador), nada muda: continuar na mesma aba é o que o operador
 * espera do navegador, e `_blank` ali só empilharia aba a cada troca de app.
 */
export function crossAppLinkAttrs(options: {
  installed: boolean;
  href: string;
  currentOrigin: string;
}): CrossAppLinkAttrs {
  if (!options.href) return SAME_WINDOW;
  if (sameOrigin(options.href, options.currentOrigin)) return SAME_WINDOW;
  if (!houseHref(options.href, options.currentOrigin)) return EXTERNAL_LINK_ATTRS;
  return options.installed ? OTHER_APP_WINDOW : SAME_WINDOW;
}


