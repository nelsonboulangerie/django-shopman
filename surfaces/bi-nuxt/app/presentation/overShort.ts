// "Sobrou ou faltou?" — a presentation pura da leitura do dia (V4-BI, prévia
// `bi-sobra4.html`). A projeção (`bi_over_short`) manda os fatos crus: quantidades
// string, horas "HH:MM", vereditos em inglês. Aqui eles viram as frases da prévia:
// a resposta, "faltou 3 de 4", "típico vende ~50; fez 44", "~14 perdidas".
import type {
  BIOverShortAnswerGroup,
  BIOverShortReport,
  BIOverShortRow,
  BIOverShortUnavailable,
} from "~/types/bi";
import type {
  ReadingChartPoint,
  ReadingChartSeries,
} from "../../../operator-kit/app/presentation/readingChart";
import { csvMoney, formatInt, formatQty, shortDate } from "./bi";

/** Custo da sobra em reais inteiros ("R$ 158"), como na prévia: centavo não decide produção. */
export function formatCostWhole(cents: number): string {
  return `R$ ${formatInt(Math.round(cents / 100))}`;
}

export type Verdict = "short" | "over" | "right";
export type VerdictTone = "destructive" | "warning" | "success";

export const VERDICTS: readonly Verdict[] = ["short", "over", "right"];

const VERDICT_META: Record<Verdict, { label: string; lower: string; tone: VerdictTone }> = {
  short: { label: "Faltou", lower: "faltou", tone: "destructive" },
  over: { label: "Sobrou", lower: "sobrou", tone: "warning" },
  right: { label: "Na medida", lower: "na medida", tone: "success" },
};

export function verdictMeta(verdict: string) {
  return VERDICT_META[(verdict as Verdict) in VERDICT_META ? (verdict as Verdict) : "right"];
}

const num = (value: string) => Number(value || 0);

// ── O dia e a comparação ─────────────────────────────────────────────────────


/** "2026-10-03" → dia da semana 0 = segunda (a convenção da projeção). */
function weekdayIndex(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  const js = new Date(Date.UTC(y!, (m ?? 1) - 1, d ?? 1)).getUTCDay();
  return (js + 6) % 7;
}

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y!, (m ?? 1) - 1, (d ?? 1) + days));
  return date.toISOString().slice(0, 10);
}

/** "Ontem", "Hoje" ou o dia da semana com maiúscula ("Quinta"). */
export function dayName(day: string, today: string): string {
  if (day === today) return "Hoje";
  if (day === addDays(today, -1)) return "Ontem";
  const label = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"][weekdayIndex(day)]!;
  return label;
}

/** O título da tela: a pergunta, com o dia ("Sobrou ou faltou ontem?"). */
export function overShortTitle(day: string, today: string): string {
  const name = dayName(day, today);
  if (name === "Ontem" || name === "Hoje") return `Sobrou ou faltou ${name.toLowerCase()}?`;
  return `Sobrou ou faltou ${name === "Sábado" || name === "Domingo" ? "no" : "na"} ${name.toLowerCase()} ${shortDate(day)}?`;
}

const WEEKDAY_TYPICAL = [
  { one: "segunda típica", many: "segundas" },
  { one: "terça típica", many: "terças" },
  { one: "quarta típica", many: "quartas" },
  { one: "quinta típica", many: "quintas" },
  { one: "sexta típica", many: "sextas" },
  { one: "sábado típico", many: "sábados" },
  { one: "domingo típico", many: "domingos" },
] as const;

/** "sábado típico" para o dia lido. */
export function typicalName(day: string): string {
  return WEEKDAY_TYPICAL[weekdayIndex(day)]!.one;
}

/** "num sábado típico", "numa segunda típica" (o artigo concorda com o dia). */
export function inTypical(day: string, compare = "typical"): string {
  const name = compareName(day, compare);
  const feminine = name.endsWith("típica") || name.endsWith("anterior") && weekdayIndex(day) < 5;
  return `${feminine ? "numa" : "num"} ${name}`;
}

/** As bases do "Comparar com" (a chave vai na URL, `?compare=`). */
export const COMPARE_KEYS = ["typical", "last", "typical8"] as const;
export type CompareKey = (typeof COMPARE_KEYS)[number];

