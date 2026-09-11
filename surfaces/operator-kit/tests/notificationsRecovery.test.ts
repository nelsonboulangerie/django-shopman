import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { effectScope, ref } from "vue";
import { installNuxtGlobals } from "./support/composableEnv";
import { useNotifications } from "../app/composables/useNotifications";

const env = installNuxtGlobals();
const session = ref<any>({ operator: { id: 1 } });
const scopes: ReturnType<typeof effectScope>[] = [];
function inboxForTest() {
  const scope = effectScope();
  scopes.push(scope);
  return scope.run(() => useNotifications())!;
}
afterEach(() => { for (const scope of scopes.splice(0)) scope.stop(); });
const notice = { pk: 42, title: "Pedido precisa de atenção", is_read: false };
beforeEach(() => {
  env.reset();
  session.value = { operator: { id: 1 } };
  vi.stubGlobal("useNuxtData", () => ({ data: session }));
  vi.stubGlobal("useUserNotifications", () => ({ realtime: ref("polling") }));
});

it("keeps the last confirmed inbox when its refresh fails", async () => {
  const inbox = inboxForTest();
  env.fetchMock.mockResolvedValueOnce({ notifications: [notice], unread_count: 1 });
  await inbox.refresh();
  env.fetchMock.mockRejectedValueOnce({ statusCode: 503 });
  await inbox.refresh();
  expect(inbox.items.value).toEqual([notice]);
  expect(inbox.unread.value).toBe(1);
});


it("drops the previous person's delayed response and clears private context", async () => {
  const inbox = inboxForTest();
  let release!: (value: unknown) => void;
  env.fetchMock.mockReturnValueOnce(new Promise(resolve => { release = resolve; }));
  const pending = inbox.refresh();
  session.value = { operator: { id: 2 } };
  env.fetchMock.mockResolvedValueOnce({ notifications: [], unread_count: 0 });
  release({ notifications: [notice], unread_count: 1 });
  await pending;
  expect(inbox.items.value).toEqual([]);
  expect(inbox.unread.value).toBe(0);
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
});

it("coalesces 100 pushes into one active and one queued read", async () => {
  const inbox = inboxForTest();
  let release!: (value: unknown) => void;
  env.fetchMock.mockReturnValueOnce(new Promise(resolve => { release = resolve; }));
  const pending = inbox.refresh();
  for (let n = 0; n < 100; n++) void inbox.refresh();
  expect(env.fetchMock).toHaveBeenCalledTimes(1);
  env.fetchMock.mockResolvedValueOnce({ notifications: [notice], unread_count: 1 });
  release({ notifications: [], unread_count: 0 });
  await pending;
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
  expect(inbox.items.value).toEqual([notice]);
});

it("does not turn failed read acknowledgement into a successful empty inbox", async () => {
  const inbox = inboxForTest();
  env.fetchMock.mockResolvedValueOnce({ notifications: [notice], unread_count: 1 });
  await inbox.refresh();
  env.fetchMock.mockRejectedValueOnce({ statusCode: 503 });
  await inbox.markRead(42);
  expect(inbox.items.value).toEqual([notice]);
  expect(inbox.error.value).toContain("confirmar a leitura");
});

it("does not query a personal inbox before identification", async () => {
  session.value = null;
  const inbox = inboxForTest();
  await inbox.refresh();
  await inbox.loadSignIns();
  await inbox.markRead(42);
  expect(env.fetchMock).not.toHaveBeenCalled();
});

it("re-gates authentication loss without calling it an empty inbox", async () => {
  const inbox = inboxForTest();
  env.fetchMock.mockRejectedValueOnce({ statusCode: 401 });
  await inbox.refresh();
  expect(inbox.error.value).toContain("Identifique-se");
  expect(env.states.get("operator-session-expired")?.value).toBe(true);
});

it("distinguishes permission denial from temporary unavailability", async () => {
  const inbox = inboxForTest();
  env.fetchMock.mockRejectedValueOnce({ statusCode: 403 });
  await inbox.refresh();
  expect(inbox.error.value).toContain("permissão");
  expect(env.states.get("operator-session-expired")?.value).toBe(false);
});
