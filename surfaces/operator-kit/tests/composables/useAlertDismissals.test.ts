// O X do aviso que não mora nas `alerts` do cabeçalho: dispensa só nesta montagem, e a
// chave com a grandeza traz o aviso de volta quando a causa muda.
import { describe, expect, it } from "vitest";

import { ALERT_CLOSE_PROPS, useAlertDismissals } from "../../app/composables/useAlertDismissals";

describe("useAlertDismissals", () => {
  it("o X fecha o aviso daquela chave, e só dela", () => {
    const notices = useAlertDismissals();
    expect(notices.isOpen("attention:H58")).toBe(true);
    notices.onOpen("attention:H58", false);
    expect(notices.isOpen("attention:H58")).toBe(false);
    expect(notices.isOpen("attention:W29")).toBe(true);
  });

  it("abrir não dispensa; chave nova (a causa mudou) é aviso novo", () => {
    const notices = useAlertDismissals();
    notices.onOpen("card-auth:Autorizado", true);
    expect(notices.isOpen("card-auth:Autorizado")).toBe(true);
    notices.close("card-auth:Autorizado");
    expect(notices.isOpen("card-auth:Recusado")).toBe(true);
  });

  it("outra montagem da tela começa com tudo aberto (nada gravado)", () => {
    useAlertDismissals().close("outside-consent");
    expect(useAlertDismissals().isOpen("outside-consent")).toBe(true);
  });

  it("o X é o mesmo das alerts do cabeçalho", () => {
    expect(ALERT_CLOSE_PROPS.close).toEqual({ color: "neutral", variant: "ghost", size: "md" });
  });
});
