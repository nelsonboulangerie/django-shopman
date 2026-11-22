import { closeSync, openSync, readSync, statSync } from "node:fs";
import { expect, type Browser, type BrowserContext } from "@playwright/test";

import { newDevice } from "../../../../operator-kit/tests/support/operatorGestures";
import { syncBrowserClock } from "./clock";

// A pilha que a suíte usa: URLs vindas do ambiente (playwright.operator.config.ts recusa
// rodar sem elas) e os papéis do elenco de dev (shopman/shop/management/commands/
// setup_operators.py). Nada aqui cria estado: os helpers só fazem o que a pessoa faz.
export const stack = {
  django: process.env.OPERATOR_DJANGO_URL!.replace(/\/$/, ""),
  store: process.env.OPERATOR_STORE_URL!.replace(/\/$/, ""),
  kitchen: process.env.OPERATOR_KITCHEN_URL!.replace(/\/$/, ""),
  // A Produção só entra nas jornadas que a pedem (J6); sem ela, essas jornadas pulam.
  production: (process.env.OPERATOR_PRODUCTION_URL || "").replace(/\/$/, ""),
  // O PDV também: só a jornada das Encomendas do PDV (E1) o pede.
  pos: (process.env.OPERATOR_POS_URL || "").replace(/\/$/, ""),
  djangoLog: process.env.OPERATOR_DJANGO_LOG!,
};

// O elenco de setup_operators.py, a espera de hidratação e a captura numerada são os
// do operator-kit (#2580), comuns ao PDV ao vivo. O superusuário nunca entra aqui.
export { capture, cast, settled } from "../../../../operator-kit/tests/support/operatorGestures";

/** Um contexto por papel: o balcão de 1366 px, ou o celular de 375 px da cliente. É o
 *  dispositivo novo do kit: cookies em 127.0.0.1 valem para todas as portas, e dois
 *  papéis no mesmo pote trocariam a sessão um do outro. */
export async function roleContext(browser: Browser, baseURL: string, phone = false, clockAt = ""): Promise<BrowserContext> {
  const context = await newDevice(browser, phone ? "phone" : "counter", baseURL);
  // Com `clockAt`, o navegador conta a mesma hora que o Django (relógio de teste).
  if (clockAt) await syncBrowserClock(context, clockAt);
  return context;
}

/** Onde o log do runserver está agora: o código pedido DEPOIS deste ponto é o nosso. */
export function djangoLogMark(): number {
  return statSync(stack.djangoLog).size;
}

/** O código de entrada que a loja mandou, lido do log do Django da pilha (o sender de
 *  console grava `[DEV] Code for <alvo>: 123456`). É o que o cliente leria no SMS. */
export async function readLoginCode(mark: number): Promise<string> {
  let code = "";
  await expect
    .poll(
      () => {
        const size = statSync(stack.djangoLog).size;
        if (size <= mark) return "";
        const fd = openSync(stack.djangoLog, "r");
        try {
          const buffer = Buffer.alloc(size - mark);
          readSync(fd, buffer, 0, buffer.length, mark);
          const found = [...buffer.toString("utf8").matchAll(/\[DEV\] Code for .*?: (\d{6})/g)];
          code = found.at(-1)?.[1] ?? "";
          return code;
        } finally {
          closeSync(fd);
        }
      },
      { message: `código de entrada no log do Django (${stack.djangoLog})`, timeout: 30_000 },
    )
    .toMatch(/^\d{6}$/);
  return code;
}

/** Um celular que nunca comprou na loja: DDD 43, nono dígito, sorteado por execução. */
export function newCustomerPhone(): string {
  const tail = String(Date.now() % 100_000_000).padStart(8, "0");
  return `439${tail}`;
}
