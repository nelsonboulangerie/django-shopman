import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type { OperatorSection } from "../app/presentation/appBar";
import {
  SUITE_RAIL_CYCLE,
  SUITE_RAIL_MEDIA,
  SUITE_RAIL_NEXT,
  nextSuiteRailState,
  railSignalChip,
  railSignalLabel,
  sectionRailSignal,
  inboxAriaLabel,
  inboxBadge,
  inboxTotal,
  isShortcutsHelpKey,
  mergeShortcutGroups,
  operatorAlertToInbox,
  urgentAlerts,
  deadlineLeftLabel,
  respondInLabel,
  reminderIntervalMs,
  phoneBarLayout,
  QUICK_BAR_MAX,
  quickBarLayout,
  quickBarProblems,
  sectionDescription,
  sectionIndexFromKey,
  sectionShortcut,
  suiteShortcutGroup,
  withSectionShortcuts,
} from "../app/presentation/suiteChrome";

// O chrome da suíte (V6-KIT), a parte pura: onde mora a navegação, as teclas de seção,
// a barra do polegar com o "Mais", e o selo único de Avisos.
const here = dirname(fileURLToPath(import.meta.url));
const SECTIONS: OperatorSection[] = ["a", "b", "c", "d", "e", "f"].map((key) => ({ key, label: key.toUpperCase(), icon: "lucide:circle" }));

describe("onde mora a navegação", () => {
  it("a régua do JS é a mesma da variante rail: do CSS", () => {
    const css = readFileSync(resolve(here, "../app/assets/css/operator-suite.css"), "utf8");
    expect(css).toContain(`@media ${SUITE_RAIL_MEDIA}`);
  });

  it("o tablet em pé (820) não tem rail; o deitado (1180) e o desktop têm", () => {
    expect(SUITE_RAIL_MEDIA).toContain("orientation: landscape");
    expect(SUITE_RAIL_MEDIA).toContain("min-width: 1024px");
  });
});

describe("Alt 1…9 em todo app", () => {
  it("as nove primeiras seções têm tecla; a décima não", () => {
    expect(sectionShortcut(0)).toBe("Alt+1");
    expect(sectionShortcut(8)).toBe("Alt+9");
    expect(sectionShortcut(9)).toBe("");
  });

  it("quem declarou a própria tecla fica com ela (F2 nas Comandas do PDV)", () => {
    const sections = withSectionShortcuts([{ key: "tabs", label: "Comandas", icon: "x", shortcut: "F2" }, { key: "pre", label: "Encomendas", icon: "x" }]);
    expect(sections.map((s) => s.shortcut)).toEqual(["F2", "Alt+2"]);
  });

  it("lê o código da tecla (Alt+3 no macOS escreve £)", () => {
    expect(sectionIndexFromKey({ key: "£", code: "Digit3", altKey: true, ctrlKey: false, metaKey: false })).toBe(2);
    expect(sectionIndexFromKey({ key: "3", code: "Digit3", altKey: false, ctrlKey: false, metaKey: false })).toBeNull();
    expect(sectionIndexFromKey({ key: "3", code: "Digit3", altKey: true, ctrlKey: true, metaKey: false })).toBeNull();
  });

  it("'?' abre a ajuda", () => {
    expect(isShortcutsHelpKey({ key: "?", altKey: false, ctrlKey: false, metaKey: false, shiftKey: true })).toBe(true);
    expect(isShortcutsHelpKey({ key: "/", altKey: false, ctrlKey: false, metaKey: false })).toBe(false);
  });
});

describe("a ajuda de atalhos", () => {
  it("o grupo comum sai das seções e não repete o que o app já disse", () => {
    const base = suiteShortcutGroup(SECTIONS.slice(0, 2), { appLabel: "Gestor" });
    expect(base.title).toBe("Em todo o Gestor");
    expect(base.items.map((i) => i.keys.join(" "))).toEqual(["Alt+1", "Alt+2", "?"]);
    const merged = mergeShortcutGroups(base, [{ title: "Na venda", items: [{ keys: ["?"], label: "Esta ajuda" }, { keys: ["F9"], label: "Enviar à cozinha" }] }]);
    expect(merged[1]!.items.map((i) => i.keys[0])).toEqual(["F9"]);
  });
});

