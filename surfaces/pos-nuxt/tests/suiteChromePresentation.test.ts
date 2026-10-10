// V4-PDV: as decisões puras da camada da suíte no PDV (ao vivo do cabeçalho e o
// ponto da coleção nos chips da grade).
import { describe, expect, it } from "vitest";

import { posLiveStatus } from "../app/presentation/events";
import { collectionColorMap } from "../app/presentation/catalog";
import type { POSProductProjection } from "../app/types/pos";

describe("ao vivo do cabeçalho do PDV", () => {
  it("com o push vivo, só o ponto e a hora", () => {
    expect(posLiveStatus({ online: true, realtime: "live" }).tone).toBe("live");
  });

  it("sem o push, diz a cadência calma; sem rede, diz por extenso", () => {
    expect(posLiveStatus({ online: true, realtime: "polling" })).toMatchObject({ tone: "calm", label: "Atualiza sozinho a cada 60 s" });
    expect(posLiveStatus({ online: true, realtime: "connecting" }).tone).toBe("calm");
    expect(posLiveStatus({ online: false, realtime: "live" })).toMatchObject({ tone: "off", label: "Sem conexão" });
  });
});

describe("cor da coleção nos chips da grade", () => {
  const product = (ref: string, color: string) =>
    ({ sku: `${ref}-${color}`, collection_ref: ref, collection_color: color }) as unknown as POSProductProjection;

  it("a primeira cor configurada vale, e coleção sem cor fica de fora", () => {
    const colors = collectionColorMap([product("doces", "#B8577A"), product("doces", "#000000"), product("paes", ""), product("", "#111111")]);
    expect(colors.get("doces")).toBe("#B8577A");
    expect(colors.has("paes")).toBe(false);
    expect(colors.size).toBe(1);
  });
});
