import { describe, expect, it } from "vitest";

import { mutationFieldErrors } from "../app/utils/mutationFieldErrors";

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
});
