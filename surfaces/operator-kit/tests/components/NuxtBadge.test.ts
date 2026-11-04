import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";
import { h } from "vue";

import NuxtBadge from "../../app/components/NuxtBadge.vue";
import BadgeInTemplate from "../support/BadgeInTemplate.vue";

// O selo do kit substitui o do Nuxt UI pelo mesmo nome: todo `<NuxtBadge>` da suíte sai
// com iniciais maiúsculas, venha o texto do `label` ou de dentro do selo.
describe("NuxtBadge do kit", () => {
  it("o label sai com iniciais maiúsculas", async () => {
    const badge = await mountSuspended(NuxtBadge, { props: { label: "loja online", color: "neutral" } });
    expect(badge.text()).toBe("Loja Online");
    expect(badge.get('[data-slot="base"]').classes().join(" ")).toContain("rounded");
  });

  it("o texto escrito dentro do selo também", async () => {
    const badge = await mountSuspended(NuxtBadge, {
      slots: { default: () => ["a receber"] },
    });
    expect(badge.text()).toBe("A Receber");
  });

  it("texto dentro de um elemento do selo também, e o resto fica como está", async () => {
    const badge = await mountSuspended(NuxtBadge, {
      slots: { default: () => h("span", { "data-x": "" }, "pago na retirada") },
    });
    expect(badge.get("[data-x]").text()).toBe("Pago na Retirada");
  });

  it("número e marca não mudam", async () => {
    const badge = await mountSuspended(NuxtBadge, { props: { label: 3 } });
    expect(badge.text()).toBe("3");
  });

  it("`<NuxtBadge>` escrito num template resolve para o selo do kit, não o do Nuxt UI", async () => {
    const page = await mountSuspended(BadgeInTemplate);
    expect(page.get("[data-a]").text()).toBe("Loja Online");
    expect(page.get("[data-b]").text()).toBe("Pago na Retirada");
  });
});
