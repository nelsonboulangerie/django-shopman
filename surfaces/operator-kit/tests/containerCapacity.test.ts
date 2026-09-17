// Leitura de capacidade com árvores falsas de /sys/fs/cgroup e /proc: cgroup v2,
// cgroup v1 (caminho relativo e raiz, sem limite), soma de processos, a ordem de
// escolha, a sondagem única por processo — e a ausência de tudo (dev local), que
// precisa dizer "sem leitura", nunca 0%.
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
  parseCgroupV1CpuCores,
  parseCgroupV1MemoryLimit,
  parseMemInfoTotal,
  parsePositiveEnv,
  parseProcSelfCgroup,
  parseProcStatTicks,
  parseProcStatus,
  readContainerCapacity,
  resetContainerCapacityState,
  type ReadContainerCapacityOptions,
} from "../server/utils/containerCapacity";

const MiB = 1024 * 1024;
const GiB = 1024 * MiB;
const V1_UNLIMITED = "9223372036854771712\n";
let root: string;
let proc: string;
let log: ReturnType<typeof vi.fn>;

function tree(base: string, files: Record<string, string>) {
  for (const [name, content] of Object.entries(files)) {
    const path = join(base, name);
    mkdirSync(join(path, ".."), { recursive: true });
    writeFileSync(path, content);
  }
}

function cgroup(files: Record<string, string>) {
  mkdirSync(root, { recursive: true });
  tree(root, files);
}

function procStat(pid: number, name: string, ticks: number): string {
  // Campos 14 (utime) e 15 (stime); o nome entre parênteses pode ter espaço.
  return `${pid} (${name}) S 0 1 1 0 -1 4194560 100 0 0 0 ${ticks} 0 0 0 20 0 11 0 12345\n`;
}

/** Um processo visível em /proc: RSS em MiB (null = thread de kernel) e ticks de CPU. */
function visibleProcess(pid: number, name: string, rssMiB: number | null, ticks: number) {
  const rss = rssMiB == null ? "" : `VmRSS:\t${rssMiB * 1024} kB\n`;
  tree(proc, {
    [`${pid}/status`]: `Name:\t${name}\nState:\tS (sleeping)\n${rss}`,
    [`${pid}/stat`]: procStat(pid, name, ticks),
  });
}

/** Relógio controlado com um gancho no `sleep` (troca os contadores no meio da janela). */
function clockWith(startMs: number, onSleep: () => void = () => {}) {
  let nowMs = startMs;
  const sleep = vi.fn(async (ms: number) => {
    nowMs += ms;
    onSleep();
  });
  return { nowMs: () => nowMs, sleep };
}

