/** Serialize refresh triggers, retaining at most one follow-up read during a burst. */
export function coalesceRefresh(read: () => Promise<unknown>) {
  let active: Promise<void> | null = null;
  let queued = false;
  return () => {
    queued = true;
    if (!active) active = (async () => {
      let failure: unknown;
      do {
        queued = false;
        try { await read(); failure = undefined; }
        catch (error) { failure = error; }
      } while (queued);
      if (failure) throw failure;
    })().finally(() => { active = null; });
    return active;
  };
}
