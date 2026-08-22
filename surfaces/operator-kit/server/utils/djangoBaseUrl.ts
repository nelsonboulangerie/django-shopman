import { createError } from "h3";

const LOCAL_DJANGO_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]);
const PRODUCTION_ENVIRONMENTS = new Set(["production", "prod"]);

function shopmanEnvironment(): string {
  return String(process.env.NUXT_SHOPMAN_ENVIRONMENT || process.env.SHOPMAN_ENVIRONMENT || "")
    .trim()
    .toLowerCase();
}

export function resolveDjangoBaseUrl(rawValue: unknown): string {
  const value = String(rawValue || "").trim().replace(/\/+$/, "");
  if (!value) {
    throw createError({ statusCode: 503, statusMessage: "Django upstream is not configured" });
  }

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw createError({ statusCode: 503, statusMessage: "Django upstream is invalid" });
  }

  if (PRODUCTION_ENVIRONMENTS.has(shopmanEnvironment()) && LOCAL_DJANGO_HOSTS.has(url.hostname)) {
    throw createError({ statusCode: 503, statusMessage: "Django upstream cannot be local in production" });
  }

  return value;
}
