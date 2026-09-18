export async function updateAppBadge(count: number, target?: Navigator): Promise<void> {
  const badgeTarget = target || (import.meta.client ? navigator : undefined);
  if (!badgeTarget) return;
  try {
    if (count > 0 && typeof badgeTarget.setAppBadge === "function") {
      await badgeTarget.setAppBadge(count);
    } else if (count <= 0 && typeof badgeTarget.clearAppBadge === "function") {
      await badgeTarget.clearAppBadge();
    }
  } catch {
    // Progressive enhancement: o contador da interface continua canônico.
  }
}
