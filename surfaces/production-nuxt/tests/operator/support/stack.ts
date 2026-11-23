import type { Browser, BrowserContext } from "@playwright/test";

// A pilha que a suíte usa: URLs vindas do ambiente (playwright.operator.config.ts recusa
// rodar sem elas) e o elenco de dev (shopman/shop/management/commands/setup_operators.py).
// Nada aqui cria estado: os helpers só fazem o que a pessoa faz.
export const stack = {
  django: process.env.OPERATOR_DJANGO_URL!.replace(/\/$/, ""),
  store: process.env.OPERATOR_STORE_URL!.replace(/\/$/, ""),
};

// O elenco, a espera de hidratação e a captura numerada são os do operator-kit (#2580),
// os mesmos do PDV ao vivo e do Gestor. O superusuário nunca entra aqui.
export {
  capture,
  cast,
  settled,
} from "../../../../operator-kit/tests/support/operatorGestures";

/** Os tamanhos em que a Produção é usada de verdade: o tablet deitado da bancada (1024 px,
 *  com toque) e o celular de quem confere de longe (375 px). O kit só traz o celular e o
 *  balcão de 1366; o tablet é da Produção. */
const sizes = {
  tablet: {
    viewport: { width: 1024, height: 768 },
    isMobile: false,
    hasTouch: true,
    deviceScaleFactor: 1,
  },
  phone: {
    viewport: { width: 375, height: 812 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2,
  },
} as const;
export type Size = keyof typeof sizes;

/** Um contexto de navegador é um DISPOSITIVO novo: sem cookie, sem vínculo, sem "Usar sem
 *  vincular" lembrado. Um por dispositivo e por papel: cookies em 127.0.0.1 valem para
 *  todas as portas, e dois papéis no mesmo pote trocariam a sessão um do outro. */
export async function device(
  browser: Browser,
  size: Size,
  baseURL: string,
): Promise<BrowserContext> {
  return browser.newContext({
    ...sizes[size],
    baseURL,
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
  });
}
