# DELIVERY-EXTERNAL-LOGISTICS-PLAN — Despacho via serviço externo (TaOn / Taxi Machine)

> Entrega via logística externa de terceiros. **2026-07-07: a API existe e a integração
> first-class foi CONSTRUÍDA** — a TaOn roda sobre a **Machine** (Gaudium,
> api.taximachine.com.br) e a doc Postman chegou. O preço ao cliente segue nas faixas/zonas
> (`DeliveryDistanceBand` + `DeliveryZone`); a cotação da Machine é **custo interno** exibido
> no gestor (decisão Pablo, 2026-07-07).

---

## 1. Duas camadas

| Camada | O que é | Estado |
|---|---|---|
| **Integração Machine** | Despacho automático + status em tempo real + ações do operador no gestor. | ✅ construída (2026-07-07), aguarda credenciais + homologação |
| **Teleporte (fallback)** | Utilitário local que leva os dados de entrega para o form do serviço (clipboard). | ✅ entregue (2026-06-29) — fallback manual (API fora / entrega própria) |

---

## 2. Integração Machine — construída (2026-07-07)

Arquitetura (funil único; letras de status da Machine: D/G/P aguardando, A aceita, S na loja,
E em andamento, F finalizada, N não atendida, C cancelada):

```
READY (lifecycle._on_ready) + ChannelConfig.fulfillment.courier == "auto" + delivery
  → Directive courier.dispatch → adapter courier → POST /abrirSolicitacao → id_mch
       → Order.data["courier"] (schema em data-schemas.md) + SSE + agenda courier.sync

Status (2 vias → services/courier.apply_status, idempotente):
  webhooks/machine.py (push, ?token=)  ─┐
  CourierSyncHandler (poll reagendável) ┴→ E→DISPATCHED (notif. "saiu p/ entrega")
                                           F→DELIVERED (notif. "entregue")
                                           N/C→OperatorAlert + re-despacho no gestor
```

- **Adapter**: `shopman/shop/adapters/courier_machine.py` (borda HTTP única; dinheiro → `_q`;
  inerte em DEBUG via `SHOPMAN_MACHINE_ALLOW_IN_DEBUG`) + `courier_mock.py` (dev/testes).
  Contrato conferido contra o OpenAPI v1 em §2.1.
  Registro: `get_adapter("courier")` ← `Shop.integrations["courier"]` > `SHOPMAN_COURIER_ADAPTER`.
- **Config por canal**: `ChannelConfig.Fulfillment.courier` = `"none" | "auto"` (iFood tem
  logística própria = none; canal delivery próprio = auto). Config diz SE; adapter diz QUEM.
- **Gestor** (orders-nuxt, página do pedido): painel da corrida (timeline, entregador, rastreio,
  custo) + ações **Cotar entrega** (avulsa, sem abrir corrida), **Chamar/Re-despachar** e
  **Cancelar corrida** (só antes da coleta). Tempo real via SSE + poll.
- **Notificações**: reusa `order_dispatched`/`order_delivered`; link de rastreio do entregador
  entra como `{courier_tracking_suffix}` (auto-suprimível).
- **Redes de segurança preservadas**: `DELIVERY_AUTO_COMPLETE` (ETA+folga) e "Recebi" do cliente
  continuam; viram no-op quando o `F` da Machine chega antes.
- **Checks**: `SHOPMAN_E011` (credenciais em prod) e `SHOPMAN_W010` (sem webhook_token → polling).

### Go-live (pendências externas)
1. Credenciais da central: `MACHINE_API_USER/PASSWORD/API_KEY` + permissão "API - Entrega"
   (ver [GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md)).
2. Ligar: `SHOPMAN_COURIER_ADAPTER=shopman.shop.adapters.courier_machine` +
   `fulfillment.courier="auto"` no canal delivery. Polling ativo desde o dia 1.
3. Homologar webhook: `MACHINE_WEBHOOK_TOKEN` + `manage.py machine_register_webhook
   https://api.<dominio>`; conferir o primeiro evento real contra o payload documentado (§2.1,
   o endpoint também loga o corpo cru) e então reduzir ou zerar
   `Shop.defaults.delivery.courier_poll_seconds`.
4. Confirmar com a central: `MACHINE_FORMA_PAGAMENTO` (default `F` faturado) e `motivo_id`
   válido de cancelamento (`MACHINE_CANCEL_REASON_ID`).
5. Ensaio de homologação ponta a ponta:
   [courier-machine-homologacao](../runbooks/courier-machine-homologacao.md).

### 2.1 Contrato da API v1, conferido endereço a endereço (01/10/2026)