function read(
  time: { nowMs: () => number; sleep: (ms: number) => Promise<void> },
  extra: ReadContainerCapacityOptions = {},
) {
  return readContainerCapacity({
    root,
    procRoot: proc,
    env: {},
    log,
    pid: 4242,
    nowMs: time.nowMs,
    sleep: time.sleep,
    cpuCount: () => 1,
    ...extra,
  });
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
  const base = mkdtempSync(join(tmpdir(), "capacity-"));
  root = join(base, "cgroup");
  proc = join(base, "proc");
  log = vi.fn();
  resetContainerCapacityState();
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

    const reading = await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 8 });

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

    const reading = await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 2 });

    expect(reading.memory).toEqual({ used_bytes: 100 * MiB, limit_bytes: null, percent: null });
    // Sem cota, o teto é o número de CPUs que o contêiner enxerga.
    expect(reading.cpu?.limit_cores).toBe(2);
    expect(reading.cpu?.percent).toBe(0);
    expect(reading.available).toBe(true);
  });

  it("cota fracionária: 0,5 núcleo inteiro ocupado é 100%, nunca mais", async () => {
    cgroup({ "cpu.stat": "usage_usec 0\n", "cpu.max": "50000 100000\n" });
    const time = clock(0, 400_000); // 400 ms de CPU em 250 ms: ruído de janela

    const reading = await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 4 });

    expect(reading.cpu?.limit_cores).toBe(0.5);
    expect(reading.cpu?.percent).toBe(100);
    expect(reading.memory).toBeNull();
    expect(reading.available).toBe(true);
  });

  it("reaproveita a amostra anterior como janela, sem dormir de novo", async () => {
    cgroup({ "cpu.stat": "usage_usec 0\n", "cpu.max": "100000 100000\n" });
    const time = clock(0, 0);
    await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });
    expect(time.sleep).toHaveBeenCalledTimes(1);

    // 30 s depois, 6 s de CPU consumidos: 20% de um núcleo na janela inteira.
    time.advance(30_000);
    writeFileSync(join(root, "cpu.stat"), "usage_usec 6000000\n");
    const reading = await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });

    expect(time.sleep).toHaveBeenCalledTimes(1);
    expect(reading.cpu).toEqual({ percent: 20, limit_cores: 1, window_ms: 30_000 });
  });

  it("amostra anterior velha demais não vale como janela", async () => {
    cgroup({ "cpu.stat": "usage_usec 0\n", "cpu.max": "100000 100000\n" });
    const time = clock(0, 0);
    await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });
    time.advance(10 * 60_000);

    const reading = await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });

    expect(time.sleep).toHaveBeenCalledTimes(2);
    expect(reading.cpu?.window_ms).toBe(CGROUP_CPU_SHORT_WINDOW_MS);
  });

  it("sem cgroup (dev local, macOS): available false e nenhum número", async () => {
    const time = clock(5_000);

    const reading = await readContainerCapacity({
      root: join(root, "nao-existe"),
      procRoot: join(proc, "nao-existe"),
      env: {},
      log,
      nowMs: time.nowMs,
      sleep: time.sleep,
      cpuCount: () => 8,
    });

    expect(reading).toEqual({
      available: false,
      source: "none",
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

    const reading = await readContainerCapacity({ root, procRoot: proc, env: {}, log, nowMs: time.nowMs, sleep: time.sleep, cpuCount: () => 1 });

    expect(reading.available).toBe(false);
    expect(reading.memory?.used_bytes).toBe(10 * MiB);
  });
});

describe("parsers do cgroup v1 e do /proc", () => {
  it("memory.limit_in_bytes absurdo é sem limite", () => {
    expect(parseCgroupV1MemoryLimit(V1_UNLIMITED)).toBeNull();
    expect(parseCgroupV1MemoryLimit("1073741824\n")).toBe(GiB);
    expect(parseCgroupV1MemoryLimit(null)).toBeNull();
  });

  it("cfs_quota_us -1 é sem cota; cota/período vira núcleos", () => {
    expect(parseCgroupV1CpuCores("-1\n", "100000\n")).toBeNull();
    expect(parseCgroupV1CpuCores("50000", "100000")).toBe(0.5);
    expect(parseCgroupV1CpuCores(null, "100000")).toBeNull();
  });

  it("/proc/self/cgroup em v1 e v2", () => {
    expect(parseProcSelfCgroup("12:memory:/docker/abc\n4:cpu,cpuacct:/docker/abc\n1:name=systemd:/x\n")).toEqual([
      { controllers: ["memory"], path: "/docker/abc" },
      { controllers: ["cpu", "cpuacct"], path: "/docker/abc" },
      { controllers: ["name=systemd"], path: "/x" },
    ]);
    expect(parseProcSelfCgroup("0::/\n")).toEqual([{ controllers: [], path: "/" }]);
    expect(parseProcSelfCgroup(null)).toEqual([]);
  });

  it("status, stat e meminfo", () => {
    expect(parseProcStatus("Name:\tnode\nVmRSS:\t   2048 kB\n")).toEqual({ name: "node", rssBytes: 2048 * 1024 });
    expect(parseProcStatus("Name:\tkthreadd\n")).toEqual({ name: "kthreadd", rssBytes: null });
    expect(parseProcStatTicks("7 (node (worker) x) S 1 7 7 0 -1 0 0 0 0 0 30 12 0 0 20 0 1 0 9\n")).toBe(42);
    expect(parseProcStatTicks("lixo")).toBeNull();
    expect(parseMemInfoTotal("MemTotal:        1048576 kB\nMemFree: 1 kB\n")).toBe(GiB);
    expect(parseMemInfoTotal(null)).toBeNull();
  });

  it("env numérica positiva ou nada", () => {
    expect(parsePositiveEnv("1073741824")).toBe(GiB);
    expect(parsePositiveEnv("0.5")).toBe(0.5);
    expect(parsePositiveEnv("")).toBeNull();
    expect(parsePositiveEnv("0")).toBeNull();
    expect(parsePositiveEnv("1GB")).toBeNull();
    expect(parsePositiveEnv(undefined)).toBeNull();
  });
});

