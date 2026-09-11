import { describe, expect, it } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useReadMetadata } from "../../app/composables/useReadMetadata";

installNuxtGlobals();

describe("hora da última leitura útil", () => {
  it("falha preserva horário anterior e não usa hora da falha como sucesso", () => {
    const data = ref<{ generated_at?: string; contract_version?: number } | null>({ generated_at: "2026-09-11T12:00:00Z", contract_version: 1 });
    const error = ref<unknown>(null);
    const observed = useReadMetadata(data, error);
    error.value = new Error("read outage");
    data.value = { generated_at: "2026-09-11T12:01:00Z", contract_version: 1 };
    expect(observed.value?.generated_at).toBe("2026-09-11T12:00:00Z");
    data.value = null;
    expect(observed.value?.generated_at).toBe("2026-09-11T12:00:00Z");
    error.value = null;
    data.value = { generated_at: "2026-09-11T12:02:00Z", contract_version: 1 };
    expect(observed.value?.generated_at).toBe("2026-09-11T12:02:00Z");
  });

  it("novo recurso ou servidor antigo não herda marca de leitura fresca", () => {
    const data = ref<{ generated_at?: string; contract_version?: number } | null>({ generated_at: "2026-09-11T12:00:00Z", contract_version: 1 });
    const error = ref<unknown>(null);
    const scope = ref("first");
    const observed = useReadMetadata(data, error, scope);
    scope.value = "second";
    expect(observed.value).toBeNull();
    data.value = {};
    expect(observed.value).toBeNull();
  });
});
