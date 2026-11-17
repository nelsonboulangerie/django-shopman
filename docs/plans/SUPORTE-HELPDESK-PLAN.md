# SUPORTE-HELPDESK-PLAN — o helpdesk interno e o gate de dev

> **Status:** spec ativa. Contrato: [ADR-046](../decisions/adr-046-suporte-helpdesk-interno.md).
> Primeiro vertical da ID3A. Interno primeiro; o tronco externo é fase posterior.
> O código entra em slices, cada um em seu PR. Nada aqui autoriza merge sem os gates da casa.

> **Vocabulário:** `Pedido` é o Order do cliente. `Chamado` é o `HELP-AAAA`. `Solicitação` é o chamado que pede mudança. `Compromisso` é o `DEV-AAAA`.

## 1. Objetivo

Dar ao operador, ao gerente e ao dono um lugar único para dúvida, queixa, defeito, solicitação e
ideia, com contexto automático, thread, estado e prova. O que precisar de código vira
`DEV-` no ledger e só muda com aprovação do dono. O que for dúvida morre resolvido ali.

**Não é:** board público, chat com presença/digitando, WhatsApp como banco, kernel novo,
surface nova, substituto do ledger de dev.

## 2. Fases

| Fase | Entrega | Critério de saída |
|---|---|---|
| 0 | ADR-046 + esta spec | aprovadas e na fila |
| 1 | Backend: models, migração, permissões, API, testes | criar/ler/responder/triar via API, com permissão |
| 2 | Hub: `/support` lista + detalhe + thread + composer | operador cria e acompanha no celular |
| 3 | Gate de dev: aprovação → `DEV-` → PR cita `Compromisso:` | uma solicitação real fecha o ciclo |
| 4 | IA de triagem (ID3A): sugestão de tipo/fila/prioridade | erro com confiança medida; fallback humano |
| 5 | Canais (Telegram/WhatsApp) e tronco externo | só depois do interno estável |

A fase 1 pode entrar antes do go-live; as fases 4 e 5, depois. A fase 1 não depende de IA.

## 3. Modelo de dados

`shopman/backstage/models/support.py`:

- **SupportTicket**
  - `ref` (`HELP-0001`, único), `shop` (FK/Schema, ADR-042), `requester` (FK user),
    `requester_role`, `audience` (`internal`/`external`, default `internal`),
    `type` (`question`, `complaint`, `bug`, `request` (Solicitação), `idea`, `decision`),
    `status`, `priority`, `subject`, `description`,
    `context` JSON (envelope operacional, sem PII),
    `assignee` (FK user, opcional), `sla_due`, `review_at`,
    `approved_by`, `approved_at`, `approval_basis`,
    `ledger_ref` (`DEV-…`, opcional), `resolution`,
    `created_at`, `updated_at`, `closed_at`.
- **SupportMessage**
  - `ticket`, `author`, `body`, `internal_note` (bool), `channel`
    (`hub`/`telegram`/`whatsapp`/`email`), `ai_meta` JSON, `created_at`.
- **SupportDecision**
  - `ticket`, `decided_by`, `decision` (`approve`/`reject`/`defer`),
    `reason`, `created_at`. A decisão é append-only.
- **SupportAttachment** (fase 5): `ticket`, `message`, `file`, `content_type`,
  `size`, `scan_status`. Sem anexo na v1.
- **AiInvocation** (fase 4, ID3A): `task`, `backend`, `model`, `tokens_in`,
  `tokens_out`, `cost_q`, `latency_ms`, `confidence`, `fallback`, `outcome`,
  `request_id`, `ticket`, `created_at`.

Índices: `(shop, status, updated_at)`, `(assignee, status)`, `(requester, created_at)`,
`ref` único. `ref` gerado como `WorkOrder.code` (sequência por loja/ano, sob trava).

## 4. Estados e transições

```
NEW → TRIAGE → WAITING_REQUESTER ↔ TRIAGE
                → WAITING_OWNER → APPROVED → IN_DEV → RESOLVED → CLOSED
                → REJECTED
                → DEFERRED (review_at) → TRIAGE
```

