// "Exibir" no estreito (dono, 07/11/2026): a vista, a densidade e o ocultar num botão só.
import { describe, expect, it, vi } from "vitest";

import {
  viewMenuHasToggleOn,
  viewMenuIcon,
  viewMenuItems,
  viewMenuLabel,
  type OperatorViewGroup,
} from "../app/presentation/viewMenu";

function groups(over: { layout?: string; density?: string; hide?: boolean; detail?: string } = {}) {
  const selectLayout = vi.fn();
  const selectDensity = vi.fn();
  const toggleHide = vi.fn();
  const list: OperatorViewGroup[] = [
    {
      kind: "choice",
      key: "layout",
      label: "Vista",
      value: over.layout ?? "grid",
      options: [
        { value: "grid", label: "Grade", icon: "lucide:layout-grid" },
        { value: "list", label: "Lista", icon: "lucide:list" },
      ],
      select: selectLayout,
    },
    {
      kind: "choice",
      key: "density",
      label: "Densidade",
      value: over.density ?? "cozy",
      options: [
        { value: "compact", label: "Compacta", icon: "lucide:grid-3x3" },
        { value: "cozy", label: "Padrão", icon: "lucide:layout-grid" },
        { value: "roomy", label: "Ampla", icon: "lucide:grid-2x2" },
      ],
      select: selectDensity,
    },
    {
      kind: "toggle",
      key: "hide",
      label: "Ocultar indisponíveis",
      onLabel: "indisponíveis ocultos",
      checked: over.hide ?? false,
      detail: over.detail,
      icon: "lucide:eye-off",
      toggle: toggleHide,
    },
  ];
  return { list, selectLayout, selectDensity, toggleHide };
}

describe("Exibir no estreito (viewMenu)", () => {
  it("uma seção por escolha, com título e a opção atual marcada; as preferências no fim", () => {
    const { list } = groups({ density: "roomy" });
    const sections = viewMenuItems(list);
    expect(sections).toHaveLength(3);
    expect(sections[0]!.map((item) => [item.label, item.checked])).toEqual([
      ["Vista", undefined],
      ["Grade", true],
      ["Lista", false],
    ]);
    expect(sections[1]!.filter((item) => item.checked).map((item) => item.label)).toEqual(["Ampla"]);
    expect(sections[2]!.map((item) => item.label)).toEqual(["Ocultar indisponíveis"]);
    expect(sections[0]![1]!.icon).toBe("i-lucide-layout-grid");
  });

  it("escolher chama a tela com o valor; o menu fica aberto para a próxima escolha", () => {
    const { list, selectLayout, toggleHide } = groups();
    const sections = viewMenuItems(list);
    sections[0]![2]!.onUpdateChecked!(true);
    expect(selectLayout).toHaveBeenCalledWith("list");
    sections[2]![0]!.onUpdateChecked!(true);
    expect(toggleHide).toHaveBeenCalledWith(true);
    const event = new Event("select", { cancelable: true });
    sections[0]![2]!.onSelect!(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("o ícone do botão é a vista atual; o nome diz o estado inteiro", () => {
    expect(viewMenuIcon(groups().list)).toBe("i-lucide-layout-grid");
    expect(viewMenuIcon(groups({ layout: "list" }).list)).toBe("i-lucide-list");
    expect(viewMenuLabel(groups().list)).toBe("Exibir: Grade, Padrão");
    expect(viewMenuLabel(groups({ hide: true, detail: "3 ocultos" }).list)).toBe(
      "Exibir: Grade, Padrão, indisponíveis ocultos (3 ocultos)",
    );
  });

  it("preferência ligada marca o botão; o complemento só aparece ligada", () => {
    expect(viewMenuHasToggleOn(groups().list)).toBe(false);
    expect(viewMenuHasToggleOn(groups({ hide: true }).list)).toBe(true);
    expect(viewMenuItems(groups({ detail: "3 ocultos" }).list)[2]![0]!.label).toBe("Ocultar indisponíveis");
    expect(viewMenuItems(groups({ hide: true, detail: "3 ocultos" }).list)[2]![0]!.label).toBe(
      "Ocultar indisponíveis (3 ocultos)",
    );
  });

});