describe("a barra do polegar: até 4 + Mais", () => {
  it("cabe tudo com 4 ou menos", () => {
    expect(phoneBarLayout(SECTIONS.slice(0, 4)).overflow).toEqual([]);
  });

  it("acima de 4, o resto vai para o Mais", () => {
    const layout = phoneBarLayout(SECTIONS);
    expect(layout.visible.map((s) => s.key)).toEqual(["a", "b", "c", "d"]);
    expect(layout.overflow.map((s) => s.key)).toEqual(["e", "f"]);
  });
});

describe("barra inferior do shell: regra única de 3 a 5 vagas (dono, 08/10/2026)", () => {
  const quick = (keys: string[]) => SECTIONS.map((section) => ({ ...section, quick: keys.includes(section.key) }));
  const keys = (list: OperatorSection[]) => list.map((section) => section.key);

  it("sem declaração: as primeiras até 4, e 'Mais' quando sobra", () => {
    const layout = quickBarLayout(SECTIONS);
    expect(keys(layout.items)).toEqual(["a", "b", "c", "d"]);
    expect(layout.more).toBe(true);
    expect(keys(layout.overflow)).toEqual(["e", "f"]);
    const fits = quickBarLayout(SECTIONS.slice(0, 3));
    expect(keys(fits.items)).toEqual(["a", "b", "c"]);
    expect(fits.more).toBe(false);
  });

  it("o app declara o que vai para a barra, na ordem da lista", () => {
    const layout = quickBarLayout(quick(["b", "d", "f"]));
    expect(keys(layout.items)).toEqual(["b", "d", "f"]);
    expect(layout.more).toBe(true);
    expect(keys(layout.overflow)).toEqual(["a", "c", "e"]);
  });

  it("5 declaradas: sem 'Mais' (o ☰ já leva ao menu completo)", () => {
    const layout = quickBarLayout(quick(["a", "b", "c", "d", "e"]));
    expect(layout.items).toHaveLength(QUICK_BAR_MAX);
    expect(layout.more).toBe(false);
    expect(keys(layout.overflow)).toEqual(["f"]);
    expect(quickBarProblems(quick(["a", "b", "c", "d", "e"]))).toEqual([]);
  });

  it("'Mais' só quando sobra seção", () => {
    const all = SECTIONS.slice(0, 4).map((section) => ({ ...section, quick: true }));
    expect(quickBarLayout(all).more).toBe(false);
  });

  it("no máximo 5: o kit corta, e o teste acusa", () => {
    const six = quick(["a", "b", "c", "d", "e", "f"]);
    expect(quickBarLayout(six).items).toHaveLength(5);
    expect(quickBarProblems(six)).toEqual(["6 seções declaradas para a barra inferior; o máximo é 5"]);
  });

  it("menos de 3 vagas é erro de configuração, salvo exceção com motivo", () => {
    const one = quick(["a"]);
    // 1 seção + "Mais" = 2 vagas.
    expect(quickBarProblems(one)).toEqual(["2 vagas na barra inferior; o mínimo é 3"]);
    expect(quickBarProblems(one, "a tela é um quiosque de uma seção só")).toEqual([]);
    expect(quickBarProblems(quick(["a", "b"]))).toEqual([]);
  });

  it("app com menos de 3 seções mostra todas, sem erro", () => {
    expect(quickBarProblems(SECTIONS.slice(0, 2))).toEqual([]);
  });
});

describe("a descrição única da seção (barra lateral, gaveta e barra inferior)", () => {
  it("'Seção · N pendências', '1 pendência', 'Seção · estado'", () => {
    expect(sectionDescription({ key: "x", label: "Saída", icon: "i", badge: "2" })).toBe("Saída · 2 pendências");
    expect(sectionDescription({ key: "x", label: "Pedidos", icon: "i", badge: "1" })).toBe("Pedidos · 1 pendência");
    expect(sectionDescription({ key: "x", label: "Canais", icon: "i", attention: "1 desligado" })).toBe("Canais · 1 desligado");
    expect(sectionDescription({ key: "x", label: "Catálogo", icon: "i" })).toBe("Catálogo");
  });
});

