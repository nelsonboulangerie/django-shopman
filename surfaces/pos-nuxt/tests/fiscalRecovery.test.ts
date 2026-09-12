import { describe, expect, it } from "vitest";
import { fiscalRecoveryUrl } from "../app/presentation/fiscalRecovery";

describe("recuperação da impressão fiscal", () => {
  it("oferece a via do provedor quando a bobina recusa XML indisponível", () => {
    expect(fiscalRecoveryUrl({ detail: "XML indisponível", danfe_url: "https://api.focusnfe.com.br/nota.pdf" })).toBe("https://api.focusnfe.com.br/nota.pdf");
  });
  it.each([null, {}, { danfe_url: "javascript:alert(1)" }, { danfe_url: "http://example.com" }, { danfe_url: "https://user:secret@example.com" }])("recusa URL não utilizável %j", (data) => {
    expect(fiscalRecoveryUrl(data)).toBe("");
  });
});
