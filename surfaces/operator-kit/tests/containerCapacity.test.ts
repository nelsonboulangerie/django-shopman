// Leitura do cgroup v2 com arquivos falsos: limite, "max", cota de CPU, janela e
// a ausência de cgroup (dev local) — que precisa dizer "sem leitura", nunca 0%.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CGROUP_CPU_SHORT_WINDOW_MS,
  capacityPeak,
  parseCgroupCpuMaxCores,
  parseCgroupKeyedValue,
  parseCgroupMemoryMax,
  readContainerCapacity,
  resetCgroupCpuSamples,
} from "../server/utils/containerCapacity";

const MiB = 1024 * 1024;
let root: string;

function cgroup(files: Record<string, string>) {
  mkdirSync(root, { recursive: true });
  for (const [name, content] of Object.entries(files)) writeFileSync(join(root, name), content);
}

/** Relógio e sono controlados: cada `sleep` avança o relógio e troca o cpu.stat. */
function clock(startMs: number, usageAfterSleep?: number) {
  let nowMs = startMs;
  const sleep = vi.fn(async (ms: number) => {
    nowMs += ms;
    if (usageAfterSleep != null) writeFileSync(join(root, "cpu.stat"), `usage_usec ${usageAfterSleep}\nuser_usec 1\n`);
  });
  return { nowMs: () => nowMs, sleep, advance: (ms: number) => { nowMs += ms; } };
}

beforeEach(() => {
  root = join(mkdtempSync(join(tmpdir(), "capacity-")), "cgroup");
  resetCgroupCpuSamples();
});
afterEach(() => {
  rmSync(join(root, ".."), { recursive: true, force: true });
});

describe("parsers do cgroup", () => {
  it("memory.max 'max' é sem limite; número é bytes", () => {
    expect(parseCgroupMemoryMax("max\n")).toBeNull();
    expect(parseCgroupMemoryMax("536870912\n")).toBe(536870912);
    expect(parseCgroupMemoryMax(null)).toBeNull();
    expect(parseCgroupMemoryMax("lixo")).toBeNull();
  });

  it("cpu.max com cota vira núcleos; sem cota é null", () => {
    expect(parseCgroupCpuMaxCores("50000 100000\n")).toBe(0.5);
    expect(parseCgroupCpuMaxCores("200000 100000")).toBe(2);
    expect(parseCgroupCpuMaxCores("max 100000")).toBeNull();
    expect(parseCgroupCpuMaxCores(null)).toBeNull();
  });

  it("lê uma chave de arquivo chave-valor", () => {
    const stat = "anon 100\nfile 900\ninactive_file 300\n";
    expect(parseCgroupKeyedValue(stat, "inactive_file")).toBe(300);
    expect(parseCgroupKeyedValue(stat, "active_file")).toBeNull();
  });
});

describe("readContainerCapacity", () => {
  it("memória é o working set (sem cache inativo) sobre o limite do contêiner", async () => {
    cgroup({
      "memory.current": String(400 * MiB),
      "memory.stat": `anon ${200 * MiB}\ninactive_file ${80 * MiB}\n`,
      "memory.max": String(512 * MiB),
      "cpu.stat": "usage_usec 1000000\n",
      "cpu.max": "100000 100000\n",
    });
    const time = clock(1_000_000, 1_000_000 + 125_000);

    const reading = await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 8 });

    expect(reading.available).toBe(true);
    expect(reading.memory).toEqual({ used_bytes: 320 * MiB, limit_bytes: 512 * MiB, percent: 62.5 });
    // 125 ms de CPU numa janela de 250 ms, com 1 núcleo de cota = 50%.
    expect(reading.cpu).toEqual({ percent: 50, limit_cores: 1, window_ms: CGROUP_CPU_SHORT_WINDOW_MS });
    expect(time.sleep).toHaveBeenCalledOnce();
    expect(capacityPeak(reading)).toBe(62.5);
    expect(reading.measured_at).toBe(new Date(1_000_000 + CGROUP_CPU_SHORT_WINDOW_MS).toISOString());
  });

  it("sem limite de memória não inventa percentual", async () => {
    cgroup({
      "memory.current": String(100 * MiB),
      "memory.max": "max\n",
      "cpu.stat": "usage_usec 0\n",
      "cpu.max": "max 100000\n",
    });
    const time = clock(0, 0);

    const reading = await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 2 });

    expect(reading.memory).toEqual({ used_bytes: 100 * MiB, limit_bytes: null, percent: null });
    // Sem cota, o teto é o número de CPUs que o contêiner enxerga.
    expect(reading.cpu?.limit_cores).toBe(2);
    expect(reading.cpu?.percent).toBe(0);
    expect(reading.available).toBe(true);
  });

  it("cota fracionária: 0,5 núcleo inteiro ocupado é 100%, nunca mais", async () => {
    cgroup({ "cpu.stat": "usage_usec 0\n", "cpu.max": "50000 100000\n" });
    const time = clock(0, 400_000); // 400 ms de CPU em 250 ms: ruído de janela

    const reading = await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 4 });

    expect(reading.cpu?.limit_cores).toBe(0.5);
    expect(reading.cpu?.percent).toBe(100);
    expect(reading.memory).toBeNull();
    expect(reading.available).toBe(true);
  });

  it("reaproveita a amostra anterior como janela, sem dormir de novo", async () => {
    cgroup({ "cpu.stat": "usage_usec 0\n", "cpu.max": "100000 100000\n" });
    const time = clock(0, 0);
    await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });
    expect(time.sleep).toHaveBeenCalledTimes(1);

    // 30 s depois, 6 s de CPU consumidos: 20% de um núcleo na janela inteira.
    time.advance(30_000);
    writeFileSync(join(root, "cpu.stat"), "usage_usec 6000000\n");
    const reading = await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });

    expect(time.sleep).toHaveBeenCalledTimes(1);
    expect(reading.cpu).toEqual({ percent: 20, limit_cores: 1, window_ms: 30_000 });
  });

  it("amostra anterior velha demais não vale como janela", async () => {
    cgroup({ "cpu.stat": "usage_usec 0\n", "cpu.max": "100000 100000\n" });
    const time = clock(0, 0);
    await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });
    time.advance(10 * 60_000);

    const reading = await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });

    expect(time.sleep).toHaveBeenCalledTimes(2);
    expect(reading.cpu?.window_ms).toBe(CGROUP_CPU_SHORT_WINDOW_MS);
  });

  it("sem cgroup (dev local, macOS): available false e nenhum número", async () => {
    const time = clock(5_000);

    const reading = await readContainerCapacity({
      root: join(root, "nao-existe"),
      nowMs: time.nowMs,
      sleep: time.sleep,
      cpuCount: () => 8,
    });

    expect(reading).toEqual({
      available: false,
      memory: null,
      cpu: null,
      measured_at: new Date(5_000).toISOString(),
    });
    expect(time.sleep).not.toHaveBeenCalled();
    expect(capacityPeak(reading)).toBeNull();
  });

  it("só uso de memória, sem limite nem CPU: não há percentual, logo não há leitura", async () => {
    cgroup({ "memory.current": String(10 * MiB), "memory.max": "max" });
    const time = clock(0);

    const reading = await readContainerCapacity({ root, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });

    expect(reading.available).toBe(false);
    expect(reading.memory?.used_bytes).toBe(10 * MiB);
  });
});
