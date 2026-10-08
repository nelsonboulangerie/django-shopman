// O chrome da suíte (V6-KIT), a parte PURA: onde mora a navegação, que tecla leva a
// cada seção, o que vai para a barra do polegar e o que vai para o "Mais", e quanto
// soma o selo de Avisos. Sem Vue, com teste (`tests/suiteChrome.test.ts`).
//
// Régua: as prévias v4 (`fontes/v4/*.html`, `_rail3bottom.html`) e, onde a v4 não
// redesenhou, a navegação v3 (`depois-navegacao.jpg`): rail compacto no tablet deitado
// e no desktop, barra de seções embaixo no tablet em pé e no celular (até 4 + Mais),
// Alt 1…9 em todo app, impresso no desktop.
import type { OperatorSection } from "./appBar";

/**
 * Onde o rail existe: tablet DEITADO (a partir de 768px) e qualquer tela de 1024px para
 * cima. Abaixo disso, ou em pé num tablet de 820, a navegação é a barra de baixo. A
 * mesma régua mora no CSS como a variante `rail:` (`operator-suite.css`); as duas
 * precisam dizer a mesma coisa, e o teste confere.
 */
export const SUITE_RAIL_MEDIA = "(min-width: 768px) and (orientation: landscape), (min-width: 1024px)";

/** Quantas seções cabem na barra do polegar antes do "Mais" (navegação v3, nível 1). */
export const PHONE_BAR_SECTIONS = 4;

/**
 * Os três estados do rail da suíte no desktop (`OperatorSuiteShell`, dono 08/10/2026,
 * PR #1539): aberto (ícone e nome), compacto (só ícone) e oculto (o sidebar não é
 * montado). Um botão só na barra e a tecla C percorrem nesta ordem, em anel.
 */
export type SuiteRailState = "open" | "compact" | "hidden";

export const SUITE_RAIL_CYCLE: readonly SuiteRailState[] = ["open", "compact", "hidden"];

export function nextSuiteRailState(state: SuiteRailState): SuiteRailState {
  return SUITE_RAIL_CYCLE[(SUITE_RAIL_CYCLE.indexOf(state) + 1) % SUITE_RAIL_CYCLE.length]!;
}

/**
 * O botão da barra diz o PRÓXIMO estado: o ícone e o nome são do gesto, não do agora.
 * Na tela a peça se chama "barra lateral" (dono, 08/10/2026, PR #1544); `rail` é só o
 * nome no código.
 */
export const SUITE_RAIL_NEXT: Readonly<Record<SuiteRailState, { label: string; icon: string }>> = {
  open: { label: "Compactar a barra lateral", icon: "i-lucide-panel-left-dashed" },
  compact: { label: "Ocultar a barra lateral", icon: "i-lucide-panel-left-close" },
  hidden: { label: "Mostrar a barra lateral", icon: "i-lucide-panel-left-open" },
};

export type RailSignalColor = "success" | "warning" | "error";

/** O sinal de um item do rail: um ponto de estado ou um número. */
export interface RailSignal {
  color: RailSignalColor;
  /** Contagem (chip numérico). Ausente = ponto de estado. */
  count?: number;
  /** O estado por extenso, para tooltip e leitor de tela ("1 desligado"). */
  state?: string;
}

/**
 * O sinal da seção: com `badge` numérico e maior que zero, o número; senão, com
 * `attention`, o ponto. Zero não é sinal. A cor é `tone` (padrão `warning`).
 */
export function sectionRailSignal(section: OperatorSection): RailSignal | undefined {
  const color = section.tone ?? "warning";
  const count = Number.parseInt(section.badge ?? "", 10);
  if (Number.isFinite(count) && count > 0) return { color, count, state: section.attention || undefined };
  if (section.attention) return { color, state: section.attention };
  return undefined;
}

/**
 * As props do Chip: o ponto no tamanho padrão do NavigationMenu; o número no `4xl` do
 * kit (o `3xl` não lê dois dígitos), `inset: false` (centrado no canto, sem cobrir o
 * ícone) e "99+" acima de 99.
 */
