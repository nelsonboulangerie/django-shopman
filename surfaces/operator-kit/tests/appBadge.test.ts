import { describe, expect, it, vi } from "vitest";
import { updateAppBadge } from "../app/utils/appBadge";

describe("updateAppBadge", () => {
  it("espelha a contagem ativa no badge do app", async () => {
    const target = { setAppBadge: vi.fn().mockResolvedValue(undefined) } as unknown as Navigator;
    await updateAppBadge(4, target);
    expect(target.setAppBadge).toHaveBeenCalledWith(4);
  });

  it("limpa o badge quando a caixa zera", async () => {
    const target = { clearAppBadge: vi.fn().mockResolvedValue(undefined) } as unknown as Navigator;
    await updateAppBadge(0, target);
    expect(target.clearAppBadge).toHaveBeenCalledOnce();
  });
});
