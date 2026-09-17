import { describe, expect, it } from "vitest";
import {
  DEVICE_ACTIVITY_COOKIE_NAME,
  DEVICE_ACTIVITY_THROTTLE_MS,
  createDeviceActivityClock,
  deviceActivityCookieDomain,
  parseDeviceActivity,
  type DeviceActivityEnv,
} from "../app/utils/deviceActivity";

/**
 * Navegador de mentira com a regra que importa: um cookie é identificado por
 * (nome, domínio), e o navegador RECUSA `Domain=` que não seja ancestral do host
 * ou que seja sufixo público. `document.cookie` devolve todos os homônimos.
 */
function fakeBrowser(hostname: string, opts: { publicSuffixes?: string[]; secure?: boolean } = {}) {
  let now = Date.parse("2026-09-17T10:00:00Z");
  const jar = new Map<string, string>(); // "domain|name" → value
  const written: string[] = [];
  const env: DeviceActivityEnv = {
    hostname,
    secure: opts.secure ?? true,
    now: () => now,
    readCookies: () => [...jar].map(([key, value]) => `${key.split("|")[1]}=${value}`).join("; "),
    writeCookie(serialized) {
      written.push(serialized);
      const [pair = "", ...attributes] = serialized.split(";").map((part) => part.trim());
      const [name = "", value = ""] = pair.split("=");
      const domainAttribute = attributes.find((attribute) => attribute.toLowerCase().startsWith("domain="));
      const domain = domainAttribute ? domainAttribute.slice(7).replace(/^\./, "") : `host:${hostname}`;
      if (domainAttribute) {
        const ancestor = hostname === domain || hostname.endsWith(`.${domain}`);
        if (!ancestor || opts.publicSuffixes?.includes(domain)) return; // recusado em silêncio
      }
      jar.set(`${domain}|${name}`, value);
    },
  };
  return {
    env,
    jar,
    written,
    advance(ms: number) { now += ms; },
    get now() { return now; },
  };
}

describe("deviceActivityCookieDomain — a zona é o host sem o primeiro rótulo", () => {
  it.each([
    ["pdv.boulangerie.com.br", "boulangerie.com.br"],
    ["GESTOR.boulangerie.com.br.", "boulangerie.com.br"],
    ["pdv.alpha.loja.example", "alpha.loja.example"],
    ["shopman-pos-abc12.ondigitalocean.app", "ondigitalocean.app"],
  ])("%s → %s", (host, zone) => {
    expect(deviceActivityCookieDomain(host)).toBe(zone);
  });

  it.each(["", "localhost", "app.localhost", "127.0.0.1", "::1", "[::1]", "boulangerie.com", "intranet"])(
    "%s → sem zona (host-only)",
    (host) => {
      expect(deviceActivityCookieDomain(host)).toBeNull();
    },
  );
});

describe("parseDeviceActivity", () => {
  const now = 1_000_000;

  it("vale o maior entre homônimos (domínio-pai e host-only antigo)", () => {
    expect(parseDeviceActivity(`a=1; ${DEVICE_ACTIVITY_COOKIE_NAME}=900000; ${DEVICE_ACTIVITY_COOKIE_NAME}=950000`, now)).toBe(950_000);
  });

  it("ignora valor no FUTURO — relógio forjado não desliga a trava", () => {
    expect(parseDeviceActivity(`${DEVICE_ACTIVITY_COOKIE_NAME}=${now + 1}`, now)).toBeNull();
    expect(parseDeviceActivity(`${DEVICE_ACTIVITY_COOKIE_NAME}=${now + 1}; ${DEVICE_ACTIVITY_COOKIE_NAME}=10`, now)).toBe(10);
  });

  it("ignora lixo, zero, negativo e nome parecido", () => {
    expect(parseDeviceActivity(`${DEVICE_ACTIVITY_COOKIE_NAME}=abc; ${DEVICE_ACTIVITY_COOKIE_NAME}=0; ${DEVICE_ACTIVITY_COOKIE_NAME}=-5; x_${DEVICE_ACTIVITY_COOKIE_NAME}=900`, now)).toBeNull();
    expect(parseDeviceActivity("", now)).toBeNull();
  });
});