export function railSignalChip(signal: RailSignal): { color: RailSignalColor; text?: string; size?: "4xl"; inset?: boolean } {
  if (signal.count === undefined) return { color: signal.color };
  return { color: signal.color, text: signal.count > 99 ? "99+" : String(signal.count), size: "4xl", inset: false };
}

/**
 * Tooltip e nome acessível do item: "Canais · 1 desligado" ou "Pedidos · 3 pendências"
 * ("1 pendência"). Contagem tem UMA palavra na suíte: o item diz o que é, o número diz
 * quanto. Quem monta o item usa `sectionDescription`, a fonte única.
 */
export function railSignalLabel(label: string, signal?: RailSignal): string {
  if (!signal) return label;
  const parts = [label];
  if (signal.count !== undefined) parts.push(`${signal.count} ${signal.count === 1 ? "pendência" : "pendências"}`);
  if (signal.state) parts.push(signal.state);
  return parts.join(" · ");
}

/**
 * A descrição de uma seção, a MESMA na barra lateral, na gaveta e na barra inferior
 * (dono, 08/10/2026, PR #1544): "Seção · N pendências" ("1 pendência") ou
 * "Seção · estado". É o tooltip e o nome acessível do item. Antes cada app contava
 * com um substantivo próprio, e o mesmo número era lido de dois jeitos na mesma tela
 * ("Saída, 2 pedidos na Saída" embaixo, "Saída · 2 pendências" ao lado).
 */
export function sectionDescription(section: OperatorSection): string {
  return railSignalLabel(section.label, sectionRailSignal(section));
}

/** Teclas de seção: Alt 1…9, pela ordem do rail. A décima seção em diante não tem tecla. */
export function sectionShortcut(index: number): string {
  return index >= 0 && index < 9 ? `Alt+${index + 1}` : "";
}

/**
 * As seções de cima do rail com a tecla de cada uma. Quem já declarou a sua (o PDV,
 * "F2" nas Comandas) fica com ela impressa; o Alt+N vale do mesmo jeito.
 */
export function withSectionShortcuts(sections: readonly OperatorSection[]): OperatorSection[] {
  return sections.map((section, index) => ({
    ...section,
    shortcut: section.shortcut || sectionShortcut(index),
  }));
}

interface KeyLike {
  key: string;
  code?: string;
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey?: boolean;
}

/**
 * Alt+N pede a seção N (base 0)? Lê o `code` ("Digit3"), porque no macOS Alt+3 escreve
 * "£" no `key`. Ctrl e Meta ficam de fora: são do navegador.
 */
export function sectionIndexFromKey(event: KeyLike): number | null {
  if (!event.altKey || event.ctrlKey || event.metaKey) return null;
  const match = /^Digit([1-9])$/.exec(event.code || "") || /^([1-9])$/.exec(event.key);
  return match ? Number(match[1]) - 1 : null;
}

/** "?" abre a ajuda de atalhos (com ou sem Shift, que é como o "?" sai no teclado). */
export function isShortcutsHelpKey(event: KeyLike): boolean {
  return event.key === "?" && !event.altKey && !event.ctrlKey && !event.metaKey;
}

export interface PhoneBarLayout {
  /** As seções que aparecem na barra, na ordem do rail. */
  visible: OperatorSection[];
  /** As que não couberam: moram no "Mais", acima do menu do operador. */
  overflow: OperatorSection[];
}

/**
 * Até 4 seções na barra e o resto no "Mais" (`cozinha-celular4.html`: Saída · Preparo ·
 * Estações · Mais). O "Mais" existe sempre que há operador: é ele que guarda Bloquear,
 * trocar de operador e o tema no celular.
 */
export function phoneBarLayout(sections: readonly OperatorSection[], max = PHONE_BAR_SECTIONS): PhoneBarLayout {
  if (sections.length <= max) return { visible: [...sections], overflow: [] };
  return { visible: sections.slice(0, max), overflow: sections.slice(max) };
}