describe("Avisos: um selo para a caixa inteira", () => {
  it("soma alertas, não lidos e a capacidade crítica", () => {
    expect(inboxTotal({ alerts: 2, unread: 1, capacityCritical: true })).toBe(4);
    expect(inboxTotal({ alerts: 0, unread: 0, capacityCritical: false })).toBe(0);
  });

  it("acima de 9 vira 9+; zero não é selo", () => {
    expect(inboxBadge(12)).toBe("9+");
    expect(inboxBadge(0)).toBe("");
  });

  it("o nome acessível diz o número", () => {
    expect(inboxAriaLabel(0)).toBe("Avisos");
    expect(inboxAriaLabel(1)).toBe("Avisos (1 pede sua atenção)");
  });

  it("um OperatorAlert vira linha da caixa, com o lugar exato e o Visto quando o servidor oferece", () => {
    const view = operatorAlertToInbox({
      pk: 3,
      type_label: "Pagamento",
      severity: "error",
      severity_label: "Erro",
      message: "Pix falhou",
      order_ref: "W07",
      created_at_display: "21:55",
      actions: [
        { kind: "open_alert_context", enabled: true, label: "Abrir o pedido", href: "/W07" },
        { kind: "acknowledge_alert", enabled: true, label: "Visto" },
      ],
    });
    expect(view).toMatchObject({ key: 3, tone: "critical", eyebrow: "Erro · Pagamento", meta: "21:55 · pedido W07", canAck: true, seen: false, href: "/W07" });
  });
});

describe("aviso com prazo: interrompe, depois lembra (dono, 07/10/2026)", () => {
  const NOW = Date.parse("2026-10-07T15:00:00Z");
  const at = (minutes: number) => new Date(NOW + minutes * 60_000).toISOString();

  it("o prazo do servidor chega ao item da caixa de Avisos", () => {
    const view = operatorAlertToInbox({
      pk: 7, type_label: "iFood: negociação esperando resposta", severity: "error",
      severity_label: "Erro", message: "O cliente pediu cancelamento.", order_ref: "IFOOD-9",
      created_at_display: "07/10 às 12:00", respond_by_iso: at(8), actions: [],
    });
    expect(view.respondByIso).toBe(at(8));
    const semPrazo = operatorAlertToInbox({
      pk: 8, type_label: "x", severity: "warning", severity_label: "Aviso", message: "m",
      created_at_display: "", respond_by_iso: "", actions: [],
    });
    expect(semPrazo).not.toHaveProperty("respondByIso");
  });

  it("bloqueia o não visto de prazo mais curto; os vistos só lembram", () => {
    const items = [
      { key: 1, respondByIso: at(9), seen: false },
      { key: 2, respondByIso: at(3), seen: false },
      { key: 3, respondByIso: at(5), seen: true },
      { key: 4, seen: false },
    ];
    const view = urgentAlerts(items, NOW);
    expect(view.blocking?.key).toBe(2);
    expect(view.reminders.map((item) => item.key)).toEqual([3]);
  });

  it("prazo do mundo lá fora vencido sai da tela: a decisão já saiu", () => {
    const view = urgentAlerts(
      [{ key: 1, respondByIso: at(-1), seen: false, deadlineKind: "external" }],
      NOW,
    );
    expect(view).toEqual({ blocking: null, reminders: [] });
  });

  it("régua da casa vencida fica: a causa continua (o cliente ainda espera)", () => {
    const view = urgentAlerts(
      [
        { key: 1, respondByIso: at(-3), seen: false, deadlineKind: "house" },
        { key: 2, respondByIso: at(-9), seen: true, deadlineKind: "house" },
      ],
      NOW,
    );
    expect(view.blocking?.key).toBe(1);
    expect(view.reminders.map((item) => item.key)).toEqual([2]);
  });

  it("o lembrete acompanha o prazo: um quarto do que falta, de 1 min a 1 dia", () => {
    const min = 60_000;
    expect(reminderIntervalMs(4 * min)).toBe(min);
    expect(reminderIntervalMs(6 * min)).toBe(1.5 * min);
    expect(reminderIntervalMs(2 * min)).toBe(min);
    expect(reminderIntervalMs(60 * min)).toBe(15 * min);
    expect(reminderIntervalMs(8 * 60 * min)).toBe(2 * 60 * min);
    expect(reminderIntervalMs(3 * 24 * 60 * min)).toBe(18 * 60 * min);
    expect(reminderIntervalMs(5 * 24 * 60 * min)).toBe(24 * 60 * min);
    expect(reminderIntervalMs(-1)).toBe(5 * min);
  });

  it("o tempo restante se diz em minutos", () => {
    expect(deadlineLeftLabel(at(6.5), NOW)).toBe("faltam 6 min");
    expect(deadlineLeftLabel(at(1.2), NOW)).toBe("falta 1 min");
    expect(deadlineLeftLabel(at(0.5), NOW)).toBe("menos de 1 min");
    expect(deadlineLeftLabel(at(-1), NOW)).toBe("prazo vencido");
  });

  it("o título do aviso é o prazo, num relance", () => {
    expect(respondInLabel(at(6.5), NOW)).toBe("Responda em 6 min");
    expect(respondInLabel(at(0.5), NOW)).toBe("Responda em menos de 1 min");
    expect(respondInLabel(at(150), NOW)).toBe("Responda em 2 h");
    expect(respondInLabel(at(3 * 24 * 60), NOW)).toBe("Responda em 3 dias");
    expect(respondInLabel(at(-3), NOW)).toBe("Passou do prazo há 3 min");
  });
});

