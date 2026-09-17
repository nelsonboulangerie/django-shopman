import { beforeEach, describe, expect, it, vi } from "vitest";
import { operatorSessionOnError } from "../app/utils/operatorSession";

// NEM TODO 403 PEDE SENHA.
//
// Esta função está no `onResponseError` de todo board de operador, e tratava
// 401 e 403 como a mesma coisa: `refreshNuxtData("operator-session")`. Três
// recusas chegam com esses status e querem coisas opostas — e o backstage já as
// separa por código (`shopman/backstage/api/permissions.py`), o `httpError.ts`
// do kit já tinha os matchers tipados, e o comentário dele já dizia por escrito
// que aceitar "todo 403" manda o operador digitar senha para uma recusa que
// senha não conserta. Faltava ESTA função usar o que a casa já sabia.

const flagIfUnauthenticated = vi.fn();
const flagIfStationLocked = vi.fn();
const refreshNuxtData = vi.fn();

beforeEach(() => {
  flagIfUnauthenticated.mockReset().mockReturnValue(false);
  flagIfStationLocked.mockReset().mockReturnValue(false);
  refreshNuxtData.mockReset();
  Object.assign(globalThis, {
    useOperatorSession: () => ({ flagIfUnauthenticated }),
    useStationLock: () => ({ flagIfStationLocked }),
    refreshNuxtData,
  });
});

describe("política de recusa das superfícies de operador", () => {
  it("sessão expirada (401) reabre o gate e marca a sessão", () => {
    flagIfUnauthenticated.mockReturnValue(true);

    operatorSessionOnError({ response: { status: 401 } });

    expect(flagIfUnauthenticated).toHaveBeenCalledWith({ status: 401, data: undefined });
    expect(refreshNuxtData).toHaveBeenCalledWith("operator-session");
  });

  it("estação travada levanta o cadeado NA HORA, sem esperar o próximo poll", () => {
    // Entre o servidor trancar e o cliente descobrir, a tela seguia montada com
    // toda leitura em 403 — no PDV isso desenhava um quadro de comandas VAZIO,
    // que no balcão se lê como "as comandas sumiram".
    flagIfStationLocked.mockReturnValue(true);
    const locked = { status: 403, _data: { error: { code: "station_locked" } } };

    operatorSessionOnError({ response: locked });

    expect(flagIfStationLocked).toHaveBeenCalledWith({
      status: 403,
      data: { error: { code: "station_locked" } },
    });
    expect(refreshNuxtData).toHaveBeenCalledWith("operator-session");
  });

  it("permissão negada NÃO manda ninguém digitar senha", () => {
    // A regressão que esta frente conserta: o operador identificado que toca uma
    // ação que não é dele caía numa tela de login — e ele JÁ estava logado.
    const denied = { status: 403, _data: { detail: "Operador sem permissão para esta ação." } };

    operatorSessionOnError({ response: denied });

    expect(flagIfUnauthenticated).toHaveBeenCalledWith({ status: 403, data: denied._data });
    expect(flagIfStationLocked).toHaveBeenCalledWith({ status: 403, data: denied._data });
    expect(refreshNuxtData).not.toHaveBeenCalled();
  });

  it("erro que não é de sessão passa reto", () => {
    operatorSessionOnError({ response: { status: 500 } });
    expect(refreshNuxtData).not.toHaveBeenCalled();
  });

  it("o corpo da resposta chega aos matchers: sem ele, o código não se lê", () => {
    // `status` sozinho não distingue as três recusas. O código vive no CORPO
    // (`_data.error.code`), e é por isso que ele é repassado.
    operatorSessionOnError({ response: { status: 403, _data: { error: { code: "station_locked" } } } });
    expect(flagIfStationLocked.mock.calls[0][0]).toHaveProperty("data.error.code", "station_locked");
  });
});
