// Relógio de atividade do APARELHO — "quando alguém tocou pela última vez em
// QUALQUER app de operador deste navegador".
//
// Por que existe: a trava do PDV é `logout()` da sessão de operador, e essa sessão
// é UMA para todos os apps do domínio-pai (pdv., gestor., kds., central.…). Medir
// ociosidade só pelo que acontece no PDV derrubava o Gestor em uso ao lado. A
// decisão (Pablo, 17/09/2026): o PDV trava só quando NENHUM app de operador foi
// tocado por N segundos.
//
// Por que cookie e não localStorage/BroadcastChannel: esses dois são por ORIGEM, e
// cada app mora num subdomínio. Um cookie com `Domain=` no domínio-pai é o único
// pote que o JS de pdv. e gestor. leem em comum. Ele guarda só um instante (epoch
// em ms), nada pessoal, e o BFF não o repassa ao Django (`operatorCookies.ts`).
//
// Framework-free: o ambiente (cookie, host, relógio) é injetável para teste.

export const DEVICE_ACTIVITY_COOKIE_NAME = "shopman_operator_activity";

/**
 * Intervalo mínimo entre escritas. O limiar da trava é 60 s e o PDV confere a
 * cada 5 s; escrever mais do que isso só gasta. O preço é a trava poder descer
 * até 5 s antes do último toque de uma rajada — nunca depois.
 */
export const DEVICE_ACTIVITY_THROTTLE_MS = 5_000;

/** Um dia basta: valor mais velho que o limiar já equivale a "ninguém tocou". */
const MAX_AGE_SECONDS = 24 * 60 * 60;

const IPV4 = /^\d{1,3}(?:\.\d{1,3}){3}$/;
const DIGITS = /^\d{1,16}$/;

export interface DeviceActivityEnv {
  /** `document.cookie` (leitura). */
  readCookies(): string;
  /** `document.cookie = …` (escrita de um Set-Cookie). */
  writeCookie(serialized: string): void;
  /** `location.hostname`. */
  hostname: string;
  /** `location.protocol === "https:"`. */
  secure: boolean;
  now(): number;
}

/**
 * Domínio-pai compartilhado pelos apps irmãos — REGRA EXPLÍCITA, não chute:
 * os apps de operador moram em `<app>.<zona>` (é o contrato do deploy:
 * `pdv.boulangerie.com.br`, `gestor.boulangerie.com.br`…), então a zona é o host
 * sem o primeiro rótulo.
 *
 * Sem zona possível (localhost, IP, host de um ou dois rótulos) devolve `null`
 * e o relógio fica host-only — em dev isso já atravessa as portas, porque cookie
 * não distingue porta. Uma zona que o navegador recusa (sufixo público, como
 * `ondigitalocean.app`) é detectada na escrita por releitura e também cai para
 * host-only: o navegador é o juiz, não uma lista nossa.
 */
export function deviceActivityCookieDomain(hostname: string): string | null {
  const host = (hostname || "").trim().toLowerCase().replace(/\.$/, "");
  if (!host || host.includes(":") || IPV4.test(host)) return null;
  if (host === "localhost" || host.endsWith(".localhost")) return null;
  const labels = host.split(".");
  if (labels.length < 3 || labels.some((label) => !label)) return null;
  return labels.slice(1).join(".");
}

/**
 * O último instante registrado no aparelho, ou `null`.
 *
 * Pode haver dois cookies homônimos (o do domínio-pai e um host-only de antes);
 * vale o maior. Valor no FUTURO é ignorado: um relógio forjado ou adiantado não
 * pode desligar a trava para sempre — na dúvida, a trava protege.
 */
export function parseDeviceActivity(cookieHeader: string, now: number): number | null {
  let latest: number | null = null;
  for (const rawPair of (cookieHeader || "").split(";")) {
    const separator = rawPair.indexOf("=");
    if (separator <= 0 || rawPair.slice(0, separator).trim() !== DEVICE_ACTIVITY_COOKIE_NAME) continue;
    const raw = rawPair.slice(separator + 1).trim();
    if (!DIGITS.test(raw)) continue;
    const value = Number(raw);
    if (value <= 0 || value > now) continue;
    if (latest === null || value > latest) latest = value;
  }
  return latest;
}

export interface DeviceActivityClock {
  /** Último toque em qualquer app de operador deste navegador, ou `null`. */
  read(): number | null;
  /**
   * Registra "alguém tocou agora". Sem `force`, não escreve se o aparelho já
   * registrou atividade há menos de `DEVICE_ACTIVITY_THROTTLE_MS` — o throttle
   * mora no próprio cookie, então vale entre abas e apps, não só nesta página.
   * Devolve se escreveu.
   */
  mark(force?: boolean): boolean;
}

export function createDeviceActivityClock(env: DeviceActivityEnv): DeviceActivityClock {
  // Resultado da primeira escrita com `Domain=`: aceita pelo navegador, ou não.
  let sharedDomainAccepted: boolean | null = null;

  function read(): number | null {
    try {
      return parseDeviceActivity(env.readCookies(), env.now());
    } catch {
      return null; // Cookie indisponível: quem lê segue com a própria atividade.
    }
  }

  function mark(force = false): boolean {
    const now = env.now();
    try {
      if (!force) {
        const last = parseDeviceActivity(env.readCookies(), now);
        if (last !== null && now - last < DEVICE_ACTIVITY_THROTTLE_MS) return false;
      }
      const base = `${DEVICE_ACTIVITY_COOKIE_NAME}=${now}; Path=/; Max-Age=${MAX_AGE_SECONDS}; SameSite=Lax${env.secure ? "; Secure" : ""}`;
      const domain = deviceActivityCookieDomain(env.hostname);
      if (domain && sharedDomainAccepted !== false) {
        env.writeCookie(`${base}; Domain=.${domain}`);
        if (sharedDomainAccepted === null) {
          sharedDomainAccepted = parseDeviceActivity(env.readCookies(), now) === now;
        }
        if (sharedDomainAccepted) return true;
      }
      env.writeCookie(base);
      return true;
    } catch {
      return false; // Navegação sem cookie: a trava local do PDV continua valendo.
    }
  }

  return { read, mark };
}

let browserClock: DeviceActivityClock | null = null;

interface BrowserGlobals {
  document?: { cookie: string };
  location?: { hostname: string; protocol: string };
}

/**
 * O relógio deste navegador (lazy; `null` fora do cliente). Lê os globais sem
 * depender da lib DOM: o BFF importa o nome do cookie deste arquivo.
 */
export function deviceActivityClock(): DeviceActivityClock | null {
  const globals = globalThis as BrowserGlobals;
  if (!globals.document) return null;
  browserClock ||= createDeviceActivityClock({
    readCookies: () => globals.document?.cookie ?? "",
    writeCookie: (serialized) => { if (globals.document) globals.document.cookie = serialized; },
    // Sem `location` (teste com `document` avulso) o relógio fica host-only.
    get hostname() { return globals.location?.hostname ?? ""; },
    get secure() { return globals.location?.protocol === "https:"; },
    now: () => Date.now(),
  });
  return browserClock;
}
