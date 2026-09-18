import { setResponseHeaders } from "h3";
import { buildOperatorManifest } from "../../server/utils/pwa";
import { resolveOperatorAppName } from "../../server/utils/operatorAppName";
import type { ResolvedOperatorPwa } from "../../pwa.config";

export default defineEventHandler(async (event) => {
  const options = useRuntimeConfig(event).public.operatorPwa as ResolvedOperatorPwa;
  const appName = await resolveOperatorAppName(event);
  setResponseHeaders(event, {
    // Curto o bastante para a troca do `Shop.short_name` no Admin chegar ao app
    // instalado sem esperar uma hora; o cache do prefixo no BFF já poupa o Django.
    "cache-control": "public, max-age=3600",
    "content-type": "application/manifest+json; charset=utf-8",
  });
  return buildOperatorManifest(options, appName);
});