describe("cgroup v2 com o caminho de /proc/self/cgroup", () => {
  it("lê o grupo relativo antes da raiz", async () => {
    tree(proc, { "self/cgroup": "0::/app.slice/web\n" });
    cgroup({
      "memory.current": String(900 * MiB),
      "memory.max": String(GiB),
      "app.slice/web/memory.current": String(256 * MiB),
      "app.slice/web/memory.max": String(512 * MiB),
      "app.slice/web/cpu.stat": "usage_usec 0\n",
    });

    const reading = await read(clockWith(0));

    expect(reading.source).toBe("cgroup-v2");
    expect(reading.memory).toEqual({ used_bytes: 256 * MiB, limit_bytes: 512 * MiB, percent: 50 });
  });

  it("memory.max 'max' com a env do deploy: o percentual sai do limite declarado", async () => {
    cgroup({ "memory.current": String(256 * MiB), "memory.max": "max\n", "cpu.stat": "usage_usec 0\n" });

    const reading = await read(clockWith(0), { env: { SHOPMAN_CONTAINER_MEMORY_LIMIT_BYTES: String(GiB) } });

    expect(reading.memory).toEqual({ used_bytes: 256 * MiB, limit_bytes: GiB, percent: 25 });
  });
});

describe("cgroup v1", () => {
  const SELF = "12:memory:/docker/abc\n4:cpu,cpuacct:/docker/abc\n0::/\n";

  it("acha o grupo pelo caminho relativo de /proc/self/cgroup, antes da raiz", async () => {
    tree(proc, { "self/cgroup": SELF });
    cgroup({
      // Raiz da hierarquia com números de outro grupo: não pode ser a escolhida.
      "memory/memory.usage_in_bytes": String(8 * GiB),
      "memory/memory.limit_in_bytes": V1_UNLIMITED,
      "memory/docker/abc/memory.usage_in_bytes": String(700 * MiB),
      "memory/docker/abc/memory.stat": `cache ${200 * MiB}\ninactive_file ${50 * MiB}\ntotal_inactive_file ${100 * MiB}\n`,
      "memory/docker/abc/memory.limit_in_bytes": String(GiB),
      "cpu,cpuacct/docker/abc/cpuacct.usage": "1000000000\n",
      "cpu,cpuacct/docker/abc/cpu.cfs_quota_us": "100000\n",
      "cpu,cpuacct/docker/abc/cpu.cfs_period_us": "100000\n",
    });
    // 62,5 ms de CPU (em nanossegundos) na janela de 250 ms.
    const time = clockWith(0, () =>
      writeFileSync(join(root, "cpu,cpuacct/docker/abc/cpuacct.usage"), String(1_000_000_000 + 62_500_000)),
    );

    const reading = await read(time, { cpuCount: () => 8 });

    expect(reading.source).toBe("cgroup-v1");
    expect(reading.memory).toEqual({ used_bytes: 600 * MiB, limit_bytes: GiB, percent: 58.6 });
    expect(reading.cpu).toEqual({ percent: 25, limit_cores: 1, window_ms: CGROUP_CPU_SHORT_WINDOW_MS });
    expect(reading.available).toBe(true);
  });

  it("caminho relativo ausente (hierarquia do contêiner montada na raiz): lê a raiz", async () => {
    tree(proc, { "self/cgroup": SELF });
    cgroup({
      "memory/memory.usage_in_bytes": String(300 * MiB),
      "memory/memory.limit_in_bytes": String(600 * MiB),
      "cpuacct/cpuacct.usage": "0\n",
    });

    const reading = await read(clockWith(0));

    expect(reading.source).toBe("cgroup-v1");
    expect(reading.memory?.percent).toBe(50);
    expect(reading.cpu?.percent).toBe(0);
  });

  it("sem limite e sem cota: uso sem percentual de memória; CPU sobre as CPUs visíveis", async () => {
    cgroup({
      "memory/memory.usage_in_bytes": String(300 * MiB),
      "memory/memory.limit_in_bytes": V1_UNLIMITED,
      "cpu,cpuacct/cpuacct.usage": "0\n",
      "cpu,cpuacct/cpu.cfs_quota_us": "-1\n",
      "cpu,cpuacct/cpu.cfs_period_us": "100000\n",
    });
    const time = clockWith(0, () => writeFileSync(join(root, "cpu,cpuacct/cpuacct.usage"), "250000000"));

    const reading = await read(time, { cpuCount: () => 4 });

    expect(reading.memory).toEqual({ used_bytes: 300 * MiB, limit_bytes: null, percent: null });
    expect(reading.cpu).toEqual({ percent: 25, limit_cores: 4, window_ms: CGROUP_CPU_SHORT_WINDOW_MS });
    expect(reading.available).toBe(true);
  });
});

