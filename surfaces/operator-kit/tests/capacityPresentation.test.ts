import { describe, expect, it } from "vitest";
import {
  capacityAriaLabel,
  capacityGuidance,
  capacityLevel,
  capacitySourceText,
  capacitySummary,
  capacityThresholdsText,
  capacityUpdatedAgo,
} from "../app/presentation/capacity";
import type { CapacityResponse } from "../app/types/capacity";

const THRESHOLDS = { attention_percent: 75, critical_percent: 90, sustain_minutes: 5 };

function reading(memory: number | null, cpu: number | null, overrides: Partial<CapacityResponse> = {}): CapacityResponse {
  return {
    service: "pos",
    available: true,
    source: "cgroup-v2",
    memory: { used_bytes: 1, limit_bytes: 2, percent: memory },
    cpu: { percent: cpu, limit_cores: 1, window_ms: 30_000 },
    measured_at: "2026-09-17T15:00:00.000Z",
    level: "normal",
    thresholds: THRESHOLDS,
    ...overrides,
  };
}

describe("capacityLevel — cor pelos limites do Admin, pelo MAIOR entre memória e CPU", () => {
  it.each([
    [62, 18, "normal"],
    [74.9, 10, "normal"],
    [75, 10, "attention"],
    [20, 89, "attention"],
    [90, 10, "critical"],
    [30, 97, "critical"],
  ])("memória %s%% · CPU %s%% → %s", (memory, cpu, level) => {
    expect(capacityLevel(reading(memory, cpu))).toBe(level);
  });

  it("os limites vêm da resposta, não do código", () => {
    const tight = { attention_percent: 50, critical_percent: 60, sustain_minutes: 1 };
    expect(capacityLevel(reading(55, 10, { thresholds: tight }))).toBe("attention");
  });

  it("sem leitura ou sem limites é 'sem leitura', nunca verde", () => {
    expect(capacityLevel(null)).toBe("unknown");
    expect(capacityLevel(reading(95, 95, { available: false }))).toBe("unknown");
    expect(capacityLevel(reading(null, null))).toBe("unknown");
    expect(capacityLevel(reading(95, 95, { thresholds: null }))).toBe("unknown");
  });
});

describe("textos em pt-BR", () => {
  it("resumo com os dois números", () => {
    expect(capacitySummary(reading(62.4, 18.2))).toBe("Memória 62% · CPU 18%");
    expect(capacitySummary(reading(null, 18))).toBe("Memória sem leitura · CPU 18%");
    expect(capacitySummary(reading(1, 1, { available: false }))).toBe(
      "Este ambiente não informa a capacidade do serviço.",
    );
  });

  it("memória sem limite conhecido sai em MB, nunca em percentual inventado", () => {
    const noLimit = reading(null, 18, {
      source: "proc",
      memory: { used_bytes: 1_536 * 1024 * 1024, limit_bytes: null, percent: null },
    });
    expect(capacitySummary(noLimit)).toBe("Memória 1.536 MB · CPU 18%");
    expect(capacitySummary(reading(null, 18, { memory: null }))).toBe("Memória sem leitura · CPU 18%");
  });

  it("de onde veio o número, sem jargão — e nada quando não há leitura", () => {
    expect(capacitySourceText(reading(50, 10, { source: "cgroup-v2" }))).toBe("Medido pelo sistema do contêiner.");
    expect(capacitySourceText(reading(50, 10, { source: "cgroup-v1" }))).toBe("Medido pelo sistema do contêiner.");
    expect(capacitySourceText(reading(50, 10, { source: "proc" }))).toBe("Estimado pelos processos do serviço.");
    expect(capacitySourceText(reading(50, 10, { source: "none", available: false }))).toBe("");
    expect(capacitySourceText(reading(50, 10, { source: "proc", available: false }))).toBe("");
    expect(capacitySourceText(null)).toBe("");
  });

  it("há quanto tempo foi lido", () => {
    const at = Date.parse("2026-09-17T15:00:00.000Z");
    expect(capacityUpdatedAgo("2026-09-17T15:00:00.000Z", at + 2_000)).toBe("atualizado agora");
    expect(capacityUpdatedAgo("2026-09-17T15:00:00.000Z", at + 20_000)).toBe("atualizado há 20 s");
    expect(capacityUpdatedAgo("2026-09-17T15:00:00.000Z", at + 150_000)).toBe("atualizado há 2 min");
    expect(capacityUpdatedAgo("2026-09-17T15:00:00.000Z", at + 2 * 3_600_000)).toBe("atualizado há 2 h");
    expect(capacityUpdatedAgo(undefined, at)).toBe("");
  });

  it("orientação diz a duração do Admin antes de avisar o gestor", () => {
    expect(capacityGuidance("critical", THRESHOLDS)).toContain("Se continuar por 5 min, o gestor é avisado.");
    expect(capacityGuidance("attention", THRESHOLDS)).toContain("lentas no pico");
    expect(capacityThresholdsText(THRESHOLDS)).toBe("Atenção a partir de 75% · crítico a partir de 90%");
  });

  it("rótulo acessível carrega estado e números — a cor nunca é a única pista", () => {
    expect(capacityAriaLabel(reading(93, 20), "critical")).toBe(
      "Capacidade do serviço: Crítica — Memória 93% · CPU 20%",
    );
    expect(capacityAriaLabel(null, "unknown")).toBe("Capacidade do serviço: Sem leitura");
  });
});
