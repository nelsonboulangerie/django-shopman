// Um stream por canal na aba (beta 05/11, GES-01): o Gestor abria quatro `/sse/catalog`
// iguais, e em HTTP/1.1 o teto de seis conexões por host travava o resto da tela.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { subscribeSharedEventSource } from "../app/utils/sharedEventSource";
import { FakeEventSource } from "./support/fakeEventSource";

describe("subscribeSharedEventSource", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("quatro assinaturas, um stream; o evento chega a todas; o último a sair fecha", () => {
    const pushes = [vi.fn(), vi.fn(), vi.fn(), vi.fn()];
    const subs = pushes.map((onEvent) =>
      subscribeSharedEventSource({ url: "/sse/catalog", events: ["backstage-catalog-update"], onEvent }),
    );
    expect(FakeEventSource.instances).toHaveLength(1);
    FakeEventSource.instances[0]!.open();
    FakeEventSource.instances[0]!.emit("backstage-catalog-update");
    for (const push of pushes) expect(push).toHaveBeenCalledTimes(1);

    subs.slice(0, 3).forEach((sub) => sub.close());
    expect(FakeEventSource.alive()).toHaveLength(1);
    subs[3]!.close();
    expect(FakeEventSource.alive()).toHaveLength(0);

    // Volta alguém: um stream novo, um só.
    const again = subscribeSharedEventSource({ url: "/sse/catalog", events: ["backstage-catalog-update"], onEvent: vi.fn() });
    expect(FakeEventSource.alive()).toHaveLength(1);
    again.close();
  });

  it("quem chega com o stream aberto já entra ao vivo", () => {
    const first = subscribeSharedEventSource({ url: "/sse/orders", events: ["x"], onEvent: vi.fn() });
    FakeEventSource.instances[0]!.open();
    const onOpen = vi.fn();
    const late = subscribeSharedEventSource({ url: "/sse/orders", events: ["x"], onEvent: vi.fn(), onOpen });
    expect(onOpen).toHaveBeenCalledWith(false);
    first.close();
    late.close();
  });

  it("canais diferentes não se misturam", () => {
    const a = subscribeSharedEventSource({ url: "/sse/catalog", events: ["c"], onEvent: vi.fn() });
    const b = subscribeSharedEventSource({ url: "/sse/orders", events: ["o"], onEvent: vi.fn() });
    expect(FakeEventSource.instances).toHaveLength(2);
    a.close();
    b.close();
  });
});
