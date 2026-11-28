import { describe, expect, it } from "vitest";

import { contactOwner, mutationFieldErrors } from "../app/utils/mutationFieldErrors";

describe("mutationFieldErrors", () => {
  it("leva a validação canônica ao campo correspondente", () => {
    const error = {
      status: 400,
      data: {
        detail: "O CPF ou CNPJ não confere.",
        field: "document",
        errors: { document: ["O CPF ou CNPJ não confere."] },
      },
    };

    expect(mutationFieldErrors(error)).toEqual({ document: "O CPF ou CNPJ não confere." });
  });

  it("não inventa campo para falha de rede", () => {
    expect(mutationFieldErrors(new Error("offline"))).toEqual({});
  });

  it("lê o dono do contato recusado (GES-13)", () => {
    const error = {
      status: 409,
      data: {
        detail: "Este telefone é de João Oliveira (CLI-003).",
        field: "phone",
        errors: { phone: ["Este telefone é de João Oliveira (CLI-003)."] },
        error: { code: "contact_conflict", owner: { ref: "CLI-003", name: "João Oliveira" } },
      },
    };
    expect(contactOwner(error)).toEqual({ field: "phone", ref: "CLI-003", name: "João Oliveira" });
    expect(contactOwner(new Error("offline"))).toBeNull();
  });
});
