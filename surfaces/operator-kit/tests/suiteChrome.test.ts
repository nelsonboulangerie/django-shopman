import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import type { OperatorSection } from "../app/presentation/appBar";
import {
  SUITE_RAIL_MEDIA,
  inboxAriaLabel,
  inboxBadge,
  inboxTotal,
  isShortcutsHelpKey,
  mergeShortcutGroups,
  operatorAlertToInbox,
  urgentAlerts,
  deadlineLeftLabel,
  URGENT_REMINDER_MINUTES,
  phoneBarLayout,
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

  it("prazo vencido não interrompe nem lembra: a decisão já saiu", () => {
    const view = urgentAlerts([{ key: 1, respondByIso: at(-1), seen: false }], NOW);
    expect(view).toEqual({ blocking: null, reminders: [] });
  });

  it("o lembrete é de 5 minutos e o tempo restante se diz em minutos", () => {
    expect(URGENT_REMINDER_MINUTES).toBe(1);
    expect(deadlineLeftLabel(at(6.5), NOW)).toBe("faltam 6 min");
    expect(deadlineLeftLabel(at(1.2), NOW)).toBe("falta 1 min");
    expect(deadlineLeftLabel(at(0.5), NOW)).toBe("menos de 1 min");
    expect(deadlineLeftLabel(at(-1), NOW)).toBe("prazo vencido");
  });
});
