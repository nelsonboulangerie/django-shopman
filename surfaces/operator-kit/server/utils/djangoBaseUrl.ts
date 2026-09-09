import { createError } from "h3";

const LOCAL_DJANGO_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]);
const PRODUCTION_ENVIRONMENTS = new Set(["production", "prod"]);
const TEST_ENVIRONMENTS = new Set(["test", "testing", "e2e"]);
const LOCAL_ENVIRONMENTS = new Set(["development", "dev", "local"]);
const DEVELOPMENT_DJANGO_BASE_URL = "http://127.0.0.1:8000";

type Environment = Record<string, string | undefined>;

function shopmanEnvironment(environment: Environment): string {
  return String(environment.NUXT_SHOPMAN_ENVIRONMENT || environment.SHOPMAN_ENVIRONMENT || "")
    .trim()
    .toLowerCase();
}

export function isProductionRuntime(environment: Environment = process.env): boolean {
  const declaredEnvironment = shopmanEnvironment(environment);
  if (PRODUCTION_ENVIRONMENTS.has(declaredEnvironment)) return true;
  // Playwright compila o app como NODE_ENV=production, mas aponta deliberadamente
  // para um mock local. A exceção exige ambiente + flag de teste explícitos.
  if (isExplicitTestRuntime(environment)) return false;
  return String(environment.NODE_ENV || "").trim().toLowerCase() === "production";
}

export function isExplicitTestRuntime(environment: Environment = process.env): boolean {
  return TEST_ENVIRONMENTS.has(shopmanEnvironment(environment))
    && environment.SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM === "1";
}

export function resolveDjangoBaseUrl(
  rawValue: unknown,
  options: { production?: boolean } = {},
): string {
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

  if (!new Set(["http:", "https:"]).has(url.protocol)) {
    throw createError({ statusCode: 503, statusMessage: "Django upstream must use HTTP or HTTPS" });
  }

  const production = options.production ?? isProductionRuntime();
  if (production) {
    if (LOCAL_DJANGO_HOSTS.has(url.hostname)) {
      throw createError({ statusCode: 503, statusMessage: "Django upstream cannot be local in production" });
    }
    if (url.protocol !== "https:") {
      throw createError({ statusCode: 503, statusMessage: "Django upstream must use HTTPS in production" });
    }
  }

  return value;
}

export function configuredDjangoBaseUrl(environment: Environment = process.env): string {
  const production = isProductionRuntime(environment);
  if (production) return assertProductionDjangoConfiguration(environment);

  const configured = environment.NUXT_DJANGO_BASE_URL;
  return resolveDjangoBaseUrl(configured || DEVELOPMENT_DJANGO_BASE_URL, { production: false });
}

export function assertProductionDjangoConfiguration(environment: Environment = process.env): string {
  const declaredEnvironment = shopmanEnvironment(environment);
  if (!declaredEnvironment) {
    throw createError({ statusCode: 503, statusMessage: "Shopman environment is not configured" });
  }
  if (LOCAL_ENVIRONMENTS.has(declaredEnvironment) || TEST_ENVIRONMENTS.has(declaredEnvironment)) {
    throw createError({ statusCode: 503, statusMessage: "Shopman environment cannot be local in production" });
  }
  return resolveDjangoBaseUrl(environment.NUXT_DJANGO_BASE_URL, { production: true });
}
