// Identidade do app no rail: o quadrado de identidade mostra o ícone REAL do app (o PNG
// da família PWA) quando o app passa `appIconSrc`, e cai no Lucide quando a prop falta
// OU quando a imagem falha — o rail nunca fica com um quadrado vazio no lugar da marca.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import type { VueWrapper } from "vue";

import OperatorRail from "../../app/components/OperatorRail.vue";

const ICON_SRC = "/pwa/pwa-64x64.png?v=3";

const mounted: VueWrapper[] = [];

async function mountRail(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorRail, {
    props: { appIcon: "shopping-basket", appLabel: "PDV", ...props },
    global: { stubs: { Icon: true, ClientOnly: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

/** O quadrado de identidade é o primeiro filho do link/div de identidade do rail. */
function identitySquare(wrapper: Awaited<ReturnType<typeof mountRail>>) {
  return wrapper.get("aside > :first-child > span");
}

beforeEach(() => {
  // O layer não instala @nuxtjs/color-mode; quem fornece o composable é o app hospedeiro.
  vi.stubGlobal("useColorMode", () => ({ value: "light", preference: "light" }));
  useRailState().set("compact");
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

describe("OperatorRail — identidade do app", () => {
  it("sem appIconSrc renderiza o Lucide (comportamento de quem não passa a prop)", async () => {
    const wrapper = await mountRail();
    const square = identitySquare(wrapper);

    expect(square.find("img").exists()).toBe(false);
    expect(square.getComponent({ name: "Icon" }).attributes("name")).toBe("lucide:shopping-basket");
  });

  it("com appIconSrc renderiza o PNG do app no lugar do Lucide, decorativo (alt vazio)", async () => {
    const wrapper = await mountRail({ appIconSrc: ICON_SRC });
    const square = identitySquare(wrapper);
    const img = square.get("img");

    expect(img.attributes("src")).toBe(ICON_SRC);
    expect(img.attributes("alt")).toBe("");
    expect(img.classes()).toContain("size-11");
    expect(square.findComponent({ name: "Icon" }).exists()).toBe(false);
  });

  it("imagem que falha cai no Lucide — nunca um quadrado vazio", async () => {
    const wrapper = await mountRail({ appIconSrc: ICON_SRC });
    const square = identitySquare(wrapper);

    await square.get("img").trigger("error");

    expect(square.find("img").exists()).toBe(false);
    expect(square.getComponent({ name: "Icon" }).attributes("name")).toBe("lucide:shopping-basket");
  });

  it("com centralUrl a imagem some no hover como o Lucide (vira a seta de voltar)", async () => {
    const wrapper = await mountRail({ appIconSrc: ICON_SRC, centralUrl: "http://central/" });
    const square = identitySquare(wrapper);

    expect(square.get("img").classes()).toContain("group-hover:hidden");
    // A seta "voltar à Central" continua ali, escondida até o hover/foco.
    const arrow = square.findAllComponents({ name: "Icon" }).find((c) => c.attributes("name") === "lucide:arrow-left");
    expect(arrow?.exists()).toBe(true);
    expect(wrapper.get("aside > a").attributes("href")).toBe("http://central/");
  });

  it("na própria Central (sem centralUrl) a imagem é identidade pura, sem hover", async () => {
    const wrapper = await mountRail({ appIconSrc: ICON_SRC });
    expect(identitySquare(wrapper).get("img").classes()).not.toContain("group-hover:hidden");
  });

  it("o PNG tem os cantos transparentes: o fundo do quadrado só aparece sem imagem ou no hover", async () => {
    const withImage = identitySquare(await mountRail({ appIconSrc: ICON_SRC, centralUrl: "http://central/" }));
    expect(withImage.classes()).not.toContain("bg-rail-foreground/15");
    expect(withImage.classes()).toContain("group-hover:bg-rail-foreground/25");

    const withLucide = identitySquare(await mountRail());
    expect(withLucide.classes()).toContain("bg-rail-foreground/15");
  });
});

describe("OperatorRail — trava de giro", () => {
  const sonner = { success: vi.fn(), warning: vi.fn() };

  async function mountWithClientOnly() {
    const wrapper = await mountSuspended(OperatorRail, {
      props: { appIcon: "chef-hat", appLabel: "Cozinha" },
      global: { stubs: { Icon: true } },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    await nextTick();
    return wrapper;
  }

  beforeEach(() => {
    sonner.success.mockReset();
    sonner.warning.mockReset();
    vi.stubGlobal("useSonner", sonner);
    useState("operator-orientation-lock").value = null;
    useState("operator-orientation-lock-status").value = "unlocked";
    useState("operator-orientation-lock-available").value = false;
    localStorage.clear();
  });

  it("PC sem toque não mostra o controle", async () => {
    Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: 0 });
    Object.defineProperty(screen, "orientation", { configurable: true, value: { type: "landscape-primary", lock: vi.fn() } });
    const wrapper = await mountWithClientOnly();

    expect(wrapper.find("[data-orientation-lock]").exists()).toBe(false);
  });

  it("tablet: trava, avisa e passa a oferecer liberar", async () => {
    Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: 5 });
    Object.defineProperty(screen, "orientation", {
      configurable: true,
      value: { type: "landscape-primary", lock: vi.fn().mockResolvedValue(undefined), unlock: vi.fn() },
    });
    const wrapper = await mountWithClientOnly();
    const item = wrapper.get("[data-orientation-lock]");
    expect(item.attributes("aria-label")).toBe("Travar o giro da tela na orientação atual");
    expect(item.attributes("aria-pressed")).toBe("false");

    await item.trigger("click");
    await vi.waitFor(() => expect(sonner.success).toHaveBeenCalledWith("Giro travado em paisagem."));
    await nextTick();
    expect(wrapper.get("[data-orientation-lock]").attributes("aria-label")).toBe("Liberar o giro da tela (travado em paisagem)");
    expect(wrapper.get("[data-orientation-lock]").attributes("aria-pressed")).toBe("true");
  });

  it("aparelho que recusa: aviso honesto e o controle continua oferecendo travar", async () => {
    Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: 5 });
    Object.defineProperty(screen, "orientation", {
      configurable: true,
      value: { type: "portrait-primary", lock: vi.fn().mockRejectedValue(new DOMException("no", "NotSupportedError")) },
    });
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query === "(display-mode: standalone)", media: query }));
    const wrapper = await mountWithClientOnly();

    await wrapper.get("[data-orientation-lock]").trigger("click");
    await vi.waitFor(() => expect(sonner.warning).toHaveBeenCalledWith(
      "Este aparelho não deixa o app travar o giro — use o bloqueio de rotação do sistema.",
    ));
    expect(sonner.success).not.toHaveBeenCalled();
    expect(wrapper.get("[data-orientation-lock]").attributes("aria-pressed")).toBe("false");
  });
});
