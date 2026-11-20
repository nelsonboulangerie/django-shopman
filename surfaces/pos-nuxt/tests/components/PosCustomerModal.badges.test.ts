// Os selos de latão do diálogo Cliente (#2894): "🎂 Aniversário hoje" e "Cliente novo".
//
// 1. Contraste AA (4,5:1). O texto em latão puro (`text-primary`) sobre latão a 10%, no
//    cartão do cadastro que já é latão a 5% sobre o branco, media 4,09:1 no PDV de verdade.
//    O texto passa a escrever com a tinta `--primary-ink` do operator-kit (o tom mais escuro
//    do mesmo latão, 85% latão + 15% do texto), a mesma do Badge `soft` e do dia escolhido
//    do `OperatorDayPicker`. Fundo e borda não mudam. Medido aqui sobre os tokens de
//    `operator-theme.css`, nos dois temas.
// 2. Selo tem maiúscula só na primeira letra (dono, 16/11): "Aniversário hoje", não "HOJE".
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";

import PosCustomerModal from "~/components/PosCustomerModal.vue";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn().mockResolvedValue({}) }));
mockNuxtImport("$fetch", () => fetchMock);

const here = dirname(fileURLToPath(import.meta.url));
const themeCss = readFileSync(resolve(here, "../../../operator-kit/app/assets/css/operator-theme.css"), "utf8");

type Theme = "light" | "dark";

function tokens(selector: ":root" | ".dark"): Record<string, string> {
  const found: Record<string, string> = {};
  const pattern = new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")}\\s*\\{([\\s\\S]*?)\\n\\}`, "g");
  for (const block of themeCss.matchAll(pattern)) {
    for (const match of block[1]!.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)) found[match[1]!] = match[2]!;
  }
  return found;
}

const THEME: Record<Theme, Record<string, string>> = {
  light: tokens(":root"),
  dark: { ...tokens(":root"), ...tokens(".dark") },
};

function rgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  return [0, 2, 4].map((at) => Number.parseInt(value.slice(at, at + 2), 16)) as [number, number, number];
}

function mix(top: string, alpha: number, bottom: string): string {
  const a = rgb(top);
  const b = rgb(bottom);
  return `#${a.map((channel, i) => Math.round(alpha * channel + (1 - alpha) * b[i]!).toString(16).padStart(2, "0")).join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** A tinta como o tema a declara: 85% de latão sobre o texto no claro, o próprio latão no escuro. */
function primaryInk(theme: Theme): string {
  const t = THEME[theme];
  return theme === "light" ? mix(t.primary!, 0.85, t.foreground!) : t.primary!;
}

/** O fundo do selo: latão a 10% sobre o cartão do cadastro (latão a 5% sobre o cartão do diálogo). */
function badgeBackground(theme: Theme): string {
  const t = THEME[theme];
  return mix(t.primary!, 0.1, mix(t.primary!, 0.05, t.card!));
}

const MARIA = {
  ref: "MARIA",
  name: "Maria Santos",
  phone: "+5543991111111",
  email: "",
  tax_id: "",
  fiscal_prefs: {},
  notes: "",
  dietary_restrictions: "",
  birthday_display: "20/11",
  is_birthday_today: true,
  is_birthday_month: true,
  birthday_promo_label: "Parabéns! Desconto de aniversário",
  memory: { total_orders: 29, average_order_display: "", favorite_product: "", favorite_item: {}, last_order_items: [] },
};

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

async function mount(props: Record<string, unknown> = {}) {
  mounted = await mountSuspended(PosCustomerModal, {
    props: {
      open: true,
      customerName: MARIA.name,
      customerPhone: MARIA.phone,
      customerTaxId: "",
      customerEmail: "",
      customerLookup: MARIA,
      searchResults: [],
      searchBusy: false,
      lookupBusy: false,
      ...props,
    },
    global: { stubs: { Icon: true } },
  });
}

const classes = (el: Element | null) => (el?.getAttribute("class") || "").split(/\s+/);

describe("selos de latão do diálogo Cliente (#2894)", () => {
  it("a tinta do latão passa o AA sobre o selo no cartão do cadastro, nos dois temas; o latão puro não passava", () => {
    expect(contrast(THEME.light.primary!, badgeBackground("light"))).toBeLessThan(4.5);
    for (const theme of ["light", "dark"] as const) {
      expect(contrast(primaryInk(theme), badgeBackground(theme)), theme).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("aniversário: 'Aniversário hoje' com maiúscula só na primeira letra, escrito com a tinta", async () => {
    await mount();
    const badge = document.querySelector("[data-customer-birthday-today]");
    expect(badge?.textContent?.replace(/\s+/g, " ").trim()).toBe("🎂 Aniversário hoje · Parabéns! Desconto de aniversário");
    expect(document.body.textContent).not.toContain("HOJE");
    expect(classes(badge)).toContain("text-(--primary-ink)");
    expect(classes(badge)).not.toContain("text-primary");
  });

  it("cliente novo: o selo do cadastro criado agora também escreve com a tinta", async () => {
    await mount({ resolvedNew: true });
    const chip = [...document.querySelectorAll("[data-customer-state] span")].find((el) => el.textContent?.trim() === "Cliente novo");
    expect(chip).toBeTruthy();
    expect(classes(chip!)).toContain("text-(--primary-ink)");
    expect(classes(chip!)).not.toContain("text-primary");
  });
});
