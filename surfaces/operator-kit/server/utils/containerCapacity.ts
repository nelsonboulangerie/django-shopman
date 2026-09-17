// Capacidade do CONTÊINER em que este processo Nitro roda, lida do cgroup v2.
//
// Por que o cgroup e não o `process.memoryUsage()`: o que engasga é o serviço
// inteiro, não este processo. Hoje cada app tem o seu contêiner; depois da
// junção vários processos Nitro (PDV, Cozinha, Pedidos, Produção, Central)
// dividem o MESMO contêiner e o mesmo limite — e o cgroup é a única régua que
// continua certa nos dois mundos. É também a régua que o kernel usa para matar
// o processo por falta de memória.
//
// Honestidade antes de número: sem cgroup v2 legível (dev local, macOS) a
// leitura sai `available: false`, nunca um percentual inventado. Sem limite de
// memória (`memory.max` = "max") não há percentual de memória — há o uso em
// bytes e nada mais.
import { availableParallelism } from "node:os";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup";

/** Janela curta quando não há amostra anterior aproveitável. */
export const CGROUP_CPU_SHORT_WINDOW_MS = 250;
/** Amostra anterior serve de janela se tiver entre 1 s e 2 min (as abas pedem a cada 30–60 s). */
const CPU_WINDOW_MIN_MS = 1_000;
const CPU_WINDOW_MAX_MS = 120_000;

export interface ContainerMemoryReading {
  used_bytes: number;
  limit_bytes: number | null;
  percent: number | null;
}

export interface ContainerCpuReading {
  percent: number | null;
  limit_cores: number;
  window_ms: number;
}

export interface ContainerCapacityReading {
  available: boolean;
  memory: ContainerMemoryReading | null;
  cpu: ContainerCpuReading | null;
  measured_at: string;
}

interface CpuSample {
  usageUsec: number;
  atMs: number;
}

export interface ReadContainerCapacityOptions {
  root?: string;
  nowMs?: () => number;
  sleep?: (ms: number) => Promise<void>;
  cpuCount?: () => number;
}

// Por raiz: o teste usa diretórios falsos e não pode herdar a amostra de outro.
const lastCpuSample = new Map<string, CpuSample>();

export function resetCgroupCpuSamples(): void {
  lastCpuSample.clear();
}

async function readText(root: string, name: string): Promise<string | null> {
  try {
    return await readFile(join(root, name), "utf8");
  } catch {
    // Arquivo ausente = controlador não exposto neste ambiente. Quem chama
    // decide o que isso significa (sem leitura), nunca um zero fingido.
    return null;
  }
}

function roundPercent(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
}

/** `memory.max`: número de bytes, ou "max" (sem limite) → null. */
export function parseCgroupMemoryMax(text: string | null): number | null {
  const value = text?.trim();
  if (!value || value === "max") return null;
  const bytes = Number(value);
  return Number.isFinite(bytes) && bytes > 0 ? bytes : null;
}

/** `memory.current` / contadores simples: inteiro não negativo ou null. */
export function parseCgroupCounter(text: string | null): number | null {
  const value = text?.trim();
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

/** Uma chave de arquivos `chave valor` (`memory.stat`, `cpu.stat`). */
export function parseCgroupKeyedValue(text: string | null, key: string): number | null {
  if (!text) return null;
  for (const line of text.split("\n")) {
    const [name, raw] = line.trim().split(/\s+/);
    if (name === key) return parseCgroupCounter(raw ?? null);
  }
  return null;
}

/** `cpu.max`: "<cota> <período>" → núcleos; "max <período>" (sem cota) → null. */
export function parseCgroupCpuMaxCores(text: string | null): number | null {
  const [quota, period] = (text?.trim() || "").split(/\s+/);
  if (!quota || quota === "max") return null;
  const q = Number(quota);
  const p = Number(period);
  if (!Number.isFinite(q) || !Number.isFinite(p) || q <= 0 || p <= 0) return null;
  return q / p;
}

async function readMemory(root: string): Promise<ContainerMemoryReading | null> {
  const current = parseCgroupCounter(await readText(root, "memory.current"));
  if (current == null) return null;
  // Working set, como o kubelet e o painel da plataforma: cache de arquivo
  // inativo é devolvido pelo kernel sob pressão e não é o que derruba o app.
  const inactiveFile = parseCgroupKeyedValue(await readText(root, "memory.stat"), "inactive_file") ?? 0;
  const used = Math.max(0, current - inactiveFile);
  const limit = parseCgroupMemoryMax(await readText(root, "memory.max"));
  return {
    used_bytes: used,
    limit_bytes: limit,
    percent: limit ? roundPercent((used / limit) * 100) : null,
  };
}

async function readCpuUsage(root: string): Promise<number | null> {
  return parseCgroupKeyedValue(await readText(root, "cpu.stat"), "usage_usec");
}

async function readCpu(root: string, options: Required<ReadContainerCapacityOptions>): Promise<ContainerCpuReading | null> {
  const first = await readCpuUsage(root);
  if (first == null) return null;
  const nowMs = options.nowMs();
  const quotaCores = parseCgroupCpuMaxCores(await readText(root, "cpu.max"));
  // Sem cota, o teto do contêiner é o número de CPUs que ele enxerga.
  const limitCores = quotaCores ?? Math.max(1, options.cpuCount());

  let start: CpuSample | undefined = lastCpuSample.get(root);
  let end: CpuSample = { usageUsec: first, atMs: nowMs };
  const age = start ? nowMs - start.atMs : -1;
  if (!start || age < CPU_WINDOW_MIN_MS || age > CPU_WINDOW_MAX_MS || first < start.usageUsec) {
    // Sem amostra anterior aproveitável: mede uma janela curta agora.
    start = end;
    await options.sleep(CGROUP_CPU_SHORT_WINDOW_MS);
    const second = await readCpuUsage(root);
    if (second == null) return null;
    end = { usageUsec: second, atMs: options.nowMs() };
  }
  lastCpuSample.set(root, end);

  const windowMs = end.atMs - start.atMs;
  if (windowMs <= 0) return { percent: null, limit_cores: limitCores, window_ms: 0 };
  const usedCores = (end.usageUsec - start.usageUsec) / 1000 / windowMs;
  return {
    percent: roundPercent((usedCores / limitCores) * 100),
    limit_cores: Math.round(limitCores * 100) / 100,
    window_ms: Math.round(windowMs),
  };
}

export async function readContainerCapacity(options: ReadContainerCapacityOptions = {}): Promise<ContainerCapacityReading> {
  const resolved: Required<ReadContainerCapacityOptions> = {
    root: options.root ?? DEFAULT_CGROUP_ROOT,
    nowMs: options.nowMs ?? Date.now,
    sleep: options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms))),
    cpuCount: options.cpuCount ?? availableParallelism,
  };
  const memory = await readMemory(resolved.root);
  const cpu = await readCpu(resolved.root, resolved);
  const measuredAt = new Date(resolved.nowMs()).toISOString();
  const hasPercent = memory?.percent != null || cpu?.percent != null;
  return {
    available: hasPercent,
    memory,
    cpu,
    measured_at: measuredAt,
  };
}

/** O maior percentual lido (memória ou CPU) — a régua dos limites do Admin. */
export function capacityPeak(reading: Pick<ContainerCapacityReading, "memory" | "cpu">): number | null {
  const values = [reading.memory?.percent, reading.cpu?.percent].filter((v): v is number => typeof v === "number");
  return values.length ? Math.max(...values) : null;
}
