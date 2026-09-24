// Mock backend mínimo p/ os e2e do Shopman Apps: devolve uma projection de hub autenticada
// (com tiles) para `/backstage/hub/`, e `{}` no resto. Não simula permissões reais — os
// tiles daqui são fixos, só para exercitar o launcher (grade, links, saudação, offline).
// O login efetivo + filtragem por permissão rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8797);

const HUB = {
  hub: {
    operator_name: "Ana",
    tiles: [
      { ref: "pos", label: "PDV", description: "Vender no balcão", icon: "shopping-basket", url: "http://127.0.0.1:3002/", kind: "launch" },
      { ref: "gestor", label: "Gestor de Pedidos", description: "Fila e acompanhamento", icon: "square-kanban", url: "http://127.0.0.1:3004/", kind: "launch" },
      // Os dois tiles com o texto MAIS LONGO do registro real
      // (`shopman/backstage/projections/hub.py`): é neles que a grade de duas colunas do
      // celular quebrava em alturas diferentes. Trocar o registro sem trocar estes dois
      // deixa a medida do `mobileTiles.spec.ts` medindo um caso fácil.
      { ref: "purchase", label: "Compras", description: "Comprar e receber insumos", icon: "package", url: "http://127.0.0.1:3008/", kind: "launch" },
      { ref: "production", label: "Produção", description: "Produção e lotes", icon: "croissant", url: "http://127.0.0.1:3005/", kind: "launch" },
      { ref: "loja", label: "Loja online", description: "Abrir a loja do cliente", icon: "store", url: "/admin/shop/shop/", kind: "external" },
    ],
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
