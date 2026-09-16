export function shouldApplyKioskUpdate(options: {
  idle: boolean;
  needsRefresh: boolean;
  applying: boolean;
}): boolean {
  return options.idle && options.needsRefresh && !options.applying;
}
