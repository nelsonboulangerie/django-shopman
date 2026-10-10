import { describe, expect, it } from "vitest";
import { OPERATOR_APPS, operatorAppNamed } from "../appIdentity";

// A frase que cita outro app ("Voltar à Central", "Versão da Central") não pode
// congelar o gênero do rótulo: um "ao" escrito à mão diante de um rótulo feminino diz
// "Voltar ao Central".
describe("operatorAppNamed", () => {
  it("contrai o artigo da identidade com a preposição", () => {
    expect(operatorAppNamed("hub")).toBe("a Central");
    expect(operatorAppNamed("hub", "a")).toBe("à Central");
    expect(operatorAppNamed("hub", "de")).toBe("da Central");
    expect(operatorAppNamed("hub", "em")).toBe("na Central");
    expect(operatorAppNamed("pos", "a")).toBe("ao PDV");
    expect(operatorAppNamed("pos", "de")).toBe("do PDV");
  });

  it("todo app declara um artigo que a contração conhece", () => {
    for (const [ref, identity] of Object.entries(OPERATOR_APPS)) {
      expect(["o", "a", "os", "as"], ref).toContain(identity.article);
    }
  });
});