describe("proc — soma dos processos visíveis", () => {
  function threeProcesses() {
    visibleProcess(1, "node", 40, 300); // o roteador
    visibleProcess(17, "node", 180, 500); // PDV
    visibleProcess(23, "node", 80, 200); // Cozinha
    tree(proc, { "self/cgroup": "0::/\n" });
  }

  function burnTicks(ticks: Record<number, number>) {
    return () => {
      for (const [pid, value] of Object.entries(ticks)) {
        writeFileSync(join(proc, pid, "stat"), procStat(Number(pid), "node", value));
      }
    };
  }

  it("três processos: RSS somado sobre o MemTotal de tamanho de contêiner, CPU pelos ticks", async () => {
    threeProcesses();
    tree(proc, { meminfo: `MemTotal:        ${1024 * 1024} kB\n` });
    // +25 ticks = 250 ms de CPU numa janela de 250 ms: um núcleo cheio de dois.
    const time = clockWith(0, burnTicks({ 1: 305, 17: 515, 23: 205 }));

    const reading = await read(time, { cpuCount: () => 2 });

    expect(reading.source).toBe("proc");
    expect(reading.memory).toEqual({ used_bytes: 300 * MiB, limit_bytes: GiB, percent: 29.3 });
    expect(reading.cpu).toEqual({ percent: 50, limit_cores: 2, window_ms: CGROUP_CPU_SHORT_WINDOW_MS });
    expect(reading.available).toBe(true);
  });

  it("MemTotal de máquina e sem env: uso em bytes, sem percentual de memória", async () => {
    threeProcesses();
    tree(proc, { meminfo: `MemTotal:        ${64 * 1024 * 1024} kB\n` });

    const reading = await read(clockWith(0), { cpuCount: () => 2 });

    expect(reading.memory).toEqual({ used_bytes: 300 * MiB, limit_bytes: null, percent: null });
    expect(reading.cpu?.percent).toBe(0);
  });

  it("as envs do deploy dão o limite e os núcleos (e vencem o MemTotal)", async () => {
    threeProcesses();
    tree(proc, { meminfo: `MemTotal:        ${2 * 1024 * 1024} kB\n` });
    const time = clockWith(0, burnTicks({ 1: 300, 17: 525, 23: 200 }));

    const reading = await read(time, {
      cpuCount: () => 8,
      env: { SHOPMAN_CONTAINER_MEMORY_LIMIT_BYTES: "536870912", SHOPMAN_CONTAINER_CPU_CORES: "1" },
    });

    expect(reading.memory).toEqual({ used_bytes: 300 * MiB, limit_bytes: 512 * MiB, percent: 58.6 });
    expect(reading.cpu).toEqual({ percent: 100, limit_cores: 1, window_ms: CGROUP_CPU_SHORT_WINDOW_MS });
  });

  it("processo que sai no meio da janela não vira percentual negativo", async () => {
    threeProcesses();
    const time = clockWith(0, () => rmSync(join(proc, "23"), { recursive: true, force: true }));

    const reading = await read(time);

    expect(reading.cpu?.percent).toBe(0);
  });

  it("enxergando processo de host (kthreadd), a régua é recusada", async () => {
    threeProcesses();
    visibleProcess(2, "kthreadd", null, 0);
    const time = clockWith(0);

    const reading = await read(time);

    expect(reading).toMatchObject({ available: false, source: "none", memory: null, cpu: null });
    expect(time.sleep).not.toHaveBeenCalled();
  });

  it("PIDs demais para um contêiner: recusa", async () => {
    for (let pid = 2; pid <= 300; pid += 1) mkdirSync(join(proc, String(pid)), { recursive: true });
    visibleProcess(1, "node", 40, 0);

    const reading = await read(clockWith(0));

    expect(reading.source).toBe("none");
  });
});

