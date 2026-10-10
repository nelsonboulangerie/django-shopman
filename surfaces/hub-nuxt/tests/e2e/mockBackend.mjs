// Mock backend mínimo p/ os e2e da Central: devolve uma projection de hub autenticada
// (com tiles) para `/backstage/hub/`, e `{}` no resto. Não simula permissões reais — os
// tiles daqui são fixos, só para exercitar o launcher (grade, links, saudação, offline).
// O login efetivo + filtragem por permissão rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8797);

// As pendências (UX-H1). Os instantes são relativos ao boot do mock: o teste lê o item e
// o gesto, não o número de minutos.
const ORDER_ITEM = {
  key: "gestor:order:WEB-20261003-K7Q2",
  app: "gestor",
  app_label: "Gestor de Pedidos",
  kind: "order_to_accept",
  title: "Pedido K7Q2 para aceitar",
  detail: "iFood · Ana Ferreira · R$ 58,40",
  waiting_since: new Date(Date.now() - 120_000).toISOString(),
  due_at: "",
  due_label: "",
  due_style: "",
  due_clock: "",
  time_mode: "since",
  attention: false,
  action_label: "Abrir pedido",
  url: "http://127.0.0.1:3004/WEB-20261003-K7Q2",
  slack_seconds: 120,
};

const PRODUCTION_ITEM = {
  key: "production:alert:9",
  app: "production",
  app_label: "Produção",
  kind: "alert",
  title: "Produção sem insumo suficiente",
  detail: "WO-2026-00022 falhou por estoque insuficiente",
  waiting_since: new Date(Date.now() - 240_000).toISOString(),
  due_at: "",
  due_label: "",
  due_style: "",
  due_clock: "",
  time_mode: "since",
  attention: false,
  action_label: "Resolver no contexto",
  url: "http://127.0.0.1:3005/close?q=WO-2026-00022",
  slack_seconds: 900,
};

const HUB = {
  hub: {
    operator_name: "Ana",
    tiles: [
      { ref: "pos", label: "PDV", description: "Vender no balcão", icon: "shopping-basket", url: "http://127.0.0.1:3002/", kind: "launch", status_attention: "", status_summary: "2 encomendas para retirar hoje", status_positive: "Caixa aberto", next_item: null },
      { ref: "gestor", label: "Gestor de Pedidos", description: "Fila e acompanhamento", icon: "square-kanban", url: "http://127.0.0.1:3004/", kind: "launch", status_attention: "1 para aceitar", status_summary: "11 ativos", next_item: ORDER_ITEM },
      // Os dois tiles com o texto MAIS LONGO do registro real
      // (`shopman/backstage/projections/hub.py`): é neles que a grade de duas colunas do
      // celular quebrava em alturas diferentes. Trocar o registro sem trocar estes dois
      // deixa a medida do `mobileTiles.spec.ts` medindo um caso fácil.
      { ref: "purchase", label: "Compras", description: "Comprar e receber insumos", icon: "package", url: "http://127.0.0.1:3008/", kind: "launch", status_attention: "", status_summary: "", next_item: null },
      { ref: "production", label: "Produção", description: "Produção e lotes", icon: "croissant", url: "http://127.0.0.1:3005/", kind: "launch", status_attention: "", status_summary: "5 de 15 lotes finalizados hoje", next_item: PRODUCTION_ITEM },
      { ref: "loja", label: "Loja online", description: "Abrir a loja do cliente", icon: "store", url: "/admin/shop/shop/", kind: "external", status_attention: "", status_summary: "", next_item: null },
    ],
    queue: {
      total_count: 4,
      server_now: new Date().toISOString(),
    },
  },
};

const server = createServer((req, res) => {
  res.setHeader("content-type", "application/json");
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");

  if (req.url && /\/backstage\/hub\/?(\?|$)/.test(req.url)) {
    res.statusCode = 200;
    res.end(JSON.stringify(HUB));
    return;
  }

  res.statusCode = 200;
  res.end("{}");
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[hub-mock] listening on http://127.0.0.1:${port}`);
});
