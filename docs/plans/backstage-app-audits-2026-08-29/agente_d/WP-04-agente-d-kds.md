# WP-04-agente-d — KDS

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-04 do Agente G)
**Superfície:** 'surfaces/kds-nuxt' + endpoints KDS/cozinha/expedição
**Objetivo:** tornar a cozinha impossível de confundir: ticket certo, estação certa, item certo, undo rápido, tempo real honesto e **payload mínimo sem chaves sensíveis**.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** item status usa índice mutável ('index' da UI → 'ticket.items[index]' no core; 'unfire_session_lines' remove itens do meio de tickets vivos, deslocando índices); 'bool("false")' marca checked (bug real); estação não vinculada ao board/action/SSE; 'operate_kds' usado para config no Admin; envelopes de mutação inconsistentes.

**Recalibrados / agravados:**
- **bool("false")** — promovido a **P0**: fix de 1 linha ('checked = bool(request.data.get("checked", False))' → parser estrito), impacto direto em marcar o item errado na cozinha.
- **SSE autoriza por tipo de canal** — o WP tratou como falha de autorização; é decisão ADR-016 documentada (canal = push de um fetch canônico; o fetch faz o gate fino — 'eventstream.py:100-101'). **O achado real é o payload**: o canal 'kds' vaza 'session_key' + 'order_ref' ('_sse_emitters.py:390-399'), e 'backstage-kds-main' é global — qualquer 'operate_kds' recebe a chave ticket↔comanda↔Order de qualquer estação. Achado novo, mais grave que o P1 original.
- **Estação vinculada** — manter, com correção de fronteira: **não** vincular 'KDSInstance' a 'Terminal' (acopla o domínio caixa/cashman); usar 'station_ref'/allowlist dentro do backstage. E o aceite "Estação A não lê board B" precisa de **exceção explícita para 'type="expedition"'** (board de expedição é global por design — 'projections/kds.py:343-345').
- **version no POST de item** — o WP subespecificava a fonte: 'KDSTicket' **não tem** 'version' nem 'updated_at' ('models/kds.py:46-95'). Decidir: campo novo 'rev' OU hash do estado; ancorar no core.
- **UX "estação lacrada"** — inalcançável hoje: não existe vínculo operador→estação em lugar nenhum. É dependência declarada do P1 de estação (só depois dele existe "estação correta" para mostrar).

**Novos (achados da verificação):**
- **SSE kds vaza 'session_key' + 'order_ref'** (acima) — P0.
- **Ref de estação inexistente → HTTP 500** (não 404): 'api/kds.py:67-69' + 'projections/kds.py:183' ('.get()' puro); o 'EXCEPTION_HANDLER' não converte 'DoesNotExist'.
- **'KDSItemProjection' descarta 'line_id'** que existe em 'ticket.items' ('projections/kds.py:449-459') — o fix vive na projection (o contrato TS é gerado dela), não no .ts.
- help_text de 'models/kds.py:75' desatualizado (sem 'line_id').

## Fronteira Natural

KDS executa trabalho já autorizado: preparar, separar, marcar item, finalizar ticket, recall, acknowledge e handoff de expedição. POS/Gestor decidem venda, pagamento, confirmação/cancelamento e fire/unfire. Produção decide WO. Pickup público mostra só código/status sem PII. **A estação de cozinha não é o terminal de caixa** — vínculo via 'station_ref' dentro do backstage.

## Evidências (verificadas)

- 'KDSItemProjection' sem 'line_id': 'shopman/backstage/projections/kds.py:42-51' (builder descarta o campo: ':449-459'); 'ticket.items[*]' tem 'line_id': 'shopman/shop/services/kds.py:238'.
- UI envia 'index': 'surfaces/kds-nuxt/app/composables/useKdsBoard.ts:164,171'.
- 'checked = bool(request.data.get("checked", False))': 'shopman/backstage/api/kds.py:88'.
- Core muta 'ticket.items[index]': 'shopman/shop/services/kds.py:452,467'; 'unfire_session_lines' remove do meio: 'shopman/shop/adapters/kds.py:78-83'.
- Board usa 'ref' da URL: 'surfaces/kds-nuxt/app/pages/[ref].vue:14-15'.
- SSE gate por kind, payload vaza 'session_key'/'order_ref': 'shopman/shop/eventstream.py:57,128-148', 'shopman/shop/handlers/_sse_emitters.py:390-399,474'.
- 'KDSInstanceAdmin' usa 'backstage.operate_kds' para os 4 has_*: 'shopman/backstage/admin/kds.py:53-63'.
- 'KDSTicket' sem 'version'/'updated_at': 'shopman/backstage/models/kds.py:46-95'.

## Achados Priorizados

### P0 — 'checked = bool("false")' marca verdadeiro

Proposta:
- Parser estrito de boolean JSON: 'string', 'null', número e ausência → 400 de campo.
- Mesmo parser para 'index' (já valida int, mas exige presença).

Aceite:
- 'false' como string retorna 400 e não altera ticket (teste API).
- Boolean JSON real continua funcionando.

### P0 — SSE do canal kds vaza session_key + order_ref

Proposta:
- Payload mínimo do canal 'kds': 'ticket_ref' + 'status' + 'version' (nunca 'session_key'/'order_ref').
- 'backstage-kds-main' deixa de existir ou carrega só o sinal mínimo (ref+status), sem chaves internas.
- A estação continua resolvendo o fetch canônico (que já é gateado) — ADR-016 preservado.

