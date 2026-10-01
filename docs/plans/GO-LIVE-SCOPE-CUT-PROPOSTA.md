# Proposta de corte de escopo do go-live (01/10/2026)

> **Proposta, não decisão.** Nada aqui altera o
> [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md). O dono aprova, recusa
> ou ajusta linha a linha; só então o backlog muda. Estado comercial, owners e
> evidência continuam morando na
> [matriz canônica](GO-LIVE-READINESS-PLAN.md).

## O problema em uma frase

A linha 77 do backlog diz que o go-live "só dispara com **todas** as ✅
entregues" (as 11 frentes de 26/06). Medido em 01/10/2026 (`main` em
`bf415ad98`), seis das onze já estão entregues ou desatualizadas no próprio
backlog, e as que faltam dependem de credencial, homologação externa ou decisão
do dono. Do jeito que está escrita, a regra trava o go-live por frentes que não
são condição para vender pão no balcão e na loja online.

## As 11 frentes, medidas

Legenda da proposta: **DENTRO** = condição do go-live; **FORA** = vira
pós-go-live, com o custo dito; **ENTREGUE** = já não trava nada, sai da conta.

| # | Frente (como o backlog nomeia) | Estado medido | Prova | Proposta | Custo do corte |
|---|---|---|---|---|---|
| 1 | Gestor de pedidos ao estado da arte | Código no ar, `orders-nuxt` é check obrigatório. QA autenticado existe de 28/08 (admin e gerente); depois das mudanças de setembro (#1231 a #1328), NÃO VERIFICADO | `docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md`; PRs #1231, #1258, #1328 | **DENTRO** (só a QA física da matriz, que já é item do pré-flight §5) | Nenhum corte: o que falta é QA, não código |
| 2 | Canal: Loja online (retirada) | No ar no ambiente técnico; smoke cobre `/ready/`, menu, checkout não mutante e SSR | matriz, linha "Smoke pós-deploy" (run 36521633479); #1329 | **DENTRO** | Nenhum corte. Condição real: ensaio do Pix real (pré-flight §4, D-006, D22) |
| 3 | Canal: PDV / balcão | `pos-nuxt` no ar, check obrigatório | `.do/app.alpha-subdomains.yaml:36`; #1218 | **DENTRO** | Nenhum corte. Impressão, gaveta e som seguem PENDENTES na matriz (QA física) |
| 4 | Canal: Entrega / delivery | Código de endereço existe (Places com fallback ViaCEP, mapa, pin, distância). Chave Maps declarada como SECRET no spec; valor e cota no vivo NÃO VERIFICADO. Pedido com entrega de ponta a ponta: NÃO VERIFICADO | `surfaces/storefront-nuxt/app/components/AddressPicker.vue`; `shopman/shop/services/delivery_distance.py`; `.do/app.alpha-subdomains.yaml:785-790` | **FORA no primeiro dia** (entra quando um pedido de entrega real fechar de ponta a ponta) | Cliente da loja online só tem retirada; quem quer entrega usa iFood ou telefone. Risco baixo: o canal fica desligado, não quebrado. Pós-go-live: QA de entrega com a chave do vivo e o entregador da casa |
| 5 | Canal: WhatsApp conversacional (ManyChat) | O plano foi superado pelo WHATSAPP-CONCIERGE-PLAN (03/09); webhooks registrados e o Concierge fecha pedido no código. Spec versionado: **desligado** (`SHOPMAN_CONCIERGE_ENABLED='false'`, `READ_ONLY='true'`). Valor vivo: NÃO VERIFICADO. Matriz: escopo DESCONHECIDO | `config/urls.py:169-177`; `shopman/storefront/concierge/tools.py`; `.do/app.alpha-subdomains.yaml:550-570`; #1131, #1132 | **FORA** | Cliente não fecha pedido conversando no WhatsApp; continua recebendo notificação e link de acesso por WhatsApp (isso não depende do Concierge). Pós-go-live: ligar por env com autorização, depois de aprovar templates na Meta/ManyChat |
| 6 | Sincronização com catálogos externos | Feed pull Google/Meta e push Meta entregues; push Meta só com `META_CATALOG_PROJECTION=1`. Falta homologação Meta, vínculo ao WhatsApp, cadastro no Merchant Center | `docs/plans/CATALOG-SYNC-EXTERNO-PLAN.md:7-9`; #1255, #957 | **FORA** | Produtos não aparecem no catálogo do Instagram/Facebook nem no Google Shopping no dia 1. Nenhum risco ao pedido. Pós-go-live: homologação nas contas do dono |
| 7 | Media persistente (Spaces/S3) | **Não feito.** `STORAGES["default"]` é `FileSystemStorage`; nenhum bucket nos specs. Fotos de produto NÃO dependem disso (estáticos do storefront em `img.`). D6 (30/09) mandou upload para o R2, depois | `config/settings.py:575-589`; `PENDING-DECISIONS.md` (D6) | **FORA** | Arquivo enviado pelo Admin (anexo, mídia avulsa) some no próximo deploy. Mitigação até lá: não usar upload em produção; anexos de receita já são "Referências externas" (#1332). Pós-go-live: storage durável (R2, conforme D6) |
| 8 | Shelf life perecível | Precedência travada por teste (27/06); validator composto ativo; janela rígida **desligada** por padrão (só aviso no Admin) | `config/settings.py:1598-1604`; `packages/stockman/shopman/stockman/tests/test_batch_consistency.py` | **ENTREGUE** (a decisão de ligar `STOCKMAN_STRICT_SHELF_LIFE_WINDOW` vira pós-go-live) | Lote com validade além da janela do produto gera aviso, não bloqueio. Risco baixo com produção do dia; pós-go-live: decidir se a trava liga |
| 9 | Revisão reversa do PDV (Fase C) | "Reconciliação concluída em 2026-09-29", nenhuma lacuna nova | `docs/plans/POS-FASE-C-REVISION.md:7-9` | **ENTREGUE** | Nenhum. Itens "a verificar" funcionais caem na QA física do pré-flight |
| 10 | Surface convergence | "CONVERGÊNCIA COMPLETA (2026-06-27)"; sem template HTMX de POS/KDS; KDS é Nuxt e check obrigatório | `docs/plans/completed/SURFACE-CONVERGENCE-PLAN.md:13-16`; `ls surfaces/` | **ENTREGUE** | Nenhum |
| 11 | Playwright E2E como gate | "Storefront E2E (Playwright)" é check obrigatório de `main`, roda em `pull_request` e `merge_group` | `.github/required-status-checks.json`; `.github/workflows/omotenashi-gate.yml` | **ENTREGUE** | Nenhum. A suíte cobre a loja; operador é coberto pelo "Browser QA" |

### Resumo

- **Entregues e fora da conta:** 8, 9, 10, 11.
- **Dentro do go-live:** 1, 2, 3 (nenhuma pede código novo; pedem QA física e o
  ensaio do Pix real, que já são itens do [pré-flight](../runbooks/go-live-preflight.md)).
- **Fora, pós-go-live:** 4 (entrega própria), 5 (WhatsApp conversacional), 6
  (catálogos externos), 7 (media persistente).

O go-live proposto é **retirada na loja online + balcão + gestor de pedidos**,
com pagamento real. É o mesmo corte que a matriz já pede para assinar na linha
"Escopo v1 de iFood, ManyChat/Concierge, Machine, fiscal e Marketing"
(DESCONHECIDO): esta proposta responde a parte de ManyChat/Concierge e deixa
iFood, Machine, fiscal e Marketing para a assinatura própria daquela linha.

## Mudança de texto proposta (para aprovar em um minuto)

**Linha 77 hoje:**

> 3. O go-live (no GO-LIVE-READINESS-PLAN) só dispara com **todas** as ✅ entregues.

**Linha 77 proposta:**

> 3. O go-live (no GO-LIVE-READINESS-PLAN) dispara com as frentes **1, 2 e 3**
>    (gestor de pedidos, loja online com retirada, PDV) prontas e com QA física,
>    mais o ensaio do Pix real do pré-flight. As frentes 4, 5, 6 e 7 (entrega
>    própria, WhatsApp conversacional, catálogos externos, media persistente)
>    passam a pós-go-live, cada uma com o custo registrado em
>    [GO-LIVE-SCOPE-CUT-PROPOSTA](GO-LIVE-SCOPE-CUT-PROPOSTA.md). As frentes 8 a
>    11 estão entregues. Decidido por Pablo em DD/MM/2026.

Acompanham a mesma aprovação, para o backlog não se contradizer:

- **Linha 6** ("o go-live real só dispara quando o 'deve entrar no v1' abaixo
  estiver fechado"): passa a apontar para a linha 77 nova.
- **Linha 57** (nota de sequenciamento, "o go-live só dispara quando **todas**
  as ✅ estiverem entregues"): mesma troca.
- **Tabela "pós-v1"**: ganha as frentes 4, 5, 6 e 7, com o custo em uma linha.

## O que esta proposta NÃO resolve

Cortar escopo não destrava sozinho o go-live. Seguem abertos na matriz, com ou
sem corte: perfil comercial do runtime, drift do spec vivo, credenciais externas
(Efí, Stripe, Focus), ensaio de restore pelo fork (403, ver
[backup-e-restore](../runbooks/backup-e-restore.md#ensaio-de-01102026)),
`production-readiness` no ambiente alvo, QA física, impressão/gaveta/som e o
GO/NO-GO assinado.

## NÃO VERIFICADO

- Valores de env no app vivo da DO (Concierge, chaves Maps,
  `META_CATALOG_PROJECTION`): só o spec versionado foi lido.
- QA autenticado do Gestor de pedidos depois das mudanças de setembro.
- Pedido com entrega de ponta a ponta no ambiente vivo.
