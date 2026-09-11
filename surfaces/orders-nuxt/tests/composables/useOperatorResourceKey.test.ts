import { expect, it, vi } from "vitest";
import { ref } from "vue";
import { useOperatorResourceKey } from "../../app/composables/useOperatorResourceKey";

it("separa cache por pessoa e recurso, inclusive antes de identificar", () => {
  const data = ref<{ operator?: { id: number } }>({});
  vi.stubGlobal("useNuxtData", () => ({ data }));
  const anonymous = useOperatorResourceKey("detail-A");
  data.value = { operator: { id: 1 } };
  const first = useOperatorResourceKey("detail-A");
  expect(first).not.toBe(useOperatorResourceKey("detail-B"));
  data.value = { operator: { id: 2 } };
  expect(first).not.toBe(useOperatorResourceKey("detail-A"));
  expect(anonymous).not.toBe(first);
});