/**
 * A barra inferior do celular no shell da suíte (dono, 08/10/2026, PR #1544). Uma
 * regra só para todo app:
 *
 * - a gaveta (☰, a barra lateral) é o menu COMPLETO; a barra inferior é o menu
 *   RÁPIDO, de 3 a 5 vagas;
 * - o app declara o que vai para a barra (`quick: true` na seção, na ordem da lista);
 *   o kit corta em 5;
 * - com menos de 5 declaradas e alguma seção de fora, uma vaga vira "Mais", que abre a
 *   gaveta; com 5, não há "Mais" (o ☰ já leva ao completo); sem seção de fora, também
 *   não;
 * - app que não declara: as primeiras seções, até 4, e "Mais" quando sobra;
 * - menos de 3 vagas é erro de configuração (`quickBarProblems`), salvo o app que tem
 *   menos de 3 seções ao todo, ou a exceção declarada com motivo.
 */
export const QUICK_BAR_MIN = 3;
export const QUICK_BAR_MAX = 5;
export const QUICK_BAR_DEFAULT = 4;

export interface QuickBarLayout {
  /** As seções da barra, na ordem da lista. */
  items: OperatorSection[];
  /** Uma vaga para "Mais" (abre a gaveta). */
  more: boolean;
  /** As seções que ficaram só na gaveta. */
  overflow: OperatorSection[];
}

export function quickBarLayout(sections: readonly OperatorSection[]): QuickBarLayout {
  const declared = sections.filter((section) => section.quick);
  const items = (declared.length ? declared : sections.slice(0, QUICK_BAR_DEFAULT)).slice(0, QUICK_BAR_MAX);
  const overflow = sections.filter((section) => !items.includes(section));
  return { items, more: items.length < QUICK_BAR_MAX && overflow.length > 0, overflow };
}

/**
 * O que está fora da regra, por extenso (vazio = dentro). O teste das seções de cada
 * app a chama. `exception` é o motivo de uma exceção declarada pelo app: ela dispensa o
 * mínimo, nunca o máximo.
 */
export function quickBarProblems(sections: readonly OperatorSection[], exception = ""): string[] {
  const problems: string[] = [];
  const declared = sections.filter((section) => section.quick).length;
  if (declared > QUICK_BAR_MAX) {
    problems.push(`${declared} seções declaradas para a barra inferior; o máximo é ${QUICK_BAR_MAX}`);
  }
  const layout = quickBarLayout(sections);
  const slots = layout.items.length + (layout.more ? 1 : 0);
  const min = Math.min(QUICK_BAR_MIN, sections.length);
  if (slots < min && !exception.trim()) {
    problems.push(`${slots} vagas na barra inferior; o mínimo é ${min}`);
  }
  return problems;
}

/** O selo do item: acima de 9 vira "9+" (o número exato não muda decisão). */
export function inboxBadge(total: number): string {
  if (total <= 0) return "";
  return total > 9 ? "9+" : String(total);
}

export interface InboxCounts {
  /** Alertas da operação ativos (OperatorAlert, decisões do Marketing). */
  alerts: number;
  /** Avisos pessoais não lidos. */
  unread: number;
  /** A capacidade do serviço passou do limite crítico. */
  capacityCritical: boolean;
}

/** Um selo só para a caixa inteira: alertas + não lidos + a capacidade crítica. */
export function inboxTotal(counts: InboxCounts): number {
  return Math.max(0, counts.alerts) + Math.max(0, counts.unread) + (counts.capacityCritical ? 1 : 0);
}

/** "Avisos (3)", "Avisos" — o nome acessível diz o número que o selo mostra. */
export function inboxAriaLabel(total: number): string {
  return total > 0 ? `Avisos (${total} ${total === 1 ? "pede" : "pedem"} sua atenção)` : "Avisos";
}

export interface ShortcutItem {
  keys: string[];
  label: string;
}

export interface ShortcutGroup {
  title: string;
  items: ShortcutItem[];
}

/**
 * O grupo que todo app tem: as seções (Alt 1…9), a busca e a própria ajuda. O app
 * acrescenta os grupos da tela dele depois deste.
 */