Aceite:
- Nenhum evento do canal 'kds' contém 'session_key'/'order_ref' (teste assert-negativo no payload).
- Pickup público: assert negativo para nome, telefone, endereço, total, 'session_key' (mantido do WP original).

### P1 — Item status usa índice mutável

Proposta:
- Expor 'item_ref'/'line_id' em 'KDSItemProjection' (o dado já existe no ticket; só falta projetar).
- POST usa '{ item_ref, checked, version }'; retornar 409 se versão/ticket mudou.
- Ancorar 'version': campo novo 'rev' em 'KDSTicket' (decidir com o dono do backstage; alternativa: hash do estado).

Aceite:
- Reordenar/remover itens não muda qual item é marcado (teste: remove item do meio, marca pelo 'line_id').
- Teste backend cobre item inexistente (404/409), versão stale (409) e payload antigo.

### P1 — Estação não está fortemente vinculada ao board/action/SSE

Proposta:
- Vincular 'KDSInstance' a 'station_ref' (allowlist de estações no backstage — **não** 'Terminal' do cashman).
- Board, actions e SSE validam a estação; ref inexistente → 404 (corrigir o 500 de 'api/kds.py:67-69').
- Override de supervisor exige permissão separada e motivo.
- **Exceção explícita:** 'type="expedition"' permanece global (board compartilhado de expedição).

Aceite:
- Estação A não lê board B, não opera ticket B e não assina SSE B (com exceção documentada para expedition).
- Ref inválida retorna 404, não 500.

### P1 — Operador KDS pode administrar configuração KDS

Proposta:
- Separar 'backstage.operate_kds' de 'backstage.manage_kds_config' (add/change/delete/view do 'KDSInstanceAdmin').
- 'setup_groups': 'manage_kds_config' vai para Gerente (não Cozinha).

Aceite:
- Operador de cozinha não altera KDSInstance no Admin (teste de permissão).
- Gerente configura roteamento/SLA/som.

### P2 — Envelopes de mutação inconsistentes

Proposta:
- Todas as mutações retornam envelope comum: estado resultante, 'updated_at', 'version', 'blocked_reason'.
- UI pode otimizar, mas reconcilia por contrato.

Aceite:
- Check item, done, recall, ack e expedition retornam o mesmo envelope (teste de contrato).

## Melhorias UX

1. **Estação lacrada** (depende do P1 de estação): URL errada vira bloqueio com cor/código da estação correta.
2. **Identidade gigante da estação:** nome/cor/código fixos, legíveis a distância.
3. **Done seguro:** finalizar sem todos os itens exige long press ou confirmação clara.
4. **Undo imediato:** barra de 5s para check/done/ack quando reversível.
5. **Expedição por checklist:** volumes, itens, etiqueta, courier, troco/equipamento antes de liberar — **troco/equipamento exigem contrato com cashman/payman (fronteira declarada; se o dado não existe na projeção, o checklist mostra só o que existe)**.
6. **Estado live/polling/stale:** operador vê última atualização.
7. **Sons semânticos:** novo ticket, atraso, cancelamento, recall, com cooldown.
8. **Código ambíguo:** se sufixos visualmente iguais, promover prefixo/origem/cor.

## RBAC / setup_groups

Permissão nova: 'backstage.manage_kds_config'. Atualizar 'setup_groups.py': conceder a Gerente (e não a Cozinha). Teste de paridade obrigatório.

## Pré-requisitos

- Bloco "Contrato de actions" do WP-02-agente-d (envelope/payload mínimo reutiliza o formato do manifest).
- P1 de estação é pré-requisito da UX "estação lacrada" (declarado).

## Testes

- Backend: estação A não toca B; expedition global preservado.
- API: boolean estrito ('"false"' → 400).
- Contract: 'KDSItemProjection' tem identity estável ('line_id'); envelope comum.
- SSE: payload mínimo sem 'session_key'/'order_ref' (assert-negativo).
- E2E duas estações; ref inválida → 404.
- Visual regression: TV/tablet/mobile, nomes longos, notas longas, muitos itens, offline/stale.
- Pickup público: assert negativo para PII.

## Fora De Escopo

Pagamento, desconto, preço, caixa, troco contábil, cancelamento comercial, edição de comanda POS, configuração runtime de KDS, planejamento produtivo e BI. Vinculação de KDSInstance a Terminal (cashman) — não fazer.

## Prompt Para Agente Executor

~~~text
Execute WP-04-agente-d (KDS).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-04-agente-d-kds.md
- surfaces/kds-nuxt/app/composables/useKdsBoard.ts
- surfaces/kds-nuxt/app/pages/[ref].vue
- shopman/backstage/api/kds.py
- shopman/backstage/projections/kds.py
- shopman/backstage/services/kds.py
- shopman/shop/services/kds.py
- shopman/shop/adapters/kds.py (unfire_session_lines)
- shopman/shop/eventstream.py + shopman/shop/handlers/_sse_emitters.py
- shopman/backstage/admin/kds.py
- shopman/backstage/models/kds.py
- shopman/shop/management/commands/setup_groups.py

Fases:
1. P0: parser boolean estrito + payload minimo do SSE (sem session_key/order_ref).
2. P1: item_ref/line_id na projection + version (campo novo ou hash) + 409 stale.
3. P1: estacao por station_ref (board/action/SSE), excecao expedition, ref invalida → 404.
4. P1: manage_kds_config separada + setup_groups.
5. P2: envelope comum nas mutacoes.
6. UX de estacao lacrada (so apos o P1 de estacao), undo e live/stale.

Nao mexa em pagamento, POS ou Producao alem dos contratos de fronteira.
~~~