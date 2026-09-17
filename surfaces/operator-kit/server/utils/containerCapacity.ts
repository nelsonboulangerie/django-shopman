// Capacidade do CONTÊINER em que este processo Nitro roda.
//
// Por que o contêiner e não o `process.memoryUsage()`: o que engasga é o serviço
// inteiro, não este processo. Com a junção dos apps em dois serviços, vários
// processos Nitro (PDV, Cozinha, Pedidos, Produção, Central) e o roteador
// dividem o MESMO contêiner e o mesmo limite.
//
// Três réguas, tentadas nesta ordem, e a leitura diz qual valeu (`source`):
//
// 1. `cgroup-v2` — `/sys/fs/cgroup/memory.current`, `cpu.stat`… É a régua que o
//    kernel usa para matar o processo por falta de memória.
// 2. `cgroup-v1` — `/sys/fs/cgroup/memory/memory.usage_in_bytes`,
//    `cpuacct.usage`, `cpu.cfs_quota_us`. O grupo do processo sai de
//    `/proc/self/cgroup`: tenta o caminho relativo e depois a raiz da hierarquia.
// 3. `proc` — sem cgroup legível (sandbox tipo gVisor no App Platform): soma o
//    `VmRSS` e o `utime+stime` de TODOS os processos visíveis. Dentro do
//    contêiner o namespace de PID só mostra os dele; se aparecer processo de
//    host (`kthreadd`, centenas de PIDs), a régua é recusada. É estimativa: o
//    RSS somado conta duas vezes a memória compartilhada entre processos.
//
// Honestidade antes de número: nenhuma régua legível (dev local, macOS) → a
// leitura sai `available: false`, nunca um percentual inventado. Sem limite de
// memória conhecido não há percentual de memória — há o uso em bytes e nada mais.
// O limite vem do cgroup; na falta dele, da env que o deploy declara
// (`SHOPMAN_CONTAINER_MEMORY_LIMIT_BYTES`); no `proc`, também do `MemTotal`
// quando ele tem tamanho de contêiner, não de máquina.
//
// Diagnóstico sem console: a PRIMEIRA leitura de cada processo escreve uma linha
// JSON `capacity.probe` no stdout (quais caminhos existem, qual régua valeu). É
// assim que se confirma no log de runtime da plataforma o que o contêiner expõe.
import { availableParallelism } from "node:os";
import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";

export const DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup";
export const DEFAULT_PROC_ROOT = "/proc";

export const MEMORY_LIMIT_ENV = "SHOPMAN_CONTAINER_MEMORY_LIMIT_BYTES";
export const CPU_CORES_ENV = "SHOPMAN_CONTAINER_CPU_CORES";

/** Janela curta quando não há amostra anterior aproveitável. */
export const CGROUP_CPU_SHORT_WINDOW_MS = 250;
/** Amostra anterior serve de janela se tiver entre 1 s e 2 min (as abas pedem a cada 30–60 s). */
const CPU_WINDOW_MIN_MS = 1_000;
const CPU_WINDOW_MAX_MS = 120_000;

/** cgroup v1 escreve "sem limite" como um número absurdo (9223372036854771712). */
const CGROUP_V1_UNLIMITED_BYTES = 2 ** 60;
/** `MemTotal` acima disto é memória de máquina, não limite de contêiner. */
export const PLAUSIBLE_CONTAINER_MEMORY_BYTES = 16 * 1024 ** 3;
/** Mais PIDs visíveis que isto não é o namespace de um contêiner de apps. */
export const PROC_MAX_VISIBLE_PIDS = 256;
/** USER_HZ: fixo em 100 na ABI do Linux para x86-64 e arm64 (e no gVisor). */
const PROC_TICKS_PER_SECOND = 100;

