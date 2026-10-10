import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  WORKSTATION_COPY_KEYS,
  WORKSTATION_KINDS,
  shouldOfferStationSetup,
  workstationKindIcon,
  workstationRadioOptions,
} from "../app/presentation/workstation";

// A fonte única das palavras dos postos é o Python. O kit espelha só as CHAVES; se
// uma divergir, a tela mostraria vazio no lugar do rótulo, e é aqui que isso acusa.
const vocabulary = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../../../shopman/backstage/workstation_vocabulary.py"),
  "utf8",
);

function pythonDictKeys(name: string): string[] {
  const start = vocabulary.indexOf(`${name}: dict[str, str] = {`);
  expect(start).toBeGreaterThanOrEqual(0);
  const body = vocabulary.slice(start, vocabulary.indexOf("\n}", start));
  return [...body.matchAll(/^ {4}"([a-z_]+)":/gm)].map((m) => m[1]!);
}

function pythonConstants(): Record<string, string> {
  return Object.fromEntries(
    [...vocabulary.matchAll(/^([A-Z_]+) = "([a-z_]+)"$/gm)].map((m) => [m[1]!, m[2]!]),
  );
}

describe("postos: espelho das chaves do backend", () => {
  it("os tipos são os mesmos, na mesma ordem", () => {
    const constants = pythonConstants();
    const labelsBlock = vocabulary.slice(vocabulary.indexOf("KIND_LABELS: dict[str, str] = {"));
    const kinds = [...labelsBlock.slice(0, labelsBlock.indexOf("\n}")).matchAll(/^ {4}([A-Z_]+):/gm)].map(
      (m) => constants[m[1]!],
    );
    expect(kinds).toEqual([...WORKSTATION_KINDS]);
  });

  it("as chaves da copy são as mesmas", () => {
    expect(pythonDictKeys("COPY").sort()).toEqual([...WORKSTATION_COPY_KEYS].sort());
  });
});

describe("postos: apresentação", () => {
  it("a opção junta o tipo e a ocupação na segunda linha", () => {
    expect(
      workstationRadioOptions([
        { ref: "pdv-main", label: "Caixa principal", kind_label: "Caixa", hint: "Com gaveta e turno · 1 dispositivo" },
        { ref: "sala-forno", label: "Sala Forno", kind_label: "Sala da Produção", hint: "" },
      ]),
    ).toEqual([
      { value: "pdv-main", label: "Caixa principal", hint: "Caixa · Com gaveta e turno · 1 dispositivo" },
      { value: "sala-forno", label: "Sala Forno", hint: "Sala da Produção" },
    ]);
  });

  it("todo tipo tem ícone, e tipo desconhecido cai num alfinete", () => {
    for (const kind of WORKSTATION_KINDS) expect(workstationKindIcon(kind)).toMatch(/^lucide:/);
    expect(workstationKindIcon("doca")).toBe("lucide:map-pin");
  });

  it("oferece só a quem está destravado num dispositivo que ainda não é posto", () => {
    const base = { canIdentify: true, locked: false, stationRef: "", dismissed: false };
    expect(shouldOfferStationSetup(base)).toBe(true);
    expect(shouldOfferStationSetup({ ...base, canIdentify: false })).toBe(false);
    expect(shouldOfferStationSetup({ ...base, locked: true })).toBe(false);
    expect(shouldOfferStationSetup({ ...base, stationRef: "expedicao" })).toBe(false);
    expect(shouldOfferStationSetup({ ...base, dismissed: true })).toBe(false);
  });
});
