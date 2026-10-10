// Pure logic ainda usada pelo PDV: o auto-lock de kiosk (usePosAutoLock). A
// identificação (PIN/crachá) e o teclado do PIN moram no kit (useOperatorLock,
// OperatorLock, OperatorPinPad).
// Framework-free para ser testável sem runtime Nuxt.

/** Whether the terminal should auto-lock given idle time. timeoutSec<=0 disables. */
export function isIdleBeyond(lastActivityMs: number, nowMs: number, timeoutSec: number): boolean {
  if (timeoutSec <= 0) return false;
  return nowMs - lastActivityMs >= timeoutSec * 1000;
}