export type CapacitySource = "cgroup-v2" | "cgroup-v1" | "proc" | "none";
type LimitOrigin = "cgroup" | "env" | "meminfo" | "none";
type CoresOrigin = "cgroup" | "env" | "cpus";

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
  source: CapacitySource;
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
  procRoot?: string;
  env?: Record<string, string | undefined>;
  nowMs?: () => number;
  sleep?: (ms: number) => Promise<void>;
  cpuCount?: () => number;
  log?: (line: string) => void;
  pid?: number;
}

type Resolved = Required<ReadContainerCapacityOptions>;

// Por régua e diretório: o teste usa árvores falsas e não pode herdar a amostra de outra.
const lastCpuSample = new Map<string, CpuSample>();
let probeLogged = false;

/** Esquece as amostras de CPU e o log de sondagem (só testes). */
export function resetContainerCapacityState(): void {
  lastCpuSample.clear();
  probeLogged = false;
}

async function readText(path: string): Promise<string | null> {
  try {
    return await readFile(path, "utf8");
  } catch {
    // Arquivo ausente = controlador não exposto neste ambiente. Quem chama
    // decide o que isso significa (sem leitura), nunca um zero fingido.
    return null;
  }
}

async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

function roundPercent(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
}

// ── parsers ────────────────────────────────────────────────────────────────

/** `memory.max`: número de bytes, ou "max" (sem limite) → null. */
export function parseCgroupMemoryMax(text: string | null): number | null {
  const value = text?.trim();
  if (!value || value === "max") return null;
  const bytes = Number(value);
  return Number.isFinite(bytes) && bytes > 0 ? bytes : null;
}

