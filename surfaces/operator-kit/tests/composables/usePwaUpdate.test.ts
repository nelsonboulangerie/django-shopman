import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import {
  bindPwaUpdateRegistration,
  usePwaUpdate,
} from "../../app/composables/usePwaUpdate";

afterEach(() => bindPwaUpdateRegistration(null));

describe("usePwaUpdate", () => {
  it("fica inerte quando a capability não registrou um worker", async () => {
    const update = usePwaUpdate();
    expect(update.needRefresh.value).toBe(false);
    await expect(update.update()).resolves.toBe(false);
  });

  it("expõe worker em espera e só aplica quando update é chamado", async () => {
    const needRefresh = ref(false);
    const updateServiceWorker = vi.fn().mockResolvedValue(undefined);
    bindPwaUpdateRegistration({ needRefresh, updateServiceWorker });
    const update = usePwaUpdate();

    needRefresh.value = true;
    expect(update.needRefresh.value).toBe(true);
    expect(updateServiceWorker).not.toHaveBeenCalled();
    await expect(update.update()).resolves.toBe(true);
    expect(updateServiceWorker).toHaveBeenCalledWith(true);
  });

  it("não propaga falha da atualização", async () => {
    bindPwaUpdateRegistration({
      needRefresh: ref(true),
      updateServiceWorker: vi.fn().mockRejectedValue(new Error("failed")),
    });
    await expect(usePwaUpdate().update()).resolves.toBe(false);
  });
});
