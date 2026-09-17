/** Prefix a path with the app's baseURL (handles the "/" no-op and trailing slash).
 *
 * Um dono só para as oito superfícies de operador: antes cada app carregava esta
 * mesma função com nome próprio (`apiPath` em bi/kds/marketing/orders/production,
 * `hubApiPath` na Central, `posApiPath` no PDV). Em código de app, prefira
 * `useApiPath()` — ele já amarra o `baseURL` do runtime config. */
export function apiPath(path: string, baseURL = "/"): string {
  const base = baseURL === "/" ? "" : baseURL.replace(/\/$/, "");
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalized}`;
}
