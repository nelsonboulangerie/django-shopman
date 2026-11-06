// Beta de 05/11/2026, frente Gestor/Catálogo/Clientes: cada regra pura que trava um
// achado. O id do achado está no nome do teste.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  availabilityRowLabel,
  availabilitySummary,
  cellState,
  channelPriceError,
  phoneChannelChips,
  rowStatus,
  weighedChannelsNotice,
} from "../app/presentation/catalog";
import {
  customerLabel,
  mergedNotice,
  undoMergeDescription,
} from "../app/presentation/customers";
import { accessResolved } from "../app/presentation/gestorSections";
import { channelHasBindingReview } from "../app/presentation/ifoodStore";
import type {
  CatalogRowProjection,
  SurfaceCellProjection,
  SurfaceProjection,
} from "../app/types/catalog";

const surface = (over: Partial<SurfaceProjection> = {}): SurfaceProjection => ({
  ref: "web",
  name: "Loja online",
  short_name: "Loja",
  is_projection_target: false,
  sync_status: "ok",
  kind: "channel",
  transactional: true,
  icon: "",
  output_path: "",
  ...over,
});

const cell = (over: Partial<SurfaceCellProjection> = {}): SurfaceCellProjection => ({
  surface_ref: "web",
  in_listing: true,
  is_published: true,
  is_sellable: true,
  available: true,
  price_q: 600,
  price_display: "R$ 6,00",
  sync_status: "",
  sync_error: "",
  synced_at: "",
  ...over,
});

const row = (over: Partial<CatalogRowProjection> = {}): CatalogRowProjection =>
  ({
    sku: "TONICA",
    name: "Água tônica",
    image_url: "",
    primary_collection: "",
    primary_collection_name: "",
    is_active: true,
    is_published: true,
    is_sellable: true,
    base_price_q: 600,
    base_price_display: "R$ 6,00",
    edit_url: "",
    stock_tracked: false,
    stock_qty: null,
    sold_out: false,
    low_stock: false,
    replenish_qty: 0,
    keywords: [],
    cells: [],
    pim_complete: false,
    hidden_by_inactive_collection: false,
    ...over,
  }) as CatalogRowProjection;

describe("CMP-08 e GES-10: só no balcão é pausar os remotos; oculto sai de todos", () => {
  const counterOnly = row({
    cells: [
      cell({ surface_ref: "pdv" }),
      cell({ surface_ref: "web", is_published: false, is_sellable: false, available: false }),
    ],
  });

  it("PDV vendendo e remotos pausados: selo 'Só no balcão', sem esmaecer", () => {
    expect(rowStatus(counterOnly)).toMatchObject({ off: false, label: "Só no balcão" });
  });

  it("um remoto vendendo: sem selo", () => {
    const everywhere = row({ cells: [cell({ surface_ref: "pdv" }), cell({ surface_ref: "web" })] });
    expect(rowStatus(everywhere).label).toBe("");
  });

  it("oculto no catálogo: o PDV também diz Oculto (GES-10)", () => {
    const hidden = row({ is_published: false, cells: [cell({ surface_ref: "pdv", available: false })] });
    expect(cellState(hidden, hidden.cells[0]!)).toBe("unpublished");
    expect(rowStatus(hidden)).toMatchObject({ off: true, label: "Oculto" });
  });
});

describe("GES-03: o selo do bloco não diz 'À venda em todos' onde o produto não está", () => {
  it("canal sem vínculo não é falta nem venda", () => {
    expect(
      availabilitySummary([
        { state: "available", since: "" },
        { state: "not_listed", since: "" },
        { state: "not_listed", since: "" },
      ]),
    ).toEqual({ color: "neutral", label: "À venda em 1 de 3" });
  });

  it("todos vendendo continua 'À venda em todos'", () => {
    expect(availabilitySummary([{ state: "available", since: "" }])).toEqual({
      color: "success",
      label: "À venda em todos",
    });
  });

  it("pausado pelo vínculo vira 'Pausado' (GES-26)", () => {
    expect(
      availabilitySummary([
        { state: "paused", since: "" },
        { state: "available", since: "" },
      ]),
    ).toEqual({ color: "error", label: "Pausado em 1 de 2" });
  });

  it("a linha diz 'Não incluído'", () => {
    expect(availabilityRowLabel({ state: "not_listed", kind: "sale" })).toBe("Não incluído");
  });
});