Fonte: OpenAPI v1 de docs.machine.global, `pages/v1/openapi-corridas.json` e
`pages/v1/openapi-entregas.json` (o adapter usa a API de **entregas**: paradas, link de
rastreio, permissão "API - Entrega"). O adapter fala v1 e fica em v1.

- **Bases**: produção `https://api.taximachine.com.br/api/integracao`; homologação
  `https://api-vendas.taximachine.com.br/api/integracao`. Mesma API Key nos dois.
- **Autenticação**: header `api-key` + `Authorization: Basic base64(usuario:senha)`
  (securitySchemes `ApiKeyAuth` + `basicAuth`). No adapter:
  `shopman/shop/adapters/courier_machine.py:122-123` (`auth=(username, password)` e
  `headers={"api-key": ...}`). [OK]

| Chamada | Método e caminho | Parâmetros principais (doc) | Veredito |
|---|---|---|---|
| Estimar | `GET /estimarSolicitacao` | entregas: `endereco_`, `bairro_`, `cidade_`, `estado_` de `partida` e de `desejado` **obrigatórios**; `lat_`/`lng_` opcionais | [DIVERGENTE] mandava só lat/lng. Corrigido: o adapter manda os oito campos de endereço (`courier_machine.py:_estimate_params`) e `services/courier.estimate_for_order` passa o endereço da loja e do cliente |
| Abrir | `POST /abrirSolicitacao` | corpo `forma_pagamento`, `partida{endereco, bairro, cidade, estado, lat, lng}`, `paradas[{endereco_parada, ..., id_externo, nome_cliente_parada, telefone_cliente_parada}]`, `retorno`; resposta `id_mch` | [OK] |
| Status | `GET /solicitacaoStatus?id_mch=` | `id_mch` obrigatório; resposta `{status}` | [OK] |
| Detalhes | `GET {base}/v1/request/{id}` | `id` no caminho; resposta sem envelope (`request_id`, `driver`, `progress`, `finished`, `stops`) | [DIVERGENTE] na base: o padrão era `https://api.taximachine.com.br/integracao/v1` (sem `/api`). Corrigido para `https://api.taximachine.com.br/api/integracao/v1` em `config/settings.py:926`, no fallback do adapter (`courier_machine.py:79`), no `settings_test.py` e no `.env.example`; o caminho `/request/{id}` estava certo |
| Posição | `GET /posicaoCondutor?id_mch=` | `id_mch` obrigatório; resposta `lat_condutor`/`lng_condutor` (nulos fora de A/S/E) | [OK] |
| Cancelar | `POST /cancelar` | corpo `id_mch` e `motivo_id`, os dois obrigatórios; só antes de F/C/N | [OK] |
| Link de rastreio | `GET /obterLinkRastreio/{id}` | `id` no caminho; só na API de entregas | Caminho [OK]. [DIVERGENTE] na resposta: a doc v1 dá `{"link": ...}` e o adapter só aceitava a lista por parada. Corrigido: os dois formatos viram a mesma lista (`courier_machine.py:273`) |
| Cadastrar webhook | `POST /cadastrarWebhook` | corpo `tipo` (`status`, `posicao`, `mensagens`, `mensagens_corrida`), `url`, `responsabilidade` (`solicitante` ou `corrida`), os três obrigatórios; até 5 por tipo | [OK] |

O teste `test_each_call_hits_the_documented_v1_path`
(`shopman/shop/tests/test_courier_machine_adapter.py`) trava método, caminho e parâmetros de
cada linha; `test_settings_py_defaults_are_the_documented_addresses` trava o padrão do
`settings.py`.

**Formas de pagamento.** O OpenAPI de corridas lista 12 (`D B C T V X P H A F I R`); o de
entregas, 8 (`D` dinheiro, `B` débito, `C` crédito, `X` Pix, `P` PicPay, `H` WhatsApp,
`F` faturado, `R` carteira de créditos). O padrão `F` vale nos dois.

**Webhooks: o payload É documentado** (página "Webhooks > Sobre" da v1). O formato antigo
(`id_mch` + `status_solicitacao`; `id_mch` + `lat_cond`/`lng_cond`) está marcado como
deprecado e a doc pede recadastro para o novo:

- **status**: um POST por evento, com `datetime`, `event_id` (UUID, idempotência),
  `company_id`, `request_id`, `status_code`, `status_label`, `stop_id` (só em parada
  finalizada) e `links{request, driver?, enterprise?}`. `status_code` é a letra da corrida
  (`D G P S N A E C F U`) ou um evento que não é estado: `AP` chegou ao local, `ER` parada
  finalizada, `L` aguardando liberação, `R` aguardando pagamento.