const WEEKDAY_LAST = [
  "segunda anterior",
  "terça anterior",
  "quarta anterior",
  "quinta anterior",
  "sexta anterior",
  "sábado anterior",
  "domingo anterior",
] as const;

/** O nome da base: "sábado típico" ou "sábado anterior". */
export function compareName(day: string, compare = "typical"): string {
  return compare === "last" ? WEEKDAY_LAST[weekdayIndex(day)]! : typicalName(day);
}

/** As opções do controle, com o alcance de cada uma ("4 sábados", "8 sábados", "um só"). */
export function compareOptions(day: string): { key: CompareKey; label: string; reach: string }[] {
  const many = WEEKDAY_TYPICAL[weekdayIndex(day)]!.many;
  return [
    { key: "typical", label: typicalName(day), reach: `4 ${many}` },
    { key: "last", label: WEEKDAY_LAST[weekdayIndex(day)]!, reach: "um só" },
    { key: "typical8", label: typicalName(day), reach: `8 ${many}` },
  ];
}

/** "4 sábados: 05/09 a 26/09" (os dias de comparação, do mais antigo ao mais recente). */
export function compareCaption(day: string, compareDays: readonly string[]): string {
  if (!compareDays.length) return "sem dias de comparação ainda";
  const many = WEEKDAY_TYPICAL[weekdayIndex(day)]!.many;
  const oldest = compareDays[compareDays.length - 1]!;
  const newest = compareDays[0]!;
  const count = compareDays.length;
  if (count === 1) return `1 ${many.replace(/s$/, "")}: ${shortDate(newest)}`;
  return `${count} ${many}: ${shortDate(oldest)} a ${shortDate(newest)}`;
}

/** "Nos 4 sábados" (cabeça da coluna do histórico). */
export function historyHeading(day: string, compareDays: readonly string[]): string {
  const many = WEEKDAY_TYPICAL[weekdayIndex(day)]!.many;
  return compareDays.length ? `Nos ${compareDays.length} ${many}` : `Nos ${many} anteriores`;
}

// ── A resposta ───────────────────────────────────────────────────────────────

function nameList(rows: readonly BIOverShortRow[]): string {
  const [first, ...rest] = rows;
  if (!first) return "";
  return rest.length ? `${first.name} e mais ${rest.length}` : first.name;
}

const SHIFT_TEXT: Record<string, string> = {
  morning: "de manhã",
  afternoon: "à tarde",
  evening: "à noite",
};

/** "nos folhados", "nas bebidas quentes", "na mercearia": o artigo pela primeira palavra. */
function inCollection(label: string): string {
  const lower = label.toLocaleLowerCase("pt-BR");
  const first = lower.split(/\s+/)[0] ?? lower;
  if (first.endsWith("as")) return `nas ${lower}`;
  if (first.endsWith("os") || first.endsWith("es") || first.endsWith("s")) return `nos ${lower}`;
  if (first.endsWith("a")) return `na ${lower}`;
  return `no ${lower}`;
}

function groupText(group: BIOverShortAnswerGroup): string {
  const where = group.kind === "collection" ? inCollection(group.label) : group.label;
  const shift = SHIFT_TEXT[group.shift] ?? "";
  return shift ? `${where} ${shift}` : where;
}

function groupsText(groups: readonly BIOverShortAnswerGroup[]): string {
  const shown = groups.slice(0, 2).map(groupText);
  const rest = groups.length - shown.length;
  if (rest > 0) shown.push(`mais ${rest}`);
  if (shown.length <= 1) return shown[0] ?? "";
  return `${shown.slice(0, -1).join(", ")} e ${shown[shown.length - 1]}`;
}

/**
 * A resposta em uma frase (pino 5): "Faltou nos folhados de manhã; sobrou baguete à
 * tarde." Os grupos vêm da projeção (coleção quando 2 ou mais produtos dela tiveram o
 * mesmo veredito, senão o produto), com o turno em que acabou ou em que a venda parou.
 */
