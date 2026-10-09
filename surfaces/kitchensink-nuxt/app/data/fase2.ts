// Dados de exemplo da proposta da fase 2 (rodada 2). Material de decisão: morre com a
// página `/proposal/fase2`. Os nomes longos são de propósito: texto da casa quebra,
// nunca corta, e as telas compostas têm de provar isso a 390.
import type {
  Fase2FilterDimension,
  Fase2Material,
  Fase2Order,
  Fase2Product,
  SavedView,
} from "../types/fase2";

export const brl = (q: number) => (q / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const QUEUE: Fase2Order[] = [
  { ref: "1049", customer: "Carla Mendes de Albuquerque Ferreira", channel: "iFood", stage: "Atrasado", total_q: 9320, eta: "10:25", payment: "Pix", items: ["1 Quiche lorraine", "2 Sanduíche de presunto e brie"] },
  { ref: "1051", customer: "Bruno Lima", channel: "iFood", stage: "Novo", total_q: 6240, eta: "10:55", payment: "Pix", items: ["4 Madeleine", "1 Chocolate quente"] },
  { ref: "1053", customer: "Fábio Nakamura", channel: "iFood", stage: "Novo", total_q: 2210, eta: "10:50", payment: "Pix", items: ["1 Croque-monsieur"] },
  { ref: "1055", customer: "Heitor Alves", channel: "iFood", stage: "Novo", total_q: 3780, eta: "11:20", payment: "Pix", items: ["1 Brioche", "2 Café coado"] },
  { ref: "1056", customer: "Isabela Torres", channel: "iFood", stage: "Em preparo", total_q: 5120, eta: "11:05", payment: "Pix", items: ["2 Pain au chocolat", "1 Suco de laranja"] },
  { ref: "1058", customer: "João Pedro Vasconcelos", channel: "iFood", stage: "Em preparo", total_q: 7460, eta: "11:15", payment: "Pix", items: ["1 Tarte au citron", "2 Café com leite"] },
  { ref: "1060", customer: "Larissa Okamoto", channel: "iFood", stage: "Pronto", total_q: 1890, eta: "10:45", payment: "Pix", items: ["1 Baguete tradicional"] },
];

const HISTORY_BASE: Omit<Fase2Order, "ref" | "date">[] = [
  { customer: "Ana Souza", channel: "Site", stage: "Retirado", total_q: 4870, eta: "08:40", payment: "Pix", items: ["2 Croissant", "1 Pain au chocolat", "1 Café coado"] },
  { customer: "Carla Mendes de Albuquerque Ferreira", channel: "iFood", stage: "Entregue", total_q: 9320, eta: "10:25", payment: "Pix", items: ["1 Quiche lorraine", "2 Sanduíche de presunto e brie"] },
  { customer: "Diego Rocha", channel: "Balcão", stage: "Retirado", total_q: 1590, eta: "07:30", payment: "Dinheiro", items: ["1 Baguete tradicional"] },
  { customer: "Bruno Lima", channel: "iFood", stage: "Entregue", total_q: 6240, eta: "10:55", payment: "Pix", items: ["4 Madeleine", "1 Chocolate quente"] },
  { customer: "Elisa Campos", channel: "Site", stage: "Cancelado", total_q: 12880, eta: "11:10", payment: "Cartão", items: ["1 Tarte au citron inteira", "6 Macaron de framboesa"] },
  { customer: "Fábio Nakamura", channel: "iFood", stage: "Entregue", total_q: 2210, eta: "10:50", payment: "Pix", items: ["1 Croque-monsieur"] },
  { customer: "Gabriela Prado", channel: "iFood", stage: "Entregue", total_q: 5400, eta: "11:00", payment: "Pix", items: ["2 Pão de campanha"] },
  { customer: "Heitor Alves", channel: "Site", stage: "Retirado", total_q: 3780, eta: "11:20", payment: "Pix", items: ["1 Brioche", "2 Café coado"] },
];

export const HISTORY: Fase2Order[] = Array.from({ length: 24 }, (_, index) => {
  const base = HISTORY_BASE[index % HISTORY_BASE.length]!;
  const day = 9 - Math.floor(index / 3);
  return {
    ...base,
    ref: String(1047 - index * 3),
    date: `${String(day).padStart(2, "0")}/10`,
  };
});

export const ORDER_DIMENSIONS: Fase2FilterDimension[] = [
  {
    id: "channel",
    label: "Canal",
    options: [
      { value: "ifood", label: "iFood", count: 7 },
      { value: "site", label: "Site", count: 6 },
      { value: "balcao", label: "Balcão", count: 5 },
    ],
  },
  {
    id: "payment",
    label: "Pagamento",
    options: [
      { value: "pix", label: "Pix", count: 9 },
      { value: "card", label: "Cartão", count: 8 },
      { value: "cash", label: "Dinheiro", count: 1 },
    ],
  },
  {
    id: "fulfillment",
    label: "Recebimento",
    options: [
      { value: "delivery", label: "Entrega", count: 10 },
      { value: "pickup", label: "Retirada", count: 8 },
    ],
  },
];

export const ORDER_QUICK = [
  { value: "late", label: "Atrasados" },
  { value: "new", label: "Novos" },
  { value: "unpaid", label: "Pagamento pendente" },
];

export const PERIODS = [
  { value: "today", label: "Hoje" },
  { value: "yesterday", label: "Ontem" },
  { value: "tomorrow", label: "Amanhã" },
  { value: "7d", label: "Últimos 7 dias" },
  { value: "month", label: "Este mês" },
];

export const ORDER_GROUPS = [
  { value: "", label: "Sem agrupar" },
  { value: "channel", label: "Canal" },
  { value: "stage", label: "Situação" },
  { value: "customer", label: "Cliente" },
];

export const ORDER_TEXT_FIELDS = [
  { value: "customer", label: "Cliente" },
  { value: "ref", label: "Pedido" },
  { value: "product", label: "Produto" },
];

export const ORDER_VIEWS: SavedView[] = [
  { id: "ifood-late", name: "iFood atrasados", summary: "Atrasados · Canal: iFood", pinned: true, state: { quick: ["late"], values: { channel: ["ifood"] } } },
  { id: "pix-today", name: "Pix de hoje", summary: "Hoje · Pagamento: Pix", pinned: false, state: { values: { payment: ["pix"] } } },
  { id: "tomorrow", name: "Encomendas de amanhã", summary: "Amanhã · Recebimento: Retirada", pinned: false, shared: true, state: { period: "tomorrow", values: { fulfillment: ["pickup"] } } },
];

export const MATERIALS: Fase2Material[] = [
  { sku: "FAR-T1-25", name: "Farinha de trigo tipo 1 Moinho Paraná, saco de 25 kg", category: "Farinhas", supplier: "Moinho Paraná", stock: "180 kg", min: "100 kg", low: false },
  { sku: "FAR-INT-5", name: "Farinha de trigo integral fina, pacote de 5 kg", category: "Farinhas", supplier: "Moinho Paraná", stock: "8 kg", min: "15 kg", low: true },
  { sku: "FAR-CEN-1", name: "Farinha de centeio", category: "Farinhas", supplier: "Grãos do Sul", stock: "6 kg", min: "5 kg", low: false },
  { sku: "MAN-SEM-5", name: "Manteiga sem sal extra, bloco de 5 kg", category: "Laticínios", supplier: "Laticínios Vale do Testo", stock: "12 kg", min: "20 kg", low: true },
  { sku: "LEI-INT-1", name: "Leite integral", category: "Laticínios", supplier: "Laticínios Vale do Testo", stock: "36 L", min: "24 L", low: false },
  { sku: "CRE-35-1", name: "Creme de leite fresco 35% de gordura", category: "Laticínios", supplier: "Laticínios Vale do Testo", stock: "4 kg", min: "6 kg", low: true },
  { sku: "OVO-GR-30", name: "Ovo branco grande, bandeja com 30", category: "Ovos", supplier: "Granja Bom Dia", stock: "210 un", min: "120 un", low: false },
  { sku: "ACU-REF-5", name: "Açúcar refinado", category: "Açúcares", supplier: "Atacado Central", stock: "25 kg", min: "10 kg", low: false },
  { sku: "ACU-CNF-1", name: "Açúcar de confeiteiro", category: "Açúcares", supplier: "Atacado Central", stock: "2 kg", min: "3 kg", low: true },
  { sku: "FER-SEC-500", name: "Fermento biológico seco instantâneo, pacote de 500 g", category: "Fermentos", supplier: "Atacado Central", stock: "3 kg", min: "2 kg", low: false },
  { sku: "SAL-MAR-1", name: "Sal marinho fino", category: "Temperos", supplier: "Atacado Central", stock: "9 kg", min: "4 kg", low: false },
  { sku: "CHO-70-1", name: "Chocolate amargo 70% em gotas para forneamento", category: "Chocolates", supplier: "Cacau Brasil Distribuidora", stock: "1,5 kg", min: "4 kg", low: true },
  { sku: "CHO-BAS-1", name: "Bastão de chocolate para pain au chocolat", category: "Chocolates", supplier: "Cacau Brasil Distribuidora", stock: "3 kg", min: "2 kg", low: false },
  { sku: "AME-LAM-1", name: "Amêndoa laminada", category: "Oleaginosas", supplier: "Grãos do Sul", stock: "2 kg", min: "1 kg", low: false },
  { sku: "FRA-CON-1", name: "Framboesa congelada", category: "Frutas", supplier: "Frutas da Serra", stock: "0,8 kg", min: "2 kg", low: true },
  { sku: "LIM-SIC-1", name: "Limão-siciliano", category: "Frutas", supplier: "Frutas da Serra", stock: "40 un", min: "20 un", low: false },
  { sku: "CAF-GRA-1", name: "Café em grão torra média", category: "Bebidas", supplier: "Torrefação Londrina", stock: "6 kg", min: "5 kg", low: false },
  { sku: "EMB-SAC-P", name: "Saco de papel kraft pequeno", category: "Embalagens", supplier: "Embalagens Norte", stock: "800 un", min: "500 un", low: false },
];

export const MATERIAL_DIMENSIONS: Fase2FilterDimension[] = [
  {
    id: "category",
    label: "Categoria",
    options: ["Farinhas", "Laticínios", "Ovos", "Açúcares", "Chocolates", "Frutas"].map((label) => ({
      value: label,
      label,
      count: MATERIALS.filter((item) => item.category === label).length,
    })),
  },
  {
    id: "supplier",
    label: "Fornecedor",
    options: ["Moinho Paraná", "Laticínios Vale do Testo", "Atacado Central", "Cacau Brasil Distribuidora"].map((label) => ({
      value: label,
      label,
      count: MATERIALS.filter((item) => item.supplier === label).length,
    })),
  },
];

export const MATERIAL_QUICK = [
  { value: "low", label: "Abaixo do mínimo" },
  { value: "no-supplier", label: "Sem fornecedor" },
  { value: "count-due", label: "Contagem vencida" },
];

export const MATERIAL_GROUPS = [
  { value: "", label: "Sem agrupar" },
  { value: "supplier", label: "Fornecedor" },
  { value: "category", label: "Categoria" },
];

export const MATERIAL_VIEWS: SavedView[] = [
  { id: "dairy-low", name: "Laticínios para pedir", summary: "Abaixo do mínimo · Categoria: Laticínios", pinned: false, state: { quick: ["low"], values: { category: ["Laticínios"] } } },
];

export const PRODUCTS: Fase2Product[] = [
  { sku: "CROI", name: "Croissant", price_q: 1150 },
  { sku: "PAC", name: "Pain au chocolat", price_q: 1290 },
  { sku: "BAG", name: "Baguete tradicional", price_q: 1590 },
  { sku: "CAMP", name: "Pão de campanha", price_q: 2700, stock: "3 restantes" },
  { sku: "BRIO", name: "Brioche", price_q: 1490 },
  { sku: "MAD", name: "Madeleine", price_q: 690 },
  { sku: "QUI", name: "Quiche lorraine", price_q: 3290 },
  { sku: "CROQ", name: "Croque-monsieur", price_q: 2210 },
  { sku: "TAR", name: "Tarte au citron", price_q: 1890 },
  { sku: "MAC", name: "Macaron de framboesa", price_q: 890, stock: "Indisponível" },
  { sku: "CAFE", name: "Café coado", price_q: 690 },
  { sku: "CHOC", name: "Chocolate quente", price_q: 1490 },
];
