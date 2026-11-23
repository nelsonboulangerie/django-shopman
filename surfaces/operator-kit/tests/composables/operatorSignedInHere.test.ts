// A marca "alguém entrou nesta aba" (#3194, P2-15 do plano de excelência do PDV).
// O login recarrega a página, e o `hadSession` da carga anterior morre com ela: a
// sessão que caía logo depois de entrar voltava ao login vazio, sem dizer por quê.
import { afterEach, describe, expect, it } from "vitest";

import { SIGNED_IN_HERE_KEY, useOperatorSession } from "../../app/composables/useOperatorSession";

afterEach(() => {
  window.sessionStorage.clear();
});

describe("useOperatorSession: a aba lembra quem entrou", () => {
  it("entrar marca a aba; sair de propósito apaga a marca", () => {
    const session = useOperatorSession();
    expect(session.signedInHereBefore()).toBe(false);

    session.rememberSignedIn();
    expect(window.sessionStorage.getItem(SIGNED_IN_HERE_KEY)).toBe("1");
    expect(session.signedInHereBefore()).toBe(true);

    session.forgetSignedIn();
    expect(session.signedInHereBefore()).toBe(false);
  });

  it("a antessala que vê alguém identificado também marca a aba", () => {
    const session = useOperatorSession();
    session.markAuthenticated();
    expect(useOperatorSession().signedInHereBefore()).toBe(true);
  });
});
