import { describe, expect, it } from "vitest";

import {
  customerGroupsLabel,
  groupMembersActionLabel,
  groupMembersHint,
  groupMembersResultMessage,
  isAlreadyMember,
} from "../app/presentation/customerGroupMembers";
import type { CustomerGroupMembersResponse } from "../app/types/customerGroups";

function response(overrides: Partial<CustomerGroupMembersResponse> = {}): CustomerGroupMembersResponse {
  return {
    outcome: "applied",
    operation: "add",
    group: { ref: "equipe", name: "Equipe" },
    applied: [],
    unchanged: [],
    skipped: [],
    moved_to_default: [],
    default_group: { ref: "varejo", name: "Varejo" },
    ...overrides,
  };
}

describe("groupMembersActionLabel", () => {
  it("o botão diz o resultado, com quantidade e grupo", () => {
    expect(groupMembersActionLabel("add", 3, "Equipe")).toBe("Adicionar 3 clientes ao grupo Equipe");
    expect(groupMembersActionLabel("remove", 1, "Equipe")).toBe("Tirar 1 cliente do grupo Equipe");
  });

  it("nada marcado: o gesto sem o zero", () => {
    expect(groupMembersActionLabel("add", 0, "Equipe")).toBe("Adicionar clientes ao grupo Equipe");
  });

  it("sem grupo escolhido, verbo e quantidade bastam", () => {
    expect(groupMembersActionLabel("add", 2)).toBe("Adicionar 2 clientes");
    expect(groupMembersActionLabel("remove", 2)).toBe("Tirar 2 clientes");
  });
});

describe("groupMembersHint", () => {
  it("adicionar avisa que os outros grupos ficam; tirar, que o padrão recebe quem sobrar", () => {
    expect(groupMembersHint("add")).toBe("Os outros grupos de cada cliente continuam.");
    expect(groupMembersHint("remove")).toBe("Quem ficar sem nenhum grupo volta para o grupo padrão.");
  });
});

describe("groupMembersResultMessage", () => {
  it("adicionar: quem entrou e quem já estava", () => {
    expect(groupMembersResultMessage(response({ applied: ["A", "B"], unchanged: ["C"] }))).toBe(
      "2 clientes entraram no grupo Equipe. 1 já estava nele.",
    );
    expect(groupMembersResultMessage(response({ applied: ["A"] }))).toBe("1 cliente entrou no grupo Equipe.");
  });

  it("repetir o gesto diz que nada mudou", () => {
    expect(groupMembersResultMessage(response({ unchanged: ["A", "B"] }))).toBe(
      "Nada mudou no grupo Equipe. 2 já estavam nele.",
    );
  });

  it("tirar: quem saiu e quem voltou para o grupo padrão", () => {
    expect(
      groupMembersResultMessage(
        response({ operation: "remove", applied: ["A", "B", "C"], moved_to_default: ["B", "C"] }),
      ),
    ).toBe("3 clientes saíram do grupo Equipe. 2 não tinham outro grupo e voltaram para Varejo.");
  });

  it("tirar do grupo padrão quem só tem ele: continua nele", () => {
    expect(
      groupMembersResultMessage(
        response({
          operation: "remove",
          group: { ref: "varejo", name: "Varejo" },
          applied: ["A"],
          skipped: [{ ref: "B", reason: "only_group" }],
        }),
      ),
    ).toBe("1 cliente saiu do grupo Varejo. 1 continua em Varejo, porque é o único grupo dele.");
  });

  it("cadastro unificado ou desativado fica de fora, com o motivo", () => {
    expect(
      groupMembersResultMessage(
        response({ applied: ["A"], skipped: [{ ref: "X", reason: "not_found_or_inactive" }, { ref: "Y", reason: "not_found_or_inactive" }] }),
      ),
    ).toBe("1 cliente entrou no grupo Equipe. 2 cadastros ficaram de fora: foram unificados ou desativados.");
  });

  it("nenhuma frase usa travessão", () => {
    const all = [
      groupMembersResultMessage(response({ applied: ["A"], unchanged: ["B"], skipped: [{ ref: "X", reason: "not_found_or_inactive" }] })),
      groupMembersResultMessage(response({ operation: "remove", applied: ["A"], moved_to_default: ["A"], unchanged: ["B"], skipped: [{ ref: "C", reason: "only_group" }] })),
      groupMembersHint("add"),
      groupMembersHint("remove"),
    ];
    for (const text of all) expect(text).not.toMatch(/[—–]/);
  });
});

describe("customerGroupsLabel e isAlreadyMember", () => {
  const groups = [
    { ref: "equipe", name: "Equipe", is_primary: true },
    { ref: "varejo", name: "Varejo", is_primary: false },
  ];

  it("lista os grupos na ordem do servidor", () => {
    expect(customerGroupsLabel(groups)).toBe("Equipe, Varejo");
    expect(customerGroupsLabel([])).toBe("");
  });

  it("reconhece quem já está no grupo pelo código", () => {
    expect(isAlreadyMember(groups, "equipe")).toBe(true);
    expect(isAlreadyMember(groups, "alianca")).toBe(false);
  });
});
