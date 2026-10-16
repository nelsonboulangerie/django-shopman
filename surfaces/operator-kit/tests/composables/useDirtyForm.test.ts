import { describe, expect, it } from "vitest";
import { reactive, ref } from "vue";

import { useDirtyForm } from "../../app/composables/useDirtyForm";

// O estado sujo lido do formulário reativo: a abertura tira o retrato e, a partir
// dele, cada diferença é "não salvo".

describe("useDirtyForm", () => {
  it("nasce limpo, marca a mudança e volta a limpo quando o valor volta ao retrato", () => {
    const form = reactive({ sku: "", name: "", published: true });
    const { dirty, changedKeys, capture } = useDirtyForm(() => ({ ...form }));

    expect(dirty.value).toBe(false);
    capture();
    expect(dirty.value).toBe(false);

    form.name = "Pão de campanha";
    expect(dirty.value).toBe(true);
    expect(changedKeys.value).toEqual(["name"]);

    form.name = "";
    expect(dirty.value).toBe(false);
    expect(changedKeys.value).toEqual([]);
  });

  it("o retrato é uma cópia: mudar o formulário não reescreve a abertura", () => {
    const tags = ref<string[]>([]);
    const { dirty, capture } = useDirtyForm(() => ({ tags: [...tags.value] }));
    capture();
    tags.value.push("fermentação natural");
    expect(dirty.value).toBe(true);
    capture();
    expect(dirty.value).toBe(false);
  });

  it("o aviso lê a contagem de campos alterados", () => {
    const form = reactive({ sku: "P1", name: "Pão" });
    const { changedKeys, capture } = useDirtyForm(() => ({ ...form }));
    capture();
    form.sku = "P2";
    form.name = "Pão de queijo";
    expect(changedKeys.value).toHaveLength(2);
  });
});