export function overShortAnswer(
  report: Pick<BIOverShortReport, "rows"> & Partial<Pick<BIOverShortReport, "answer_short" | "answer_over">>,
): string {
  if (!report.rows.length) return "Nenhum lote fechado neste dia: não há o que comparar.";
  if (report.answer_short?.length || report.answer_over?.length) {
    const parts: string[] = [];
    if (report.answer_short?.length) parts.push(`faltou ${groupsText(report.answer_short)}`);
    if (report.answer_over?.length) parts.push(`sobrou ${groupsText(report.answer_over)}`);
    if (!parts.length) return "Tudo na medida: nada acabou cedo e nada sobrou além de 2 unidades.";
    const sentence = parts.join("; ");
    return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`;
  }
  return productAnswer(report);
}

/**
 * A resposta produto a produto (quando a projeção não agrupa): onde faltou e quando acabou, onde sobrou e quanto.
 * Os produtos já vêm na ordem da leitura (faltou primeiro, o que acabou mais cedo antes;
 * sobrou pela maior sobra).
 */
function productAnswer(report: Pick<BIOverShortReport, "rows">): string {
  const short = report.rows.filter((row) => row.verdict === "short");
  const over = report.rows.filter((row) => row.verdict === "over");
  const parts: string[] = [];
  if (short.length) {
    const first = short[0]!;
    parts.push(`faltou ${nameList(short)}${first.soldout_at ? ` (acabou às ${first.soldout_at})` : ""}`);
  }
  if (over.length) {
    const first = over[0]!;
    parts.push(`sobrou ${nameList(over)} (${formatQty(first.leftover)} un.)`);
  }
  if (!parts.length) return "Tudo na medida: nada acabou cedo e nada sobrou além de 2 unidades.";
  const sentence = parts.join("; ");
  return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`;
}

// ── Os três números ──────────────────────────────────────────────────────────

const plural = (count: number, one: string, many: string) => (count === 1 ? one : many);

export function shortUnit(report: BIOverShortReport): string {
  const count = report.summary.short;
  const lost = num(report.summary.lost_estimate);
  const base = plural(count, "produto", "produtos");
  return lost > 0 ? `${base} · ~${formatQty(report.summary.lost_estimate)} vendas perdidas (est.)` : base;
}

export function overUnit(report: BIOverShortReport): string {
  const count = report.summary.over;
  const parts = [plural(count, "produto", "produtos")];
  const units = num(report.summary.leftover_units);
  if (units > 0) parts.push(`${formatQty(report.summary.leftover_units)} un.`);
  if (report.summary.leftover_cost_q > 0) {
    parts.push(`${formatCostWhole(report.summary.leftover_cost_q)} de custo${report.summary.cost_complete ? "" : " (parcial)"}`);
  } else if (units > 0 && !report.summary.cost_complete) {
    parts.push("sem custo cadastrado");
  }
  return parts.join(" · ");
}

/** A comparação embaixo de cada número ("sábado típico: 2 produtos"). */
export function typicalLine(report: BIOverShortReport, verdict: Verdict): string {
  const typical = report.typical;
  const name = compareName(report.day, report.compare);
  if (!typical.days) return `${name}: sem dias de comparação ainda`;
  if (verdict === "short") return `${name}: ${formatQty(typical.short)} ${plural(num(typical.short), "produto", "produtos")}`;
  if (verdict === "over") {
    const cost = typical.leftover_cost_q > 0 ? ` · ${formatCostWhole(typical.leftover_cost_q)}` : "";
    return `${name}: ${formatQty(typical.leftover_units)} un.${cost}`;
  }
  const late = report.closes_at ? `acabou depois das ${lastHour(report.closes_at)}` : "acabou na última hora";
  return `${late} ou sobrou até 2`;
}

/** "18:00" → "17h" (a última hora do expediente). */
function lastHour(closesAt: string): string {
  const [h, m] = closesAt.split(":").map(Number);
  const minutes = (h ?? 0) * 60 + (m ?? 0) - 60;
  const hour = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hour}h${String(rest).padStart(2, "0")}` : `${hour}h`;
}

// ── Cada produto ─────────────────────────────────────────────────────────────

/** "fez 44 · vendeu 44 · ~14 perdidas" (o desfecho da barra). */
export function outcomeText(row: BIOverShortRow): string {
  if (row.verdict === "short") {
    return num(row.lost_estimate) > 0 ? `~${formatQty(row.lost_estimate)} perdidas` : "acabou";
  }
  const left = num(row.leftover);
  return left > 0 ? `sobrou ${formatQty(row.leftover)}` : "zerou";
}

/** "10:40", "não acabou". */
export function soldoutText(row: BIOverShortRow): string {
  return row.soldout_at || "não acabou";
}

/** "faltou 3 de 4" (quantas vezes o veredito de hoje se repetiu nos dias de comparação). */
export function historyText(row: BIOverShortRow): string {
  if (!row.history.length) return "sem histórico";
  const same = row.history.filter((verdict) => verdict === row.verdict).length;
  return `${verdictMeta(row.verdict).lower} ${same} de ${row.history.length}`;
}

/** "típico vende ~50; fez 44", "típico ~50; R$ 61 de custo", "acabou perto de fechar". */
export function versusTypicalText(row: BIOverShortRow): string {
  const typical = row.typical_sold ? `~${formatQty(row.typical_sold)}` : "";
  if (row.verdict === "short") {
    return typical ? `típico vende ${typical}; fez ${formatQty(row.made)}` : `fez ${formatQty(row.made)}; sem típico ainda`;
  }
  if (row.verdict === "over") {
    const cost = row.leftover_cost_q ? `${formatCostWhole(row.leftover_cost_q)} de custo` : "";
    return [typical ? `típico ${typical}` : "sem típico ainda", cost].filter(Boolean).join("; ");
  }
  if (row.soldout_at) return "acabou perto de fechar";
  return typical ? `típico ${typical}` : "sem típico ainda";
}

// ── O gráfico "Fez × vendeu" (OperatorReadingChart do kit, deitado e empilhado) ──

/**
 * Os segmentos de cada barra: o que vendeu (cheio) e o que sobrou (o mesmo latão,
 * claro) somam o que a casa fez; as vendas perdidas depois que acabou (tijolo,
 * listrado: é estimativa) estendem a barra além do feito. Sobra e falta não aparecem
 * juntas no mesmo produto.
 */
export const MADE_SOLD_SERIES: ReadingChartSeries[] = [
  { key: "sold", label: "Vendeu", tone: "primary" },
  { key: "leftover", label: "Sobrou", tone: "primary", fill: "tint" },
  { key: "lost", label: "Vendas perdidas (estimativa)", tone: "error", fill: "hatch" },
];

/** Um ponto por produto, na ordem da leitura (faltou primeiro, depois a maior sobra). */
export function madeSoldPoints(rows: readonly BIOverShortRow[]): ReadingChartPoint[] {
  return rows.map((row) => ({
    label: row.name,
    values: { sold: num(row.sold), leftover: num(row.leftover), lost: num(row.lost_estimate) },
  }));
}

/** "+4 produtos: Focaccia do dia (sobrou 6) · Madeleine e Kuro Pan (na medida)". */
export function hiddenRowsSummary(rows: readonly BIOverShortRow[]): string {
  if (!rows.length) return "";
  const groups = VERDICTS.map((verdict) => ({
    verdict,
    rows: rows.filter((row) => row.verdict === verdict),
  })).filter((group) => group.rows.length);
  const text = groups
    .map((group) => {
      if (group.verdict === "over") {
        return group.rows.map((row) => `${row.name} (sobrou ${formatQty(row.leftover)})`).join(" · ");
      }
      const names = group.rows.map((row) => row.name);
      const joined = names.length > 1 ? `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}` : names[0];
      return `${joined} (${verdictMeta(group.verdict).lower})`;
    })
    .join(" · ");
  return `+${rows.length} ${plural(rows.length, "produto", "produtos")}: ${text}`;
}

/** Filtro da lista: veredito, coleção e busca por nome ou SKU (sem acento, sem caixa). */
export function filterRows(
  rows: readonly BIOverShortRow[],
  filters: { verdict: string; collection: string; query: string },
): BIOverShortRow[] {
  const fold = (value: string) => value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const query = fold(filters.query.trim());
  return rows.filter(
    (row) =>
      (!filters.verdict || row.verdict === filters.verdict) &&
      (!filters.collection || row.collection_ref === filters.collection) &&
      (!query || fold(row.name).includes(query) || fold(row.sku).includes(query)),
  );
}

/** As coleções presentes no dia, para o recorte "Coleção". */
export function collectionsOf(rows: readonly BIOverShortRow[]): { ref: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const row of rows) if (row.collection_ref && !seen.has(row.collection_ref)) seen.set(row.collection_ref, row.collection);
  return [...seen].map(([ref, name]) => ({ ref, name })).sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
}

// ── O que aconteceu depois e os caminhos ─────────────────────────────────────

function joinNames(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

/** "iFood, Meta e Google indisponíveis às 10:40" (o "(automático)" fica com a tela). */
export function unavailableText(item: BIOverShortUnavailable): string {
  const verb = item.channels.length === 1 ? "indisponível" : "indisponíveis";
  return `${joinNames(item.channels)} ${verb} às ${item.at}`;
}

/** "5 clientes" (o "Me avise" do site, por produto e dia). */
export function clientCount(count: number): string {
  return `${formatInt(count)} ${plural(count, "cliente", "clientes")}`;
}

/** "Abrir os 44 pedidos" / "Abrir o pedido". */
export function ordersLinkLabel(count: number): string {
  return count === 1 ? "Abrir o pedido" : `Abrir os ${formatInt(count)} pedidos`;
}

/** "Os 4 sábados" (os dias da comparação em que o produto foi feito). */
export function historyDaysLabel(day: string, count: number): string {
  const many = WEEKDAY_TYPICAL[weekdayIndex(day)]!.many;
  const one = many.replace(/s$/, "");
  return count === 1 ? `O ${one}` : `Os ${count} ${many}`;
}

const ORDINAL = (n: number) => `${n}º`;

/**
 * A linha sob os lotes: "Sem 3º lote: o plano dizia 44." quando o plano tinha mais
 * lotes do que os que fecharam; senão "2 lotes · 44 un. feitas".
 */
export function lotsLine(row: BIOverShortRow): string {
  const done = row.lots.length;
  const made = row.lots.reduce((sum, lot) => sum + num(lot.qty), 0);
  if (row.planned_lots > done) {
    return `Sem ${ORDINAL(done + 1)} lote: o plano dizia ${formatQty(row.planned)}.`;
  }
  return `${done === 1 ? "1 lote" : `${done} lotes`} · ${formatQty(String(made))} un. feitas`;
}

/** O gesto do cabeçalho: "Levar ao plano do próximo sábado" / "da próxima segunda". */
export function carryLabel(planDay: string): string {
  if (!planDay) return "";
  const index = weekdayIndex(planDay);
  const name = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][index]!;
  return index >= 5 ? `Levar ao plano do próximo ${name}` : `Levar ao plano da próxima ${name}`;
}

/** O botão do plano: "Abrir o plano de sábado 10/10". */
export function planLabel(planDay: string): string {
  if (!planDay) return "";
  const name = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][weekdayIndex(planDay)]!;
  return `Abrir o plano de ${name} ${shortDate(planDay)}`;
}

// ── A tabela produto a produto (NuxtTable) ──────────────────────────────────

/** A cor do selo do veredito (o tom carrega o sentido; o rótulo também). */
export const VERDICT_COLOR = { short: "error", over: "warning", right: "success" } as const satisfies Record<
  Verdict,
  "error" | "warning" | "success"
>;

export function verdictColor(verdict: string): "error" | "warning" | "success" {
  return VERDICT_COLOR[(verdict as Verdict) in VERDICT_COLOR ? (verdict as Verdict) : "right"];
}

/** O botão que abre o resto da tabela: "Ver os outros 3 produtos". */
export function showHiddenLabel(count: number): string {
  return count === 1 ? "Ver o outro produto" : `Ver os outros ${count} produtos`;
}

/**
 * O CSV do quadro "Produto a produto": as colunas da tabela com número cru (quem abre
 * o arquivo faz conta com ele).
 */
export function overShortCsv(rows: readonly BIOverShortRow[]): { header: string[]; rows: (string | number)[][] } {
  return {
    header: [
      "Produto",
      "SKU",
      "Veredito",
      "Fez",
      "Vendeu",
      "Vendas perdidas (estimativa)",
      "Sobrou",
      "Acabou às",
      "Típico vendido",
      "Custo da sobra (R$)",
    ],
    rows: rows.map((row) => [
      row.name,
      row.sku,
      verdictMeta(row.verdict).label,
      num(row.made),
      num(row.sold),
      num(row.lost_estimate),
      num(row.leftover),
      row.soldout_at || "",
      row.typical_sold ? num(row.typical_sold) : "",
      row.leftover_cost_q ? csvMoney(row.leftover_cost_q) : "",
    ]),
  };
}