describe("rail da suíte em três estados (PR-K4)", () => {
  it("o anel é aberto → compacto → oculto → aberto, e o botão diz o próximo", () => {
    expect(SUITE_RAIL_CYCLE).toEqual(["open", "compact", "hidden"]);
    expect(nextSuiteRailState("open")).toBe("compact");
    expect(nextSuiteRailState("compact")).toBe("hidden");
    expect(nextSuiteRailState("hidden")).toBe("open");
    expect(SUITE_RAIL_NEXT.open.label).toBe("Compactar a barra lateral");
    expect(SUITE_RAIL_NEXT.compact.label).toBe("Ocultar a barra lateral");
    expect(SUITE_RAIL_NEXT.hidden.label).toBe("Mostrar a barra lateral");
  });

  it("o sinal: número com badge maior que zero, ponto com atenção, nada sem os dois", () => {
    const base = { key: "a", label: "Pedidos", icon: "i-lucide-list" };
    expect(sectionRailSignal(base)).toBeUndefined();
    expect(sectionRailSignal({ ...base, badge: "0" })).toBeUndefined();
    expect(sectionRailSignal({ ...base, badge: "4" })).toEqual({ color: "warning", count: 4, state: undefined });
    expect(sectionRailSignal({ ...base, attention: "1 desligado", tone: "error" })).toEqual({ color: "error", state: "1 desligado" });
  });

  it("o chip: ponto no tamanho padrão; número 4xl, sem inset, e 99+ acima de 99", () => {
    expect(railSignalChip({ color: "success" })).toEqual({ color: "success" });
    expect(railSignalChip({ color: "error", count: 12 })).toEqual({ color: "error", text: "12", size: "4xl", inset: false });
    expect(railSignalChip({ color: "error", count: 99 }).text).toBe("99");
    expect(railSignalChip({ color: "error", count: 100 }).text).toBe("99+");
  });

  it("a descrição: 'App · estado' ou 'App · N pendências' (1 pendência)", () => {
    expect(railSignalLabel("Catálogo")).toBe("Catálogo");
    expect(railSignalLabel("PDV", { color: "error", state: "sem conexão" })).toBe("PDV · sem conexão");
    expect(railSignalLabel("Cozinha", { color: "error", count: 1 })).toBe("Cozinha · 1 pendência");
    expect(railSignalLabel("Gestor", { color: "error", count: 12 })).toBe("Gestor · 12 pendências");
  });

  it("a ajuda de atalhos ensina a tecla C só onde o rail tem três estados", () => {
    const sections = [{ key: "a", label: "Pedidos", icon: "i-lucide-list" }];
    expect(suiteShortcutGroup(sections).items.some((item) => item.keys[0] === "C")).toBe(false);
    expect(suiteShortcutGroup(sections, { rail: true }).items).toContainEqual({ keys: ["C"], label: "Barra lateral: aberta, compacta ou oculta" });
  });
});