- `NEW`: capturado, sem triagem. Dono: fila do Suporte.
- `TRIAGE`: gerente/IA classificando. Dono: gerente.
- `WAITING_REQUESTER`: pergunta única pendente. Dono: requester.
- `WAITING_OWNER`: solicitação de produto aguardando decisão. Dono: Pablo.
- `APPROVED`: aprovado; gera/liga `DEV-`. Dono: engenharia.
- `REJECTED`: recusado com motivo. Terminal.
- `IN_DEV`: `DEV-` com PR. Dono: engenharia.
- `RESOLVED`: entregue ou respondido; aguarda confirmação. Dono: requester.
- `CLOSED`: confirmado ou fechado por prazo. Terminal.
- `DEFERRED`: adiado com `review_at`; volta para `TRIAGE` na data. Nunca é silêncio.

## 5. Permissões

| Permissão | Operador | Gerente | Dono | Agente |
|---|---|---|---|---|
| `shop.create_support_ticket` | sim | sim | sim | não |
| `shop.triage_support_tickets` | não | sim | sim | não |
| `shop.view_all_support_tickets` | não | sim (loja) | sim | não |
| `shop.approve_support_requests` | não | não | **sim** | não |
| `shop.link_support_dev` | não | não | sim | sim (service account) |
| `shop.view_support_audit` | não | sim | sim | não |

- Operador vê os próprios tickets; gerente vê os da loja/setor; dono vê tudo.
- O agente (Claude/Codex/DSH) usa uma service account de escopo mínimo: lê o aprovado,
  comenta o link do PR, atualiza `IN_DEV`/`RESOLVED`; **nunca** aprova.
- Permissões entram no `setup_groups`/seed, não em código espalhado.

## 6. API (DRF, `/api/v1/backstage/support/`)

- `GET /tickets/` — filtros `mine`, `status`, `type`, `assignee`, `q`; paginação.
- `POST /tickets/` — `{subject?, description, type?, context, audience?}`; devolve `HELP-…`.
  Idempotente por `client_uuid` (offline).
- `GET /tickets/<ref>/` — ticket + mensagens + decisões + links.
- `POST /tickets/<ref>/messages/` — `{body, internal_note?}`; SSE `support`.
- `POST /tickets/<ref>/triage/` — `{type, priority, assignee?}` (gerente).
- `POST /tickets/<ref>/decision/` — `{decision, reason}` (dono).
- `POST /tickets/<ref>/link-dev/` — `{dev_ref}` (dono/agente).
- `GET /tickets/<ref>/events/` — SSE do ticket (ou canal `support` global).
- Erros no dialeto `{detail, field, errors}`; copy sem travessão.

Projeções: lista e detalhe são projections puras em `shopman/backstage/projections/support.py`
(sem regra de negócio na view). A view só valida transporte, permissão e idempotência.

## 7. UI no hub

`surfaces/hub-nuxt/app/pages/support.vue` (rota `/support`, inglês; texto em português):

- **Lista**: “Meus chamados” (operador) / “Todos” (gerente/dono), filtros por estado e tipo.
- **Detalhe**: cabeçalho de contexto, thread, composer, status, ações por papel.
- **Composer**: um campo. O contexto vai num bloco recolhível; o operador só escreve a
  exceção. Sem dois botões “Solicitação/Ideia”; a sugestão da IA aparece como chip editável.
- **Aprovação**: o dono vê “Aprovar”, “Recusar”, “Adiar” com motivo; a tela mostra o
  `DEV-` gerado e o PR quando existir.
- **Mobile**: PWA do hub; `MoreBelow`, `useNextFocus`, alvos ≥ 48 px; SSE para updates.
- **Erros**: o dialeto canônico; nada de tela em branco.

## 8. Contexto automático

Payload (JSON, sem PII):

```json
{
  "actor_ref": "user:42",
  "role": "operator",
  "shop_ref": "nelson",
  "sector_ref": "balcao",
  "workstation_ref": "pdv-02",
  "business_date": "2026-11-12",
  "route": "/pos",
  "focus": {"kind": "order", "ref": "ORD-1234"},
  "device_ref": "device:abc",
  "app_version": "1.42.0",
  "connectivity": "online",
  "last_error_id": "8f3a",
  "request_id": "..."
}
```

