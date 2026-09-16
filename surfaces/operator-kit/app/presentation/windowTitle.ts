/**
 * Título da janela de um app de operador: `"<App> · <Página>"`.
 *
 * O app vem PRIMEIRO por causa do Chrome: num PWA instalado, quando o
 * `document.title` não começa com o `name` do manifesto, o navegador prefixa
 * `"<name> - "` por segurança (docs/webapps do Chromium). Com a página primeiro
 * ("Filipetas · PDV") a janela virava "PDV - Filipetas · PDV". Com o app na
 * frente, o Chrome reconhece o nome e não repete nada.
 *
 * Regra pura para ser testada sem montar componente:
 *   - sem título de página → só o nome do app;
 *   - título igual ao nome do app → só o nome (a home não duplica);
 *   - senão → `"<App> · <Página>"`.
 */
export function windowTitle(appName: string, pageTitle?: string | null): string {
  const app = appName.trim();
  const page = (pageTitle || "").trim();
  if (!page || page === app) return app;
  if (!app) return page;
  return `${app} · ${page}`;
}
