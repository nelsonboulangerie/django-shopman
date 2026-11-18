import { describe, expect, it, vi } from "vitest";
import { computed } from "vue";
import { mount } from "@vue/test-utils";

import KdsCardButton from "../../app/components/KdsCardButton.vue";
import { nuxtUiStubs } from "../support/nuxtUi";

// Auto-import do Nuxt que o SFC usa como global (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);

const STRIPES =
  "bg-[repeating-linear-gradient(135deg,transparent_0_7px,color-mix(in_oklab,var(--destructive)_9%,transparent)_7px_14px)]";

describe("KdsCardButton, tom travado (Pronto que o servidor recusaria)", () => {
  it("entrega o texto apagado e o listrado como duas classes separadas", () => {
    const wrapper = mount(KdsCardButton, {
      props: { tone: "locked", icon: "lucide:lock", label: "Pronto W07", sizeClass: "h-14 text-base" },
      global: { stubs: nuxtUiStubs },
    });
    const classes = wrapper.get("button").classes();
    // Coladas ("text-muted-foregroundbg-[...]"), nenhuma das duas existe no Tailwind e o
    // travado fica só com a borda tracejada.
    expect(classes).toContain("text-muted-foreground");
    expect(classes).toContain(STRIPES);
    expect(classes).toContain("border-dashed");
    expect(classes.some((c) => c.startsWith("text-muted-foregroundbg"))).toBe(false);
  });
});
