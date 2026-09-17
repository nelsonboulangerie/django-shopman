import { describe, expect, it } from "vitest";
import {
  ORIENTATION_LOCK_COPY,
  orientationFailureCopy,
  orientationFamily,
  orientationLockedCopy,
  orientationLockFailure,
  parseStoredOrientation,
} from "../app/presentation/orientationLock";

describe("orientationLock — regra pura da trava de giro", () => {
  it("trava a FAMÍLIA, não o lado: -primary e -secondary viram a mesma orientação", () => {
    expect(orientationFamily("landscape-primary")).toBe("landscape");
    expect(orientationFamily("landscape-secondary")).toBe("landscape");
    expect(orientationFamily("portrait-primary")).toBe("portrait");
    expect(orientationFamily("portrait-secondary")).toBe("portrait");
    expect(orientationFamily("")).toBeNull();
    expect(orientationFamily(undefined)).toBeNull();
    expect(orientationFamily("natural")).toBeNull();
  });

  it("preferência persistida só sobrevive como família válida", () => {
    expect(parseStoredOrientation("portrait")).toBe("portrait");
    expect(parseStoredOrientation("landscape")).toBe("landscape");
    expect(parseStoredOrientation("landscape-primary")).toBeNull();
    expect(parseStoredOrientation(null)).toBeNull();
    expect(parseStoredOrientation("any")).toBeNull();
  });

  it("recusa fora do app instalado manda instalar; dentro dele, usar o bloqueio do sistema", () => {
    expect(orientationLockFailure({ installed: false, ios: false })).toBe("needs-install");
    expect(orientationLockFailure({ installed: true, ios: false })).toBe("unsupported");
  });

  it("iPhone/iPad nunca recebem 'instale' — lá nem instalado trava", () => {
    expect(orientationLockFailure({ installed: false, ios: true })).toBe("unsupported");
    expect(orientationLockFailure({ installed: true, ios: true })).toBe("unsupported");
  });

  it("a cópia diz o que fazer, sem fingir que travou", () => {
    expect(orientationFailureCopy("unsupported")).toBe(ORIENTATION_LOCK_COPY.unsupported);
    expect(ORIENTATION_LOCK_COPY.unsupported).toContain("bloqueio de rotação do sistema");
    expect(orientationFailureCopy("needs-install")).toBe(ORIENTATION_LOCK_COPY.needsInstall);
    expect(orientationLockedCopy("portrait")).toBe("Giro travado em retrato.");
    expect(orientationLockedCopy("landscape")).toBe("Giro travado em paisagem.");
  });
});