describe("GES-02: Vendido por peso avisa antes de salvar", () => {
  it("ligar diz de quais canais sai e que volta", () => {
    expect(
      weighedChannelsNotice({
        savedUnit: "un",
        draftUnit: "kg",
        remoteChannels: ["Loja online", "iFood", "WhatsApp"],
      }),
    ).toBe(
      "Vendido só no balcão: o preço final sai da balança. Ao salvar, sai de Loja online, iFood e WhatsApp; desmarcar depois traz de volta.",
    );
  });

  it("desligar diz que volta", () => {
    expect(
      weighedChannelsNotice({ savedUnit: "kg", draftUnit: "un", remoteChannels: [] }),
    ).toBe("Ao salvar, volta para os canais de onde saiu por ser vendido por peso.");
  });

  it("sem mudança de unidade, nada a avisar", () => {
    expect(
      weighedChannelsNotice({ savedUnit: "un", draftUnit: "un", remoteChannels: ["iFood"] }),
    ).toBe("");
  });
});

describe("GES-05: preço do canal maior que zero, dito no campo", () => {
  it("zero e negativo são recusados com o porquê", () => {
    expect(channelPriceError("0")).toBe("O preço precisa ser maior que zero.");
    expect(channelPriceError("0,00")).toBe("O preço precisa ser maior que zero.");
    expect(channelPriceError("-3")).toBe("O preço precisa ser maior que zero.");
  });

  it("texto que não é preço pede o formato", () => {
    expect(channelPriceError("abc")).toBe("Informe o preço em reais, como 12,50.");
  });

  it("preço positivo passa", () => {
    expect(channelPriceError("12,50")).toBe("");
  });
});

describe("GES-19: no celular, o canal desce para a linha do produto", () => {
  it("uma pílula por canal de venda onde o produto está, com preço ou estado", () => {
    const r = row({
      cells: [
        cell({ surface_ref: "pdv", price_display: "R$ 5,00" }),
        cell({ surface_ref: "web", is_sellable: false }),
        cell({ surface_ref: "ifood", in_listing: false }),
      ],
    });
    const surfaces = [
      surface({ ref: "pdv", short_name: "PDV" }),
      surface({ ref: "web", short_name: "Loja" }),
      surface({ ref: "ifood", short_name: "iFood" }),
      surface({ ref: "meta", short_name: "Meta", transactional: false }),
    ];
    expect(phoneChannelChips(r, surfaces)).toEqual([
      { ref: "pdv", label: "PDV R$ 5,00", tone: "success" },
      { ref: "web", label: "Loja pausado", tone: "warning" },
    ]);
  });

  it("as colunas de canal do Catálogo são de apoio (somem no celular)", () => {
    const page = readFileSync(new URL("../app/pages/catalog.vue", import.meta.url), "utf8");
    const columns = page.slice(page.indexOf("const catalogColumns"), page.indexOf("const catalogRowClass"));
    expect(columns).toMatch(/surfaceColumnId\(surface\.ref\)[\s\S]*supporting: true/);
  });
});

describe("GES-18: a barra de Clientes quebra a linha no tablet", () => {
  const page = readFileSync(new URL("../app/pages/customers/index.vue", import.meta.url), "utf8");

  it("o cabeçalho não trava os filtros numa linha só", () => {
    const header = page.slice(page.indexOf("<OperatorPageHeader"), page.indexOf(">", page.indexOf("<OperatorPageHeader")));
    expect(header).not.toContain(':filters-wrap="false"');
    expect(page).toMatch(/class="flex flex-wrap items-center gap-3" data-customers-toolbar/);
  });

  it("o telefone não quebra no meio", () => {
    expect(page).toMatch(/class="whitespace-nowrap"[\s\S]{0,120}data-customer-phone/);
  });
});