describe("ordem de escolha", () => {
  it("v2 vence v1, que vence proc", async () => {
    cgroup({
      "memory.current": String(100 * MiB),
      "memory.max": String(400 * MiB),
      "memory/memory.usage_in_bytes": String(200 * MiB),
      "memory/memory.limit_in_bytes": String(400 * MiB),
    });
    visibleProcess(1, "node", 300, 0);
    const time = clockWith(0);

    expect((await read(time)).source).toBe("cgroup-v2");

    rmSync(join(root, "memory.current"));
    expect((await read(time)).source).toBe("cgroup-v1");

    rmSync(join(root, "memory"), { recursive: true });
    expect((await read(time)).source).toBe("proc");

    rmSync(proc, { recursive: true });
    expect((await read(time)).source).toBe("none");
  });
});

describe("sondagem capacity.probe", () => {
  it("uma linha JSON na primeira leitura do processo, e só nela — sem env", async () => {
    tree(proc, { "self/cgroup": "12:memory:/docker/abc\n0::/\n", meminfo: `MemTotal:        ${1024 * 1024} kB\n` });
    visibleProcess(1, "node", 40, 0);
    visibleProcess(9, "node", 60, 0);
    const time = clockWith(0);
    const env = { SHOPMAN_CONTAINER_CPU_CORES: "1", NUXT_DJANGO_PROXY_SECRET: "segredo-que-nao-sai" };

    await read(time, { env, cpuCount: () => 4 });
    await read(time, { env, cpuCount: () => 4 });

    expect(log).toHaveBeenCalledOnce();
    const line = String(log.mock.calls[0]![0]);
    expect(line).not.toContain("segredo-que-nao-sai");
    const probe = JSON.parse(line);
    expect(probe).toMatchObject({
      event: "capacity.probe",
      pid: 4242,
      source: "proc",
      available: true,
      memory_limit_from: "meminfo",
      cpu_cores_from: "env",
      proc_self_cgroup: ["12:memory:/docker/abc", "0::/"],
      meminfo_total_bytes: GiB,
      visible_pids: 2,
      host_pids_visible: false,
      cpus: 4,
    });
    expect(probe.paths).toEqual({
      [join(root, "memory.current")]: false,
      [join(root, "memory.max")]: false,
      [join(root, "cpu.stat")]: false,
      [join(root, "cpu.max")]: false,
      [`${join(root, "memory")}/`]: false,
      [`${join(root, "cpu,cpuacct")}/`]: false,
      [`${join(root, "cpuacct")}/`]: false,
      [`${join(root, "cpu")}/`]: false,
    });
  });

  it("com cgroup v2, os caminhos que existem aparecem como tais", async () => {
    cgroup({ "memory.current": String(MiB), "memory.max": String(GiB), "cpu.stat": "usage_usec 0\n" });

    await read(clockWith(0));

    const probe = JSON.parse(String(log.mock.calls[0]![0]));
    expect(probe.source).toBe("cgroup-v2");
    expect(probe.memory_limit_from).toBe("cgroup");
    expect(probe.paths[join(root, "memory.current")]).toBe(true);
    expect(probe.paths[join(root, "cpu.max")]).toBe(false);
  });

  it("sem régua nenhuma, a sondagem diz isso também", async () => {
    await read(clockWith(0));

    const probe = JSON.parse(String(log.mock.calls[0]![0]));
    expect(probe).toMatchObject({ source: "none", available: false, visible_pids: null, proc_self_cgroup: null });
  });
});
