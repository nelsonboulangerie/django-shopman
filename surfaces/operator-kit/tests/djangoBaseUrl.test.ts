import { describe, expect, it } from "vitest";

import {
  assertProductionDjangoConfiguration,
  isProductionRuntime,
  resolveDjangoBaseUrl,
} from "../server/utils/djangoBaseUrl";

describe("Django upstream configuration", () => {
  it("fails with an HTTP-shaped 503 without importing the h3 runtime", () => {
    try {
      resolveDjangoBaseUrl("", { production: true });
      throw new Error("expected configuration failure");
    } catch (error) {
      expect(error).toMatchObject({
        statusCode: 503,
        statusMessage: "Django upstream is not configured",
      });
    }
  });

  it("accepts only an explicit remote HTTPS upstream in production", () => {
    expect(
      assertProductionDjangoConfiguration({
        NODE_ENV: "production",
        NUXT_SHOPMAN_ENVIRONMENT: "alpha",
        NUXT_DJANGO_BASE_URL: "https://api.boulangerie.com.br/",
      }),
    ).toBe("https://api.boulangerie.com.br");

    expect(() =>
      assertProductionDjangoConfiguration({
        NODE_ENV: "production",
        NUXT_SHOPMAN_ENVIRONMENT: "alpha",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8000",
      }),
    ).toThrow("Django upstream cannot be local in production");
  });

  it("lets an explicitly local prepare step override npm's production NODE_ENV", () => {
    expect(
      isProductionRuntime({
        NODE_ENV: "production",
        NUXT_SHOPMAN_ENVIRONMENT: "development",
      }),
    ).toBe(false);
  });
});