describe("GES-09: Revisar vínculos só no canal com catálogo externo", () => {
  it("só o iFood", () => {
    expect(channelHasBindingReview("ifood")).toBe(true);
    expect(channelHasBindingReview("web")).toBe(false);
    expect(channelHasBindingReview("pdv")).toBe(false);
  });
});

describe("GES-22: a grade de Ajustes espera as permissões", () => {
  it("pendente segura; sucesso e erro liberam", () => {
    expect(accessResolved(["success", "pending", "success"])).toBe(false);
    expect(accessResolved(["idle", "success"])).toBe(false);
    expect(accessResolved(["success", "error", "success"])).toBe(true);
  });
});

describe("GES-14: unificação contada com nomes", () => {
  it("o aviso usa nome e código", () => {
    expect(
      mergedNotice({
        sourceName: "Ana Silva",
        sourceRef: "CUST-1",
        targetName: "Ana S.",
        targetRef: "CUST-2",
      }),
    ).toBe(
      "Ana Silva (CUST-1) foi unificado a Ana S. (CUST-2). Dá para desfazer em Unificações por 24 horas.",
    );
  });

  it("sem nome, só o código", () => {
    expect(customerLabel("", "CUST-1")).toBe("CUST-1");
  });

  it("a confirmação do desfazer não tem maiúscula no meio da frase", () => {
    expect(
      undoMergeDescription({
        source_name: "Ana Silva",
        source_ref: "CUST-1",
        target_name: "Ana S.",
        target_ref: "CUST-2",
        moved_label: "Nada além do próprio cadastro",
        loyalty_merged: false,
      }),
    ).toBe("Ana Silva (CUST-1) volta a ser um cadastro separado, com nada além do próprio cadastro.");
  });
});

describe("GES-25: o nome do produto no Tabelão abre o produto", () => {
  const page = readFileSync(new URL("../app/pages/catalog.vue", import.meta.url), "utf8");

  it("o nome é botão do conjunto mínimo que chama openDetail(row)", () => {
    const button = page.slice(page.lastIndexOf("<NuxtButton", page.indexOf("data-catalog-open")), page.indexOf("/>", page.indexOf("data-catalog-open")));
    expect(button).toContain(':label="row.name"');
    expect(button).toContain('@click.stop="openDetail(row)"');
    expect(button).toMatch(/variant="(solid|outline|ghost)"/);
  });
});

describe("GES-21: o dispositivo do posto ganha nome", () => {
  const page = readFileSync(new URL("../app/pages/workstations.vue", import.meta.url), "utf8");
  const composable = readFileSync(new URL("../app/composables/useWorkstations.ts", import.meta.url), "utf8");

  it("cada dispositivo tem Renomear ao lado de Desvincular", () => {
    expect(page).toMatch(/data-device-rename-start="device\.id"[\s\S]{0,80}@click="startDeviceRename\(device\)"/);
  });

  it("renomear é inline, com Salvar e Cancelar, e vai ao PATCH do dispositivo", () => {
    const form = page.slice(page.indexOf("data-device-rename\n"), page.indexOf("</NuxtForm>", page.indexOf("data-device-rename\n")));
    expect(form).toContain('@submit="saveDeviceRename(row.ref)"');
    expect(form).toContain('label="Cancelar"');
    expect(composable).toMatch(/function renameDevice[\s\S]*method: "PATCH", body: \{ label \}/);
  });
});

describe("GES-24: o preço mostrado tem um formato só", () => {
  const panel = readFileSync(new URL("../app/components/CatalogProductPanel.vue", import.meta.url), "utf8");

  it("o painel do produto mostra preço pelo formatBRL, como o Tabelão", () => {
    expect(panel).not.toContain("R$ ${centsToText");
    expect(panel).toContain("formatBRL(detail.base_price_q)");
  });
});
