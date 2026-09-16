export function idleReloadPathAllowed(allowedPaths: string[], path: string): boolean {
  return allowedPaths.some((allowed) => allowed === "*"
    || path === allowed
    || path.startsWith(`${allowed.replace(/\/$/, "")}/`));
}

export function shouldApplyKioskUpdate(options: {
  idle: boolean;
  needsRefresh: boolean;
  applying: boolean;
  safeToReload: boolean;
}): boolean {
  return options.safeToReload
    && options.idle
    && options.needsRefresh
    && !options.applying;
}

export async function applyKioskUpdate(
  options: {
    allowedPaths: string[];
    path: string;
    idle: boolean;
    needsRefresh: boolean;
    applying: boolean;
  },
  update: () => Promise<boolean>,
): Promise<boolean> {
  if (!shouldApplyKioskUpdate({
    idle: options.idle,
    needsRefresh: options.needsRefresh,
    applying: options.applying,
    safeToReload: idleReloadPathAllowed(options.allowedPaths, options.path),
  })) return false;
  return update();
}
