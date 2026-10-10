// Travas da conformidade V6 da Produção com a v4 (auditoria pdv-prod-compras, ids R*).
// Cada bloco segura uma classe de divergência que já voltou uma vez.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  commitmentChipLabel,
  dayContextLine,
  formatQty,
  formatQtyUnit,
  latestPlanTime,
  lotLabelPayload,
  matchLotCode,
  plannedAsSuggested,
} from "~/presentation/production";
import { suggestionHistory } from "~/presentation/planningReason";
import type {
  ProductionMatrixRowProjection,
  ProductionSuggestionProjection,
  WorkOrderCardProjection,
} from "~/types/production";

const APP = resolve(__dirname, "../../app");
const read = (path: string) => readFileSync(resolve(APP, path), "utf8");

function order(over: Partial<WorkOrderCardProjection> = {}): WorkOrderCardProjection {
  return {
    pk: 1,
    ref: "WO-2026-00020",
    rev: 1,
    recipe_pk: 1,
    recipe_ref: "R",
    recipe_name: "Croissant",
    base_usages: [],
    output_sku: "CRO",
    status: "planned",
    status_label: "",
    tone: "",
    planned_qty: "52",
    started_qty: "",
    finished_qty: "",
    yield_rate: "",
    loss: "",
    operator_ref: "",
    position_ref: "",
    target_date_display: "",
    started_at_display: "",
    created_at_display: "",
    progress_pct: 0,
    committed_qty: "6",
    order_commitments: [],
    can_void: true,
    position_name: "",
    created_at_time: "",
    ...over,
  };
}

function row(over: Partial<ProductionMatrixRowProjection> = {}): ProductionMatrixRowProjection {
  return {
    recipe_pk: 1,
    output_sku: "CRO",
    recipe_name: "Croissant",
    base_usages: [],
    suggestion: null,
    planned_orders: [],
    started_orders: [],
    finished_orders: [],
    planned_qty: "0",
    started_qty: "0",
    finished_qty: "0",
    loss_qty: "0",
    output_unit: "un",
    ...over,
  };
}

describe("R07: número da bancada em português, com unidade", () => {
  it("vírgula decimal, milhar com ponto, grama acima de um quilo vira quilo", () => {
    expect(formatQty("1230.77", "g")).toBe("1,23 kg");
    expect(formatQty("830.5", "g")).toBe("830,5 g");
    expect(formatQty("18720", "g")).toBe("18,72 kg");
    expect(formatQty("52", "un")).toBe("52");
    expect(formatQty("1500", "ml")).toBe("1,5 l");
    expect(formatQtyUnit("26", "un")).toBe("26 un.");
  });

  it("nenhum número cru com ponto decimal na linha dos planejados", () => {
    const grid = read("components/ProductionStageGrid.vue");
    expect(grid).not.toMatch(/<b class="tnum">\{\{ plannedQtyLabel\(row\) \}\}<\/b>/);
    expect(grid).toContain("formatQty(plannedQtyLabel(row), row.output_unit)");
  });

  it("o separador anda colado ao item e some no celular (nunca sobra um · sozinho)", () => {
    const grid = read("components/ProductionStageGrid.vue");
    const item = grid.indexOf("data-planned-item");
    expect(item).toBeGreaterThan(-1);
    expect(grid.indexOf("data-planned-separator")).toBeGreaterThan(item);
    expect(grid).toMatch(/class="pl-0\.5 text-muted-foreground max-sm:hidden"\s+aria-hidden="true"\s+data-planned-separator/);
  });
});

describe("R05: a hora do compromisso no chip", () => {
  it('"6 un. para 08:30" com a hora mais cedo; sem hora, só as unidades', () => {
    const withTime = row({
      planned_orders: [
        order({
          order_commitments: [
            { ref: "P1", status: "", status_label: "", qty_required: "4", due_time: "12:00" },
            { ref: "P2", status: "", status_label: "", qty_required: "2", due_time: "08:30" },
          ],
        }),
      ],
    });
    expect(commitmentChipLabel(withTime)).toBe("6 un. para 08:30");
    const noTime = row({
      planned_orders: [
        order({
          order_commitments: [{ ref: "P1", status: "", status_label: "", qty_required: "6", due_time: "" }],
        }),
      ],
    });
    expect(commitmentChipLabel(noTime)).toBe("6 un.");
  });
});

