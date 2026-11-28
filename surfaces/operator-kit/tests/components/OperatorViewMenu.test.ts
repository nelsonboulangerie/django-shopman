// "Exibir" no estreito (dono, 07/11/2026): a peça é um botão só, com o estado no nome.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";

import OperatorViewMenu from "../../app/components/OperatorViewMenu.vue";
import type { OperatorViewGroup } from "../../app/presentation/viewMenu";

const groups: OperatorViewGroup[] = [
  {
    kind: "choice",
    key: "layout",
    label: "Vista",
    value: "list",
    options: [
      { value: "grid", label: "Grade", icon: "lucide:layout-grid" },
      { value: "list", label: "Lista", icon: "lucide:list" },
    ],
    select: () => {},
  },
  {
    kind: "toggle",
    key: "hide",
    label: "Ocultar indisponíveis",
    onLabel: "indisponíveis ocultos",
    checked: true,
    icon: "lucide:eye-off",
    toggle: () => {},
  },
];

describe("OperatorViewMenu", () => {
  it("um botão só, com o estado inteiro no nome", async () => {
    const wrapper = await mountSuspended(OperatorViewMenu, { props: { groups } });
    const button = wrapper.get("[data-operator-view-menu]");
    expect(button.attributes("aria-label")).toBe("Exibir: Lista, indisponíveis ocultos");
    expect(wrapper.findAll("button")).toHaveLength(1);
    wrapper.unmount();
  });
});
