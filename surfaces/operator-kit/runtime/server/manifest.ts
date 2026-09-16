import { setResponseHeaders } from "h3";
import { buildOperatorManifest } from "../../server/utils/pwa";
import type { OperatorPwaCapabilityOptions } from "../../pwa.config";

export default defineEventHandler((event) => {
  const options = useRuntimeConfig(event).public.operatorPwa as OperatorPwaCapabilityOptions;
  setResponseHeaders(event, {
    "cache-control": "public, max-age=3600",
    "content-type": "application/manifest+json; charset=utf-8",
  });
  return buildOperatorManifest(options);
});
