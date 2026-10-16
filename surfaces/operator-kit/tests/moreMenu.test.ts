import { describe, expect, it } from "vitest";

import { moreMenuActionCount, moreMenuGroups, moreMenuItem } from "../app/presentation/moreMenu";

describe("⋯ único: os itens como dados", () => {
  it("lista simples vira um grupo; lista de grupos fica como está", () => {
    expect(moreMenuGroups([{ label: "Atualizar" }])).toEqual([[{ label: "Atualizar" }]]);
    expect(moreMenuGroups([[{ label: "A" }], [{ label: "B" }]])).toEqual([[{ label: "A" }], [{ label: "B" }]]);
  });

  it("grupo vazio, ou só com o rótulo, some", () => {
    const groups = moreMenuGroups([[{ type: "label", label: "Ordenar" }], [], [{ label: "Exportar CSV" }]]);
    expect(groups).toEqual([[{ label: "Exportar CSV" }]]);
    expect(moreMenuGroups([])).toEqual([]);
  });

  it("a ação que não pode diz por quê, escrito sob o rótulo", () => {
    expect(moreMenuItem({ label: "Voltar para a Cozinha", disabled: true, reason: "A Cozinha já fechou." })).toEqual({
      label: "Voltar para a Cozinha",
      disabled: true,
      description: "A Cozinha já fechou.",
    });
  });

  it("o motivo só vale com disabled, e não apaga uma descrição escrita", () => {
    expect(moreMenuItem({ label: "Atualizar", reason: "sobra" })).toEqual({ label: "Atualizar" });
    expect(
      moreMenuItem({ label: "X", disabled: true, reason: "motivo", description: "descrição própria" }).description,
    ).toBe("descrição própria");
  });

  it("as chaves do kit (prioridade, busca) não chegam ao menu", () => {
    const item = moreMenuItem({ label: "Buscar", priority: 1, search: true } as never);
    expect(item).toEqual({ label: "Buscar" });
  });

  it("conta só ações, não rótulos nem separadores", () => {
    expect(
      moreMenuActionCount([
        [{ type: "label", label: "Leitura" }, { label: "Atualizar" }],
        [{ type: "separator" }, { label: "Cancelar", color: "error" }],
      ]),
    ).toBe(2);
  });
});
