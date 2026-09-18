/**
 * Nome e título da janela de um app de operador.
 *
 * O app instalado se chama `"<casa> · <App>"` ("Nelson · PDV"). A casa é dado do
 * tenant (`Shop.short_name`, lido do Django em runtime pelo BFF); o app declara só o
 * próprio rótulo ("PDV") em `definePwaCapability(...)`. O separador é SEMPRE o ponto
 * médio: hífen na barra de título da janela é o que o dono não quer ver.
 *
 * O nome vem PRIMEIRO no título por causa do Chrome: num PWA instalado, quando o
 * `document.title` não começa com o `name` do manifesto, o navegador prefixa
 * `"<name> - "` por segurança (docs/webapps do Chromium). Com a página primeiro
 * ("Filipetas · PDV") a janela virava "PDV - Filipetas · PDV". Com o nome na frente
 * — o MESMO que o `/manifest.webmanifest` serve — o Chrome não repete nada.
 */

export const OPERATOR_TITLE_SEPARATOR = " · ";

/** Rota same-origin (Nitro) que devolve o `OperatorAppName` do app, com a casa vinda do Django. */
export const OPERATOR_APP_NAME_ROUTE = "/_operator/app-name";

/** Chave do `useState` que leva o nome do SSR para o cliente no payload. */
export const OPERATOR_APP_NAME_STATE = "operator-app-name";

/** O que o app mostra como nome: casa + rótulo, ou só o rótulo quando não há casa. */
export interface OperatorAppName {
  /** `Shop.short_name` ("Nelson"); vazio quando o Django não respondeu nem uma vez. */
  prefix: string;
  /** Rótulo declarado pelo app ("PDV"). */
  label: string;
  /** `"<prefix> · <label>"` — o `name` do manifesto e o começo de todo título. */
  name: string;
}

// Hífen, meia-risca, travessão e barra vertical usados como separador de título
// ("404 - Page not found | Nuxt", da página de erro padrão do Nuxt). Hífen colado
// em palavra ("pão-de-queijo") não é separador e fica.
const TITLE_SEPARATORS = /\s+[-–—|]\s+/g;

function clean(value: string | null | undefined): string {
  return (value || "").replace(TITLE_SEPARATORS, OPERATOR_TITLE_SEPARATOR).trim();
}

export function operatorAppName(prefix: string | null | undefined, label: string | null | undefined): OperatorAppName {
  const cleanPrefix = clean(prefix);
  const cleanLabel = clean(label);
  const name = [cleanPrefix, cleanLabel].filter(Boolean).join(OPERATOR_TITLE_SEPARATOR);
  return { prefix: cleanPrefix, label: cleanLabel, name };
}

/**
 * Regra pura do título, testável sem montar componente:
 *   - sem título de página → só o nome do app;
 *   - título igual ao nome ou ao rótulo do app → só o nome (a home não duplica);
 *   - senão → `"<Nome> · <Página>"`, com qualquer separador de hífen/barra da página
 *     trocado pelo ponto médio.
 */
export function windowTitle(app: OperatorAppName | string, pageTitle?: string | null): string {
  const { name, label } = typeof app === "string" ? operatorAppName("", app) : app;
  const page = clean(pageTitle);
  if (!page || page === name || page === label) return name;
  if (!name) return page;
  return `${name}${OPERATOR_TITLE_SEPARATOR}${page}`;
}
