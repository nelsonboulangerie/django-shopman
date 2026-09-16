import { describe, expect, it } from "vitest";
import { definePwaCapability } from "../pwa.config";
import { buildOperatorManifest } from "../server/utils/pwa";

const options = {
  app: "pos",
  display: "standalone" as const,
  wakeLock: true,
  kiosk: false,
  manifest: {
    name: "Shopman PDV",
    shortName: "PDV",
    description: "Caixa da loja",
    themeColor: "#292524",
    backgroundColor: "#FAFAF9",
    orientation: "landscape" as const,
    icons: [
      { src: "/pwa/pwa-192x192.png", sizes: "192x192", purpose: "any" as const },
      { src: "/pwa/pwa-512x512.png", sizes: "512x512", purpose: "any" as const },
      { src: "/pwa/maskable-512x512.png", sizes: "512x512", purpose: "maskable" as const },
    ],
    shortcuts: [
      { name: "Venda", url: "/" },
      { name: "Caixa", shortName: "Caixa", url: "/session" },
    ],
  },
};

describe("operator PWA capability", () => {
  it("é um módulo opt-in com a configuração inteira do app", () => {
    const registration = definePwaCapability(options);
    expect(registration).toHaveLength(2);
    expect(registration[1]).toEqual(options);
  });

  it("produz manifesto same-origin completo e sem push", () => {
    const manifest = buildOperatorManifest(options);
    expect(manifest).toMatchObject({
      id: "/",
      name: "Shopman PDV",
      short_name: "PDV",
      start_url: "/?source=pwa",
      scope: "/",
      display: "standalone",
      orientation: "landscape",
      theme_color: "#292524",
      background_color: "#FAFAF9",
    });
    expect(manifest.icons).toEqual(expect.arrayContaining([
      expect.objectContaining({ sizes: "192x192", purpose: "any" }),
      expect.objectContaining({ sizes: "512x512", purpose: "maskable" }),
    ]));
    expect(manifest.shortcuts).toEqual([
      expect.objectContaining({ name: "Venda", url: "/" }),
      expect.objectContaining({ name: "Caixa", url: "/session" }),
    ]);
    expect(manifest).not.toHaveProperty("gcm_sender_id");
  });
});