describe("R06: Planejado 15:12 · como sugerido", () => {
  it("a hora é a do plano mais recente", () => {
    const rows = [
      row({ planned_qty: "20", planned_orders: [order({ created_at_time: "09:10" })] }),
      row({ planned_qty: "10", planned_orders: [order({ created_at_time: "15:12" })] }),
    ];
    expect(latestPlanTime(rows)).toBe("15:12");
  });

  it("como sugerido só quando o planejado é o número da sugestão", () => {
    const suggestion = { quantity: "52" } as ProductionSuggestionProjection;
    expect(plannedAsSuggested(row({ suggestion, planned_qty: "52" }))).toBe(true);
    expect(plannedAsSuggested(row({ suggestion, planned_qty: "50" }))).toBe(false);
  });
});

describe("R04: ocasião e clima no cabeçalho do Planejamento", () => {
  it("previsão para o dia que vem, medição para o passado, nada sem dado", () => {
    expect(
      dayContextLine(
        { occasion: "Sábado comum, sem feriado", weather: "24 °C e sol", weather_kind: "forecast" },
        "como os sábados usados na conta",
      ),
    ).toBe("Sábado comum, sem feriado · previsão 24 °C e sol (como os sábados usados na conta)");
    expect(dayContextLine({ occasion: "", weather: "18 °C e chuva", weather_kind: "measured" })).toBe(
      "18 °C e chuva",
    );
    expect(dayContextLine(null)).toBe("");
  });
});

describe("R09: o desfecho de cada dia da amostra no Por quê", () => {
  it('"Acabou às 10:40 em 3 dos últimos 4 sábados", com a nota da projeção', () => {
    const suggestion = {
      soldout_days: 3,
      sample_size: 8,
      same_weekday: true,
      waste_percent: 0,
      waste_discounted: false,
      season_fallback: false,
      season_label: "",
      recent_days: [
        { date: "2026-09-05", date_display: "05/09", outcome: "soldout", soldout_at: "10:40" },
        { date: "2026-09-12", date_display: "12/09", outcome: "soldout", soldout_at: "10:20" },
        { date: "2026-09-19", date_display: "19/09", outcome: "ok", soldout_at: "" },
        { date: "2026-09-26", date_display: "26/09", outcome: "soldout", soldout_at: "11:05" },
      ],
    } as unknown as ProductionSuggestionProjection;
    const [line] = suggestionHistory(suggestion, "2026-10-03");
    expect(line!.text).toBe("Acabou às 10:40 em 3 dos últimos 4 sábados");
    expect(line!.note).toBe("a projeção já soma o que deixou de vender");
  });
});

describe("R19: a etiqueta do lote abre o lote", () => {
  const orders = [
    { ref: "WO-2026-00020", output_sku: "CRO" },
    { ref: "WO-2026-00021", output_sku: "KUP" },
  ];
  it("lê o QR da etiqueta de preparo, o código do lote e o SKU", () => {
    expect(matchLotCode(lotLabelPayload("KUP"), orders)?.ref).toBe("WO-2026-00021");
    expect(matchLotCode("wo-2026-00020", orders)?.output_sku).toBe("CRO");
    expect(matchLotCode("CRO", orders)?.ref).toBe("WO-2026-00020");
    expect(matchLotCode("nada", orders)).toBeNull();
  });
});

describe("R10/R11/R16: cabeçalho", () => {
  it("sem 'Voltar para hoje' solto ao lado do dia nas telas do dia", () => {
    for (const file of ["components/ProductionStageGrid.vue", "pages/close.vue"]) {
      expect(read(file)).toContain('class="[&_[data-period-today]]:hidden"');
    }
  });

  it("Qualidade: subtítulo com o dia sob o título, sem sobrelinha nem dia na linha", () => {
    const quality = read("pages/quality.vue");
    expect(quality).toContain(':subtitle="qualitySubtitle"');
    expect(quality).not.toContain("Lotes fechados hoje' : 'Lotes fechados no dia'");
    expect(quality).not.toMatch(/<OperatorPeriodPicker/);
  });

  it("o ao vivo mora no #status do cabeçalho do kit (no celular, a 2ª linha da barra)", () => {
    const header = read("components/ProductionHeader.vue");
    expect(header).toContain("data-header-subtitle");
    expect(header).toMatch(/<template #status>\s*<OperatorLiveStatus/);
    // Sem régua própria: o kit escolhe o desenho do celular pelo CSS.
    expect(header).not.toContain("useMediaQuery");
  });
});