- O hub preenche o que sabe; o operador não digita nada disso.
- `context` é validado e limitado (tamanho, chaves conhecidas); o que não se encaixa vai
  em `extra` com limite.
- Offline: o ticket é enfileirado no cliente (IndexedDB/`useConnectivity`) com
  `client_uuid`; ao voltar, sincroniza. O ticket não se perde quando o sistema cai.

## 9. Gate de dev

1. Solicitação de produto aprovada pelo dono (`APPROVED`).
2. Aprovação cria/liga a linha `DEV-AAAA` no `docs/coordination/COMMITMENTS.md`
   (`tipo=solicitacao`, `origem=HELP-…`, `dono=Engenharia`, `revisar_em`).
3. O PR cita `Compromisso: DEV-AAAA`; o CI reprova sem a linha.
4. O merge atualiza o `DEV-` para `FEITO` com `prova: #PR` e fecha/atualiza o ticket.
5. O requester recebe o changelog (“sua solicitação foi atendida no PR #…”).

Solicitação explícita do dono nasce `APPROVED` com `approved_by=Pablo`,
`approval_basis="solicitado pelo dono"`. Ideia nasce `TRIAGE`. Ambíguo: uma pergunta.

## 10. IA (ID3A) — opcional na v1

- A v1 funciona com triagem humana. A IA entra na fase 4, como sugestão:
  tipo/fila/prioridade, duplicado, FAQ, resumo.
- JEV decide entre opções tipadas com probabilidade; se a confiança for baixa, pergunta.
- LLM só para resumo/resposta sugerida, com citação e rótulo “sugestão”.
- Embeddings locais para duplicados/FAQ; nada de PII para fora.
- Orçamento, timeout, cache, fallback e auditoria (`AiInvocation`); sem loop pago.
- A IA nunca aprova, nunca escreve em dinheiro/estoque/fiscal/pedido.

## 11. Testes

- Modelo: `ref` único, transições válidas, `DEFERRED` exige data, `REJECTED` exige motivo.
- API: permissões por papel, isolamento por loja, idempotência, erros canônicos.
- Gate: aprovação cria `DEV-`; PR sem `Compromisso:` reprova; `DEV-` fechado com prova.
- UI: vitest de composables/projection; Playwright do fluxo operador→gerente→dono.
- Offline: ticket criado sem rede sincroniza uma vez só.
- Carga: lista com 1k tickets; SSE com 100 clientes.

## 12. Métricas

- tempo até triagem; tempo até primeira resposta; tempo até decisão do dono;
- tickets sem dono; tickets vencidos; `DEFERRED` vencidos;
- solicitações aprovadas sem `DEV-`; `DEV-` sem PR; PR sem prova;
- custo por ticket (IA), aceitação da sugestão, erro com confiança;
- taxa de captura offline; duplicados.

## 13. Riscos

- **Escopo**: virar Canny clone. Corte: sem board público, sem votação, sem anexo na v1.
- **Dono gargalo**: só produto vai para ele; suporte o gerente resolve.
- **PII**: contexto com refs; retenção e acesso definidos; sem CPF/telefone.
- **Offline**: sem fila local, o helpdesk falha no incidente que importa.
- **Permissão**: operador não vê ticket de outro; agente não aprova.
- **Custo**: IA fora do caminho de captura; orçamento e kill switch.
- **Duplicados**: linkar, não apagar.

## 14. Primeiros PRs

1. **Este**: ADR-046 + spec + índices.
2. **Backend**: models, migração, permissões, API, testes (fase 1).
3. **Hub**: `/support` lista/detalhe/thread/composer (fase 2).
4. **Gate**: aprovação → `DEV-` → PR (fase 3).
5. **IA**: triagem/ID3A (fase 4), depois canais e externo (fase 5).

Cada PR é uma frente, um branch, um PR. Nenhum começa sem o anterior na fila ou mergeado.
