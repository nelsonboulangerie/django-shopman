// Identidade do app no rail: o quadrado de identidade mostra o ícone REAL do app (o PNG
// da família PWA) quando o app passa `appIconSrc`, e cai no Lucide quando a prop falta
// OU quando a imagem falha — o rail nunca fica com um quadrado vazio no lugar da marca.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { VueWrapper } from "vue";

import OperatorRail from "../../app/components/OperatorRail.vue";

const ICON_SRC = "/pwa/pwa-64x64.png?v=2";

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
});