describe("createDeviceActivityClock", () => {
  it("escreve no domínio-pai, Lax, Secure em https, sem dado além do instante", () => {
    const browser = fakeBrowser("pdv.boulangerie.com.br");
    const clock = createDeviceActivityClock(browser.env);
    expect(clock.mark()).toBe(true);
    expect(browser.written).toEqual([
      `${DEVICE_ACTIVITY_COOKIE_NAME}=${browser.now}; Path=/; Max-Age=86400; SameSite=Lax; Secure; Domain=.boulangerie.com.br`,
    ]);
    expect(clock.read()).toBe(browser.now);
  });

  it("o toque no Gestor é lido pelo PDV (mesmo pote no domínio-pai)", () => {
    const pdv = fakeBrowser("pdv.boulangerie.com.br");
    const gestorEnv: DeviceActivityEnv = { ...pdv.env, hostname: "gestor.boulangerie.com.br" };
    createDeviceActivityClock(gestorEnv).mark();
    expect(createDeviceActivityClock(pdv.env).read()).toBe(pdv.now);
  });

  it("throttle mora no cookie: dentro de 5 s ninguém reescreve, nem de outro app", () => {
    const browser = fakeBrowser("pdv.boulangerie.com.br");
    const pdv = createDeviceActivityClock(browser.env);
    const gestor = createDeviceActivityClock({ ...browser.env, hostname: "gestor.boulangerie.com.br" });
    expect(pdv.mark()).toBe(true);
    for (let i = 0; i < 50; i++) expect(pdv.mark()).toBe(false);
    browser.advance(DEVICE_ACTIVITY_THROTTLE_MS - 1);
    expect(gestor.mark()).toBe(false);
    browser.advance(1);
    expect(gestor.mark()).toBe(true);
    expect(browser.written).toHaveLength(2);
  });

  it("force ignora o throttle (travar re-ancora)", () => {
    const browser = fakeBrowser("pdv.boulangerie.com.br");
    const clock = createDeviceActivityClock(browser.env);
    clock.mark();
    browser.advance(1);
    expect(clock.mark(true)).toBe(true);
    expect(clock.read()).toBe(browser.now);
  });

  it("valor forjado no futuro não segura o throttle: a próxima atividade sobrescreve", () => {
    const browser = fakeBrowser("pdv.boulangerie.com.br");
    browser.jar.set(`boulangerie.com.br|${DEVICE_ACTIVITY_COOKIE_NAME}`, String(browser.now + 10 * 60_000));
    const clock = createDeviceActivityClock(browser.env);
    expect(clock.read()).toBeNull();
    expect(clock.mark()).toBe(true);
    expect(clock.read()).toBe(browser.now);
  });

  it("zona recusada pelo navegador (sufixo público) cai para host-only e não insiste", () => {
    const browser = fakeBrowser("shopman-pos.ondigitalocean.app", { publicSuffixes: ["ondigitalocean.app"] });
    const clock = createDeviceActivityClock(browser.env);
    expect(clock.mark()).toBe(true);
    expect(clock.read()).toBe(browser.now);
    browser.advance(DEVICE_ACTIVITY_THROTTLE_MS);
    expect(clock.mark()).toBe(true);
    expect(browser.written.filter((cookie) => cookie.includes("Domain="))).toHaveLength(1);
    expect(browser.written.at(-1)).not.toContain("Domain=");
  });

  it("localhost/IP ficam host-only (em dev o cookie já atravessa as portas)", () => {
    const browser = fakeBrowser("127.0.0.1", { secure: false });
    const clock = createDeviceActivityClock(browser.env);
    clock.mark();
    expect(browser.written).toEqual([`${DEVICE_ACTIVITY_COOKIE_NAME}=${browser.now}; Path=/; Max-Age=86400; SameSite=Lax`]);
  });

  it("sem cookie (leitura ou escrita lançam) degrada sem quebrar quem chama", () => {
    const broken: DeviceActivityEnv = {
      hostname: "pdv.boulangerie.com.br",
      secure: true,
      now: () => 1,
      readCookies: () => { throw new Error("SecurityError"); },
      writeCookie: () => { throw new Error("SecurityError"); },
    };
    const clock = createDeviceActivityClock(broken);
    expect(clock.read()).toBeNull();
    expect(clock.mark()).toBe(false);
    expect(clock.mark(true)).toBe(false);
  });
});
