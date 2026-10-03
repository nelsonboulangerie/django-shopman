import { apiPath } from "../utils/api";

/** `apiPath` já amarrado ao `baseURL` deste app (runtime config).
 *
 * É como PDV e Central sempre consumiram o prefixo — cada um com o seu wrapper
 * idêntico (`usePosApiPath`, `useHubApiPath`). Agora há um só. */
export function useApiPath(): (path: string) => string {
  const baseURL = useRuntimeConfig().app.baseURL || "/";
  return (path: string) => apiPath(path, baseURL);
}
