import { describe, expect, it } from "vitest";
import { definePwaCapability } from "../pwa.config";
import { buildOperatorManifest } from "../server/utils/pwa";
import { operatorAppName } from "../app/presentation/windowTitle";

const options = {
  app: "pos",
  display: "standalone" as const,
  wakeLock: true,
  kiosk: false,
  manifest: {
    label: "PDV",
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
    const manifest = buildOperatorManifest(options, operatorAppName("Nelson", "PDV"));
    expect(manifest).toMatchObject({
      id: "/",
      name: "Nelson · PDV",
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

  it("chegar de outro app FOCA a janela existente em vez de levá-la embora", () => {
    // `navigate-existing` recarregaria o PDV com venda na mão só porque alguém tocou
    // no atalho da Central. `focus-existing`, sem consumidor de `launchQueue`, traz a
    // janela para a frente e descarta o URL — que é o que um launcher deve fazer.
    const manifest = buildOperatorManifest(options);
    expect(manifest.launch_handler).toEqual({ client_mode: "focus-existing" });
  });

  it("sem a casa (Django fora e nenhum nome anterior) o manifesto é só o rótulo", () => {
    const manifest = buildOperatorManifest(options);
    expect(manifest.name).toBe("PDV");
    expect(manifest.short_name).toBe("PDV");
  });
});