export function suiteShortcutGroup(sections: readonly OperatorSection[], options: { appLabel?: string; search?: boolean; rail?: boolean } = {}): ShortcutGroup {
  const items: ShortcutItem[] = [];
  sections.forEach((section, index) => {
    const alt = sectionShortcut(index);
    if (!alt) return;
    const keys = section.shortcut && section.shortcut !== alt ? [alt, section.shortcut] : [alt];
    items.push({ keys, label: section.label });
  });
  if (options.search) items.push({ keys: ["/"], label: "Buscar nesta tela" });
  if (options.rail) items.push({ keys: ["C"], label: "Barra lateral: aberta, compacta ou oculta" });
  items.push({ keys: ["?"], label: "Abrir esta ajuda" });
  return { title: options.appLabel ? `Em todo o ${options.appLabel}` : "Em todo o app", items };
}

/**
 * Junta o grupo da suíte com os grupos do app, sem repetir a mesma tecla com o mesmo
 * rótulo (o PDV já listava "?" na ajuda dele).
 */
export function mergeShortcutGroups(base: ShortcutGroup, extra: readonly ShortcutGroup[]): ShortcutGroup[] {
  const seen = new Set(base.items.map((item) => `${item.keys.join("+")}|${item.label}`));
  const baseKeys = new Set(base.items.flatMap((item) => item.keys));
  const groups = extra.map((group) => ({
    title: group.title,
    items: group.items.filter((item) => {
      const id = `${item.keys.join("+")}|${item.label}`;
      if (seen.has(id)) return false;
      // A tecla que o grupo da suíte já explica (Alt+1, "?") não se repete com outro texto.
      if (item.keys.length === 1 && baseKeys.has(item.keys[0]!) && /^(Alt\+[1-9]|\?)$/.test(item.keys[0]!)) return false;
      seen.add(id);
      return true;
    }),
  }));
  return [base, ...groups.filter((group) => group.items.length)];
}

/** O `OperatorAlert` do backstage como os apps o leem (Gestor, Produção). */
export interface OperatorAlertLike {
  pk: number;
  type_label: string;
  severity: string;
  severity_label: string;
  message: string;
  order_ref?: string | null;
  created_at_display: string;
  /** Prazo em que a causa decide sozinha (ISO); vazio sem prazo. */
  respond_by_iso?: string;
  /** `external` (o mundo lá fora decide no fim) ou `house` (régua da casa). */
  deadline_kind?: string;
  /** De onde vem e do que se trata, para ler num relance. */
  origin_label?: string;
  origin_icon?: string;
  subject?: string;
  actions?: ReadonlyArray<{ kind: string; enabled: boolean; label: string; href?: string | null }>;
}

export interface InboxAlertView {
  key: number;
  tone: "critical" | "warning" | "info";
  eyebrow: string;
  message: string;
  meta: string;
  seen: boolean;
  canAck: boolean;
  href?: string;
  hrefLabel?: string;
  respondByIso?: string;
  deadlineKind?: "external" | "house";
  origin?: string;
  originIcon?: string;
  subject?: string;
}

/**
 * Um alerta da operação escrito para a caixa de Avisos: a gravidade como tom (crítico e
 * erro são o vermelho de "bloqueado com motivo"; aviso, o âmbar), o lugar exato quando o
 * servidor o oferece, e "Visto" só quando o servidor oferece o gesto.
 */
