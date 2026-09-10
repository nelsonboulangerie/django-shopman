import { expect, it, vi } from "vitest";
import { coalesceRefresh } from "../../app/utils/coalesceRefresh";

it("a hundred SSE triggers during a read produce one follow-up, never overlapping", async () => {
  let release!: () => void;
  const read = vi.fn().mockImplementationOnce(() => new Promise<void>((resolve) => { release = resolve; })).mockResolvedValue(undefined);
  const refresh = coalesceRefresh(read);
  const first = refresh();
  for (let i = 0; i < 100; i++) expect(refresh()).toBe(first);
  expect(read).toHaveBeenCalledTimes(1);
  release();
  await first;
  expect(read).toHaveBeenCalledTimes(2);
});

it("a failed read still drains the queued recovery", async () => {
  let reject!: (error: unknown) => void;
  const read = vi.fn().mockImplementationOnce(() => new Promise<void>((_, fail) => { reject = fail; })).mockResolvedValue(undefined);
  const refresh = coalesceRefresh(read);
  const first = refresh();
  refresh();
  reject(new Error("connection lost"));
  await first;
  expect(read).toHaveBeenCalledTimes(2);
});
