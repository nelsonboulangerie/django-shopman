import { setResponseHeaders } from "h3";
import { resolveOperatorAppName } from "../../server/utils/operatorAppName";

// `{ prefix, label, name }` do app para a primeira pintura (SSR) e para o cliente sem
// payload. Mesmo resolvedor do `/manifest.webmanifest`: título e manifesto não divergem.
export default defineEventHandler(async (event) => {
  setResponseHeaders(event, { "cache-control": "no-store" });
  return resolveOperatorAppName(event);
});