/** `memory.limit_in_bytes` (v1): o "sem limite" é um número perto de 2^63 → null. */
export function parseCgroupV1MemoryLimit(text: string | null): number | null {
  const bytes = parseCgroupMemoryMax(text);
  return bytes != null && bytes < CGROUP_V1_UNLIMITED_BYTES ? bytes : null;
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

/** `cpu.cfs_quota_us` + `cpu.cfs_period_us` (v1): cota -1 = sem cota → null. */
export function parseCgroupV1CpuCores(quotaText: string | null, periodText: string | null): number | null {
  const quota = Number(quotaText?.trim());
  const period = Number(periodText?.trim());
  if (!Number.isFinite(quota) || !Number.isFinite(period) || quota <= 0 || period <= 0) return null;
  return quota / period;
}

export interface ProcCgroupLine {
  controllers: string[];
  path: string;
}

/** `/proc/self/cgroup`: "4:memory:/docker/abc", "3:cpu,cpuacct:/…", "0::/" (v2). */
export function parseProcSelfCgroup(text: string | null): ProcCgroupLine[] {
  if (!text) return [];
  const lines: ProcCgroupLine[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const first = line.indexOf(":");
    const second = first === -1 ? -1 : line.indexOf(":", first + 1);
    if (second === -1) continue;
    const controllers = line.slice(first + 1, second).split(",").filter(Boolean);
    lines.push({ controllers, path: line.slice(second + 1) || "/" });
  }
  return lines;
}

/** `Name:` e `VmRSS:` de `/proc/<pid>/status`. Thread de kernel não tem VmRSS. */
export function parseProcStatus(text: string | null): { name: string | null; rssBytes: number | null } {
  if (!text) return { name: null, rssBytes: null };
  let name: string | null = null;
  let rssBytes: number | null = null;
  for (const line of text.split("\n")) {
    if (line.startsWith("Name:")) name = line.slice(5).trim();
    else if (line.startsWith("VmRSS:")) {
      const kb = Number(line.slice(6).trim().split(/\s+/)[0]);
      if (Number.isFinite(kb) && kb >= 0) rssBytes = kb * 1024;
    }
  }
  return { name, rssBytes };
}

/** `utime + stime` (campos 14 e 15) de `/proc/<pid>/stat`, em ticks. O nome pode ter espaço e parêntese. */
export function parseProcStatTicks(text: string | null): number | null {
  if (!text) return null;
  const close = text.lastIndexOf(")");
  if (close === -1) return null;
  const fields = text.slice(close + 1).trim().split(/\s+/);
  // Depois do ")" o primeiro campo é o 3 (estado): utime = 14, stime = 15.
  const utime = Number(fields[11]);
  const stime = Number(fields[12]);
  if (!Number.isFinite(utime) || !Number.isFinite(stime) || utime < 0 || stime < 0) return null;
  return utime + stime;
}

/** `MemTotal:` de `/proc/meminfo`, em bytes. */
export function parseMemInfoTotal(text: string | null): number | null {
  const match = text?.match(/^MemTotal:\s+(\d+)\s*kB/m);
  if (!match) return null;
  const bytes = Number(match[1]) * 1024;
  return bytes > 0 ? bytes : null;
}

/** Env numérica positiva; qualquer outra coisa é "não declarada". */
export function parsePositiveEnv(raw: string | undefined): number | null {
  const value = Number(raw?.trim());
  return raw != null && raw.trim() !== "" && Number.isFinite(value) && value > 0 ? value : null;
}

// ── réguas ─────────────────────────────────────────────────────────────────

interface MemoryRaw {
  used: number;
  limit: number | null;
}

interface Strategy {
  source: Exclude<CapacitySource, "none">;
  /** Chave da amostra de CPU guardada entre leituras. */
  sampleKey: string;
  memory(): Promise<MemoryRaw | null>;
  cpuUsageUsec(): Promise<number | null>;
  cpuQuotaCores(): Promise<number | null>;
}

/** Diretórios candidatos: o caminho do grupo relativo à hierarquia e, depois, a raiz dela. */
function candidateDirs(base: string, relative: string | undefined): string[] {
  const dirs: string[] = [];
  if (relative && relative !== "/") dirs.push(join(base, relative));
  dirs.push(base);
  return dirs;
}

function v1Path(lines: ProcCgroupLine[], controller: string): string | undefined {
  return lines.find((line) => line.controllers.includes(controller))?.path;
}

async function firstDirWith(dirs: string[], file: string, parse: (text: string | null) => number | null) {
  for (const dir of dirs) {
    if (parse(await readText(join(dir, file))) != null) return dir;
  }
  return null;
}

async function detectCgroupV2(options: Resolved, lines: ProcCgroupLine[]): Promise<Strategy | null> {
  const unified = lines.find((line) => line.controllers.length === 0)?.path;
  for (const dir of candidateDirs(options.root, unified)) {
    const memoryText = await readText(join(dir, "memory.current"));
    const cpuText = await readText(join(dir, "cpu.stat"));
    if (parseCgroupCounter(memoryText) == null && parseCgroupKeyedValue(cpuText, "usage_usec") == null) continue;
    return {
      source: "cgroup-v2",
      sampleKey: `cgroup-v2:${dir}`,
      async memory() {
        const current = parseCgroupCounter(await readText(join(dir, "memory.current")));
        if (current == null) return null;
        // Working set, como o kubelet e o painel da plataforma: cache de arquivo
        // inativo é devolvido pelo kernel sob pressão e não é o que derruba o app.
        const inactive = parseCgroupKeyedValue(await readText(join(dir, "memory.stat")), "inactive_file") ?? 0;
        return {
          used: Math.max(0, current - inactive),
          limit: parseCgroupMemoryMax(await readText(join(dir, "memory.max"))),
        };
      },
      async cpuUsageUsec() {
        return parseCgroupKeyedValue(await readText(join(dir, "cpu.stat")), "usage_usec");
      },
      async cpuQuotaCores() {
        return parseCgroupCpuMaxCores(await readText(join(dir, "cpu.max")));
      },
    };
  }
  return null;
}

const V1_CPUACCT_MOUNTS = ["cpu,cpuacct", "cpuacct", "cpuacct,cpu"];
const V1_CPU_MOUNTS = ["cpu,cpuacct", "cpu", "cpuacct,cpu"];

async function detectCgroupV1(options: Resolved, lines: ProcCgroupLine[]): Promise<Strategy | null> {
  const memoryDir = await firstDirWith(
    candidateDirs(join(options.root, "memory"), v1Path(lines, "memory")),
    "memory.usage_in_bytes",
    parseCgroupCounter,
  );
  const cpuacctDirs = V1_CPUACCT_MOUNTS.flatMap((mount) =>
    candidateDirs(join(options.root, mount), v1Path(lines, "cpuacct")),
  );
  const cpuacctDir = await firstDirWith(cpuacctDirs, "cpuacct.usage", parseCgroupCounter);
  if (!memoryDir && !cpuacctDir) return null;
  const cpuDirs = V1_CPU_MOUNTS.flatMap((mount) => candidateDirs(join(options.root, mount), v1Path(lines, "cpu")));

  return {
    source: "cgroup-v1",
    sampleKey: `cgroup-v1:${cpuacctDir ?? memoryDir}`,
    async memory() {
      if (!memoryDir) return null;
      const usage = parseCgroupCounter(await readText(join(memoryDir, "memory.usage_in_bytes")));
      if (usage == null) return null;
      const statText = await readText(join(memoryDir, "memory.stat"));
      // `total_inactive_file` inclui os subgrupos; `inactive_file` é só o grupo.
      const inactive =
        parseCgroupKeyedValue(statText, "total_inactive_file") ?? parseCgroupKeyedValue(statText, "inactive_file") ?? 0;
      return {
        used: Math.max(0, usage - inactive),
        limit: parseCgroupV1MemoryLimit(await readText(join(memoryDir, "memory.limit_in_bytes"))),
      };
    },
    async cpuUsageUsec() {
      if (!cpuacctDir) return null;
      const nanoseconds = parseCgroupCounter(await readText(join(cpuacctDir, "cpuacct.usage")));
      return nanoseconds == null ? null : nanoseconds / 1000;
    },
    async cpuQuotaCores() {
      for (const dir of cpuDirs) {
        const quota = await readText(join(dir, "cpu.cfs_quota_us"));
        if (quota == null) continue;
        return parseCgroupV1CpuCores(quota, await readText(join(dir, "cpu.cfs_period_us")));
      }
      return null;
    },
  };
}

interface ProcScan {
  /** PIDs numéricos em `/proc`; null quando `/proc` não é legível. */
  pids: string[] | null;
  /** Viu processo de host (thread de kernel ou PIDs demais): a régua não vale. */
  hostVisible: boolean;
}

async function listPids(procRoot: string): Promise<ProcScan> {
  let entries: string[];
  try {
    entries = await readdir(procRoot);
  } catch {
    return { pids: null, hostVisible: false };
  }
  const pids = entries.filter((name) => /^\d+$/.test(name));
  return { pids, hostVisible: pids.length > PROC_MAX_VISIBLE_PIDS };
}

async function sumProcMemory(procRoot: string, pids: string[]): Promise<{ rss: number; counted: number; host: boolean }> {
  let rss = 0;
  let counted = 0;
  for (const pid of pids) {
    // Processo que morreu entre o readdir e a leitura some da soma, sem erro.
    const status = parseProcStatus(await readText(join(procRoot, pid, "status")));
    if (status.name === "kthreadd") return { rss: 0, counted: 0, host: true };
    if (status.rssBytes == null) continue;
    rss += status.rssBytes;
    counted += 1;
  }
  return { rss, counted, host: false };
}

async function detectProc(options: Resolved): Promise<Strategy | null> {
  const scan = await listPids(options.procRoot);
  if (!scan.pids || scan.hostVisible) return null;
  const first = await sumProcMemory(options.procRoot, scan.pids);
  if (first.host || first.counted === 0) return null;

  return {
    source: "proc",
    sampleKey: `proc:${options.procRoot}`,
    async memory() {
      // A soma da detecção é desta mesma leitura: não varre /proc duas vezes.
      return { used: first.rss, limit: null };
    },
    async cpuUsageUsec() {
      const { pids, hostVisible } = await listPids(options.procRoot);
      if (!pids || hostVisible) return null;
      let ticks = 0;
      let counted = 0;
      for (const pid of pids) {
        const value = parseProcStatTicks(await readText(join(options.procRoot, pid, "stat")));
        if (value == null) continue;
        ticks += value;
        counted += 1;
      }
      // Processo que sai no meio da janela leva os ticks dele: a soma cai e a
      // janela é refeita curta (ver readCpu), nunca um percentual negativo.
      return counted ? (ticks / PROC_TICKS_PER_SECOND) * 1_000_000 : null;
    },
    async cpuQuotaCores() {
      return null;
    },
  };
}

// ── leitura ────────────────────────────────────────────────────────────────

async function readCpu(
  strategy: Strategy,
  options: Resolved,
): Promise<{ reading: ContainerCpuReading | null; coresFrom: CoresOrigin }> {
  const quota = await strategy.cpuQuotaCores();
  const envCores = parsePositiveEnv(options.env[CPU_CORES_ENV]);
  // Sem cota, o teto é o que o deploy declara ou, na falta, as CPUs que o processo enxerga.
  const coresFrom: CoresOrigin = quota != null ? "cgroup" : envCores != null ? "env" : "cpus";
  const limitCores = quota ?? envCores ?? Math.max(1, options.cpuCount());

  const first = await strategy.cpuUsageUsec();
  if (first == null) return { reading: null, coresFrom };
  const nowMs = options.nowMs();

  let start: CpuSample | undefined = lastCpuSample.get(strategy.sampleKey);
  let end: CpuSample = { usageUsec: first, atMs: nowMs };
  const age = start ? nowMs - start.atMs : -1;
  if (!start || age < CPU_WINDOW_MIN_MS || age > CPU_WINDOW_MAX_MS || first < start.usageUsec) {
    // Sem amostra anterior aproveitável: mede uma janela curta agora.
    start = end;
    await options.sleep(CGROUP_CPU_SHORT_WINDOW_MS);
    const second = await strategy.cpuUsageUsec();
    if (second == null) return { reading: null, coresFrom };
    end = { usageUsec: second, atMs: options.nowMs() };
  }
  lastCpuSample.set(strategy.sampleKey, end);

  const windowMs = end.atMs - start.atMs;
  if (windowMs <= 0) return { reading: { percent: null, limit_cores: limitCores, window_ms: 0 }, coresFrom };
  const usedCores = Math.max(0, end.usageUsec - start.usageUsec) / 1000 / windowMs;
  return {
    reading: {
      percent: roundPercent((usedCores / limitCores) * 100),
      limit_cores: Math.round(limitCores * 100) / 100,
      window_ms: Math.round(windowMs),
    },
    coresFrom,
  };
}

async function readMemory(
  strategy: Strategy,
  options: Resolved,
  memTotal: number | null,
): Promise<{ reading: ContainerMemoryReading | null; limitFrom: LimitOrigin }> {
  const raw = await strategy.memory();
  const envLimit = parsePositiveEnv(options.env[MEMORY_LIMIT_ENV]);
  const plausibleMemTotal =
    strategy.source === "proc" && memTotal != null && memTotal <= PLAUSIBLE_CONTAINER_MEMORY_BYTES ? memTotal : null;
  const limitFrom: LimitOrigin =
    raw?.limit != null ? "cgroup" : envLimit != null ? "env" : plausibleMemTotal != null ? "meminfo" : "none";
  if (!raw) return { reading: null, limitFrom };
  const limit = raw.limit ?? envLimit ?? plausibleMemTotal;
  return {
    reading: {
      used_bytes: Math.round(raw.used),
      limit_bytes: limit,
      percent: limit ? roundPercent((raw.used / limit) * 100) : null,
    },
    limitFrom,
  };
}

const PROBE_PATHS_V2 = ["memory.current", "memory.max", "cpu.stat", "cpu.max"];
const PROBE_PATHS_V1 = ["memory", "cpu,cpuacct", "cpuacct", "cpu"];
const PROBE_CGROUP_LINES = 12;
const PROBE_CGROUP_LINE_CHARS = 120;

async function probe(
  options: Resolved,
  cgroupText: string | null,
  memTotal: number | null,
  chosen: { source: CapacitySource; limitFrom: LimitOrigin; coresFrom: CoresOrigin | null; available: boolean },
) {
  const paths: Record<string, boolean> = {};
  for (const name of PROBE_PATHS_V2) paths[join(options.root, name)] = await exists(join(options.root, name));
  for (const name of PROBE_PATHS_V1) paths[`${join(options.root, name)}/`] = await exists(join(options.root, name));
  const scan = await listPids(options.procRoot);
  const line = {
    event: "capacity.probe",
    pid: options.pid,
    source: chosen.source,
    available: chosen.available,
    memory_limit_from: chosen.limitFrom,
    cpu_cores_from: chosen.coresFrom,
    paths,
    proc_self_cgroup: cgroupText
      ? cgroupText
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean)
          .slice(0, PROBE_CGROUP_LINES)
          .map((l) => l.slice(0, PROBE_CGROUP_LINE_CHARS))
      : null,
    meminfo_total_bytes: memTotal,
    visible_pids: scan.pids?.length ?? null,
    host_pids_visible: scan.hostVisible,
    cpus: options.cpuCount(),
  };
  options.log(JSON.stringify(line));
}

