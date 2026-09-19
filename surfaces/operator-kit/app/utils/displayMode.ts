interface NavigatorWithStandalone extends Navigator {
  standalone?: boolean;
}

/** Os modos em que a superfície roda como APP, sem o chrome do navegador em volta. */
const INSTALLED_DISPLAY_MODES = ["standalone", "fullscreen", "minimal-ui"] as const;

/**
 * A superfície está rodando como app INSTALADO?
 *
 * Fonte única: três lugares perguntavam isso (convite de instalação, trava de giro e
 * agora a navegação entre apps) e duas versões já divergiam — uma olhava só
 * `standalone`, a outra os três modos. `navigator.standalone` é o iOS, que não
 * implementa `display-mode`.
 */
export function isInstalledDisplay(): boolean {
  try {
    if (typeof window === "undefined") return false;
    return INSTALLED_DISPLAY_MODES.some((mode) => window.matchMedia?.(`(display-mode: ${mode})`).matches)
      || Boolean((navigator as NavigatorWithStandalone).standalone);
  } catch {
    return false;
  }
}