- **posicao**: lote a cada 10 s com `event_id`, `datetime` e `data[]` (até 500 itens de
  `timestamp`, `company_id`, `request_id`, `driver_id`, `coordinates{latitude,
  longitude}`). Sem reenvio; posição com mais de 15 s é descartada pela própria Machine.
- **Assinatura**: header `Signature-V2`, HMAC-SHA-512 com a chave da API, calculado sobre o
  corpo inteiro.

`shopman/shop/webhooks/machine.py` entende os dois formatos: `status_code` de estado entra no
funil `apply_status`; `AP`/`ER`/`L`/`R` são aceitos e logados sem mexer na letra; o lote de
posição vai para o cache por `request_id`. Pendente: conferir a `Signature-V2` (hoje a borda
autentica pelo token da URL).

**Limites.** O gateway conta por `api-key`, em janela deslizante de 60 s, e responde `429`
com `Retry-After`. Os números que o dono trouxe (corridas 800/min, webhooks 60/min) são os da
tabela da **v2** (`/api/v2/integracao/corridas*` e `/webhooks*`, vezes a faixa da central).
Na v1, que é a que o adapter fala, a tabela publicada em 01/10/2026 é: `/api/integracao/*`
1000 × faixa por minuto; `solicitacao` e `solicitacaoStatus` 1900 × faixa;
`posicaoCondutor` 1000 × faixa; `/integracao/v1/*` (detalhes) 200 × faixa. E um limite
fixo por recurso: **3 consultas por minuto por solicitação** em `solicitacao` e
`solicitacaoStatus`. O polling padrão (`DEFAULT_POLL_SECONDS = 60`, 1 por minuto por
corrida) cabe; `courier_poll_seconds` abaixo de 20 estoura.

---

## 3. Teleporte — fallback manual (slice clipboard)

WP-11 slice 3 do [STOREFRONT-GAPS-ACTION-PLAN](STOREFRONT-GAPS-ACTION-PLAN.md). Decisão travada
(Pablo, 2026-06-17): **utilitário LOCAL Python**, roda na máquina do operador (desacoplado do
deploy), **clipboard como fallback**, DOM-fill quando houver URL/campos.

**Entregue 2026-06-29:**
- [`shopman/shop/services/dispatch_handoff.py`](../../shopman/shop/services/dispatch_handoff.py) —
  `build_dispatch_payload(order)` (payload estruturado a partir de `Order.data`; rejeita retirada),
  `format_dispatch_text(payload)` (bloco pt-BR paste-ready), `copy_to_clipboard(text)`
  (best-effort pbcopy/wl-copy/xclip/xsel/clip).
- [`manage.py teleporte ORDER-REF`](../../shopman/shop/management/commands/teleporte.py) —
  imprime + copia. `--json` emite o payload estruturado; `--no-copy` só imprime.
- 7 testes ([`test_dispatch_handoff.py`](../../shopman/shop/tests/test_dispatch_handoff.py)).

Lê de `Order.data`: `customer{name,phone}`, `delivery_address_structured{route, street_number,
complement, neighborhood, city, state_code, postal_code, formatted_address,
delivery_instructions, lat/lng}`, `delivery_distance_km`, `delivery_fee_q` (ver
[data-schemas](../reference/data-schemas.md)).

O auto-fill do form (DOM/deep-link) que estava bloqueado em URL/campos ficou **obsoleto** com a
integração Machine — o despacho agora é API. O teleporte permanece como fallback de contingência
(API fora do ar, corrida não atendida com entrega própria).

---

## 4. Decisões (histórico)

1. ~~TaOn tem API?~~ **Sim** — TaOn roda sobre a Machine (Gaudium); doc Postman chegou 2026-07-07
   → virou a integração de §2.
2. Preço ao cliente = faixas/zonas; cotação Machine = custo interno no gestor (Pablo, 2026-07-07).
3. Auto-avanço: coleta→"saiu p/ entrega" e finalização→"entregue" automáticos, sem gate de
   confirmação do cliente (benchmark iFood); "como foi a entrega?" = avaliação pós-entrega,
   feature separada (`customer_rating`).
4. Falha de despacho: alerta + re-despacho manual (sem retry automático de corrida).

## Referências
- [STOREFRONT-GAPS-ACTION-PLAN](STOREFRONT-GAPS-ACTION-PLAN.md) — WP-11 (entrega), slice 3 (teleporte)
- [GO-LIVE-CREDENTIALS-MATRIX](GO-LIVE-CREDENTIALS-MATRIX.md) — §5 logística externa
- [data-schemas](../reference/data-schemas.md) — chaves de entrega em `Order.data`
- [ADR-001](../decisions/adr-001-protocol-adapter.md) · [ADR-003](../decisions/adr-003-directives-sem-celery.md)