export async function readContainerCapacity(options: ReadContainerCapacityOptions = {}): Promise<ContainerCapacityReading> {
  const resolved: Resolved = {
    root: options.root ?? DEFAULT_CGROUP_ROOT,
    procRoot: options.procRoot ?? DEFAULT_PROC_ROOT,
    env: options.env ?? process.env,
    nowMs: options.nowMs ?? Date.now,
    sleep: options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms))),
    cpuCount: options.cpuCount ?? availableParallelism,
    log: options.log ?? ((line) => console.log(line)),
    pid: options.pid ?? process.pid,
  };

  const cgroupText = await readText(join(resolved.procRoot, "self", "cgroup"));
  const lines = parseProcSelfCgroup(cgroupText);
  const strategy =
    (await detectCgroupV2(resolved, lines)) ?? (await detectCgroupV1(resolved, lines)) ?? (await detectProc(resolved));
  // MemTotal serve de limite só no `proc`; na primeira leitura vai também para a sondagem.
  const needsMemTotal = strategy?.source === "proc" || !probeLogged;
  const memTotal = needsMemTotal ? parseMemInfoTotal(await readText(join(resolved.procRoot, "meminfo"))) : null;

  let memory: ContainerMemoryReading | null = null;
  let cpu: ContainerCpuReading | null = null;
  let limitFrom: LimitOrigin = "none";
  let coresFrom: CoresOrigin | null = null;
  if (strategy) {
    ({ reading: memory, limitFrom } = await readMemory(strategy, resolved, memTotal));
    ({ reading: cpu, coresFrom } = await readCpu(strategy, resolved));
  }

  const available = memory?.percent != null || cpu?.percent != null;
  const source: CapacitySource = strategy?.source ?? "none";
  if (!probeLogged) {
    probeLogged = true;
    try {
      await probe(resolved, cgroupText, memTotal, { source, limitFrom, coresFrom, available });
    } catch {
      // A sondagem é diagnóstico: falhar nela não pode derrubar a leitura.
    }
  }

  return {
    available,
    source,
    memory,
    cpu,
    measured_at: new Date(resolved.nowMs()).toISOString(),
  };
}

/** O maior percentual lido (memória ou CPU) — a régua dos limites do Admin. */
export function capacityPeak(reading: Pick<ContainerCapacityReading, "memory" | "cpu">): number | null {
  const values = [reading.memory?.percent, reading.cpu?.percent].filter((v): v is number => typeof v === "number");
  return values.length ? Math.max(...values) : null;
}