export function operatorAlertToInbox(alert: OperatorAlertLike): InboxAlertView {
  const actions = alert.actions ?? [];
  const context = actions.find((action) => action.kind === "open_alert_context" && action.enabled && action.href);
  const canAck = actions.some((action) => action.kind === "acknowledge_alert" && action.enabled);
  return {
    key: alert.pk,
    tone: alert.severity === "critical" || alert.severity === "error" ? "critical" : "warning",
    eyebrow: `${alert.severity_label} · ${alert.type_label}`,
    message: alert.message,
    meta: alert.order_ref ? `${alert.created_at_display} · pedido ${alert.order_ref}` : alert.created_at_display,
    seen: !canAck,
    canAck,
    ...(context ? { href: context.href ?? undefined, hrefLabel: context.label } : {}),
    ...(alert.respond_by_iso ? { respondByIso: alert.respond_by_iso } : {}),
    ...(alert.deadline_kind === "external" || alert.deadline_kind === "house"
      ? { deadlineKind: alert.deadline_kind }
      : {}),
    ...(alert.origin_label ? { origin: alert.origin_label } : {}),
    ...(alert.origin_icon ? { originIcon: alert.origin_icon } : {}),
    ...(alert.subject ? { subject: alert.subject } : {}),
  };
}

/**
 * Depois do Visto, o aviso volta num ritmo proporcional ao que falta (dono, 08/10/2026):
 * mais ou menos a cada quarto do tempo restante, nunca menos de 1 min nem mais de 1 dia.
 * Perto do prazo aperta sozinho. Vencido pela régua da casa, a causa continua: lembra a
 * cada 5 min até alguém resolver.
 */
export const REMINDER_MIN_MS = 60_000;
export const REMINDER_MAX_MS = 24 * 60 * 60_000;
export const OVERDUE_REMINDER_MS = 5 * 60_000;
export function reminderIntervalMs(leftMs: number): number {
  if (leftMs <= 0) return OVERDUE_REMINDER_MS;
  return Math.min(REMINDER_MAX_MS, Math.max(REMINDER_MIN_MS, Math.floor(leftMs / 4)));
}

export interface UrgentAlertsView<T> {
  /** O aviso que interrompe a tela agora: com prazo correndo e ainda sem Visto. */
  blocking: T | null;
  /** Os já vistos cujo prazo ainda corre: lembram até a causa acabar. */
  reminders: T[];
}

type Urgent = { respondByIso?: string; seen?: boolean; deadlineKind?: string };

/**
 * Quais avisos interrompem a tela: os que têm prazo. Vencido o prazo do mundo lá fora
 * (`external`, ex.: o iFood), a decisão já saiu e o aviso sai da tela; vencida a régua
 * da casa (`house`), a causa continua e o aviso fica, atrasado. Entre os não vistos,
 * o de prazo mais curto primeiro.
 */
export function urgentAlerts<T extends Urgent>(items: readonly T[], nowMs: number): UrgentAlertsView<T> {
  const running = items
    .map((item) => ({ item, deadline: Date.parse(item.respondByIso ?? "") }))
    .filter(
      ({ item, deadline }) =>
        Number.isFinite(deadline) && (deadline > nowMs || item.deadlineKind === "house"),
    )
    .sort((a, b) => a.deadline - b.deadline);
  return {
    blocking: running.find(({ item }) => !item.seen)?.item ?? null,
    reminders: running.filter(({ item }) => item.seen).map(({ item }) => item),
  };
}

/** "6 min" · "menos de 1 min" · "2 h" · "3 dias": quanto, num relance. */
export function spanLabel(ms: number): string {
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "menos de 1 min";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 dia" : `${days} dias`;
}

/** Título do prazo: "Responda em 6 min" · "Responda em 2 h" · "Passou do prazo há 3 min". */
export function respondInLabel(respondByIso: string, nowMs: number): string {
  const left = Date.parse(respondByIso) - nowMs;
  if (!Number.isFinite(left)) return "";
  return left > 0 ? `Responda em ${spanLabel(left)}` : `Passou do prazo há ${spanLabel(-left)}`;
}

/** "faltam 6 min" · "falta 1 min" · "menos de 1 min" */
export function deadlineLeftLabel(respondByIso: string, nowMs: number): string {
  const left = Date.parse(respondByIso) - nowMs;
  if (!Number.isFinite(left) || left <= 0) return "prazo vencido";
  const minutes = Math.floor(left / 60_000);
  if (minutes < 1) return "menos de 1 min";
  return minutes === 1 ? "falta 1 min" : `faltam ${minutes} min`;
}
