# Sonda ao vivo do PDV — texto cortado

`copy-overflow.live.spec.ts` percorre as telas principais do PDV em **1366×768,
1280×800 e 1024×768**, com a barra lateral **compacta** e **estendida**, e mede
todo elemento com texto que não cabe na própria caixa
(`surfaces/operator-kit/tests/support/clippedText.js`):

| tipo | o que é |
|---|---|
| `ellipsis` | `text-overflow: ellipsis` cortando de fato ("Dividir co…") |
| `clip-x` / `clip-y` | overflow oculto com o conteúdo maior que a caixa (`line-clamp`) |
| `clip-parent` | o texto passa da borda de um ancestral que corta |
| `spill` | o texto sai da própria caixa ou da tela |
| `crushed` | a coluna ficou tão estreita que a frase vira uma palavra por linha |

O critério (`violatesHouseRule`) é o da casa: **aviso e título nunca se cortam,
coluna esmagada nunca passa**; o resto só passa cortado com o texto INTEIRO no
`title` (dado do usuário: nome de produto, cliente, resumo da comanda). O rótulo
fixo de botão nem chega aqui: `truncate` em texto escrito no template reprova na
varredura estática `operator-kit/tests/guardrails.copyNeverTruncates.test.ts`,
que roda em todo CI.

## Por que ao vivo, e não no mock

As telas que estouram são as **cheias**: comanda com itens, encomenda de entrega
com cliente, endereço e data, os bloqueios do pagamento, a semana de encomendas.
O `mockBackend.mjs` só sabe dizer 401. Esta sonda roda contra um PDV de verdade:
Django semeado + pos-nuxt.

## Como rodar

```bash
# 1. Django semeado (banco local à parte, para não mexer no seu)
createdb shopman_sonda
DATABASE_URL=postgres://localhost/shopman_sonda DJANGO_DEBUG=1 .venv/bin/python manage.py migrate
DATABASE_URL=postgres://localhost/shopman_sonda DJANGO_DEBUG=1 .venv/bin/python manage.py seed --profile qa
# o bloqueio "Entrega com nota fiscal: falta o CPF" só aparece com um resolver
# fiscal que emita na entrega (o do alpha):
SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.on_request_or_tax_id,shopman.shop.fiscal_resolvers.eletronic_payment,shopman.shop.fiscal_resolvers.deferred_settlement" \
DATABASE_URL=postgres://localhost/shopman_sonda DJANGO_DEBUG=1 .venv/bin/python manage.py runserver 127.0.0.1:8811

# 2. o PDV apontando para ele
cd surfaces/pos-nuxt
NUXT_DJANGO_BASE_URL=http://127.0.0.1:8811 npx nuxi dev --port 3312

# 3. a sonda (usuário com senha que abre o caixa — o superusuário do seed)
PDV_LIVE_URL=http://127.0.0.1:3312 PDV_LIVE_USER=<usuário> PDV_LIVE_PASSWORD=<senha> \
  PDV_LIVE_SHOTS=/tmp/sonda-shots PDV_LIVE_REPORT=/tmp/sonda.json \
  npm run test:live
```

Variáveis opcionais: `PDV_LIVE_RAILS` (`compact,extended`), `PDV_LIVE_CUSTOMER`
(cliente com endereço salvo; padrão do seed: Ana Ferreira), `PDV_LIVE_PRODUCTS`
(nomes separados por `|`). `PDV_LIVE_SHOTS` guarda um retrato por tela medida;
`PDV_LIVE_REPORT` guarda todos os achados (inclusive os aceitos) e os passos que
não acharam o que procuravam (`skipped`).

A sonda cria comandas e fecha uma venda de verdade no banco que você apontar.
Use um banco descartável.
