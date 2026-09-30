# HANDOFF — aceleração de go-live

> Escrito em **2026-09-30, ~21:30 UTC**. Leia este arquivo ANTES de abrir qualquer frente de
> infraestrutura, deploy ou performance. Ele existe porque este projeto perdeu 21 horas num
> incidente que já estava documentado em outro lugar.
>
> **Estado anterior:** `docs/plans/GO-LIVE-ACCELERATION-PLAN-2026-09-29.md` (diagnóstico completo)
> e `docs/coordination/DECISIONS.md` (decisões D-001 a D-009 + B-001 resolvido).
> **Evidência:** `docs/reports/go-live-acceleration-20260929/` (15 relatórios).

---

## 1. O que foi resolvido hoje

| Item | Estado | Prova |
|---|---|---|
| **App congelado 21 h** | ✅ RESOLVIDO | O spec vivo tinha perdido o bloco `databases` (só `- name: postgres`). Devolvido. Deployment `3a3b0053` ACTIVE 18:21 UTC |
| **Storefront lento (queixa nº1)** | ✅ RESOLVIDO | `/` de **3,06–4,49 s → 0,49–0,92 s**. `/menu` 3,79 s → **0,40–0,49 s** |
| **Deploy: até 4 deployments por run** | ✅ RESOLVIDO | Run `36774871663`: **1** deployment, causa `manual`, `deploy_mode: single_deployment`, smoke passou |
| **Prova de origem do BFF (IP do cliente)** | ✅ LIGADA | Auditoria gravava IP de saída da DO (`206.189.202.53`); agora grava o IP real do cliente |
| **VAPID (notificação push)** | ✅ LIGADO | 5 chaves aplicadas; `check --deploy` sem E024/W024 |
| **Contexto doctl cego** | ✅ REMOVIDO | Era o **default**, mutilava `databases` na leitura SEM ERRO. 8 docs corrigidos |
| **Guard de drift do spec** | ✅ NO AR | `scripts/check_do_spec_drift.py` cobre `databases`, imagens e tamanho de componente |

## 2. Armadilhas — leia antes de tocar em qualquer coisa

1. ⛔ **NUNCA** `doctl apps update --spec` com um arquivo que não veio do spec VIVO. O update
   **substitui** o spec inteiro, não faz merge. Foi assim que o app congelou.
2. ⛔ **Sempre** `--context shopman-spec-update`. O default do doctl agora é vazio e **falha alto**
   de propósito — não "conserte" isso pondo um token no default.
3. **Antes de aplicar qualquer spec:** `make deploy-spec-drift context=shopman-spec-update`.
   Se houver linha em SUMIRIAM, **pare**.
4. **Depois de aplicar:** `spec get` de novo e compare os SECRET antes × depois. Hoje são 42.
5. `deploy_on_push` está `false` nos 8 componentes. **Quem criar o deployment é o
   `deploy-images.yml`**, um por run. Não religue sem motivo.
6. A **primeira requisição após um deploy é lenta** (3–5 s); depois estabiliza. Não é regressão.

## 3. Em voo (verifique antes de abrir frente)

- PRs `#1291` (`deploy_on_push` false no arquivo `.do/`) e `#1292` (docs do contexto doctl).
  Quando o #1291 mergear, `make deploy-spec-drift` fica **verde**.
- O **caminho de deploy por push** (merge → 1 deployment) usa o mesmo passo do teste manual, mas
  ainda não foi exercitado por um merge real.

## 4. Próxima frente: ONDA 1 — o backend do Storefront

O cache de borda resolveu o **anônimo**. O que **não** foi resolvido é o custo do backend:

```
/api/v1/storefront/menu/   → ~3,3 s
  server-timing: projection;dur=2719 · availability;dur=1680 · db;dur=614 · shadow;dur=0.00
```

**93 consultas por request** para 44 cards. A disponibilidade é calculada **4× por request** e custa
`O(linhas de stockman_quant)`, não O(SKUs). **Análise completa e medida:**
`docs/reports/go-live-acceleration-20260929/13-hot-path-projecao.md` — não refaça.

Ordem sugerida (P1 e P6 já foram feitos):

| # | Ação | Ganho | Risco |
|---|---|---|---|
| **P3** | `home/` para de construir o catálogo para guardar 3 cards (`home.py:379`) | **−2,0 a −2,5 s** | médio-baixo |
| **P8** | Memo de `ChannelConfig.for_channel`/`is_channel_active` por request | −5 consultas · limpa 100.974 seq scans/dia | baixo |
| **P4** | `published_products_by_collection`: 1 consulta + agrupamento Python | −27 consultas | baixo |
| **P7/P9** | `tracked_skus` com `_quantity__gt=0` · higiene do laço por item | −100 a −250 ms | baixo |
| **P2** | Disponibilidade 1× por request (waitlist re-chama o batch por data; bundle faz 3ª passada) | **−0,9 a −1,3 s** | **ALTO — é Core** |
| P5 | Cortar duplicação do payload (120 cópias de card; 85 KB de 135 KB são `sections`) | −100 a −200 ms | médio (BE+FE atômico) |

**Comece por P3 + P8 + P4** — são os maiores com menor risco, e não tocam `packages/`.
**P2 toca o Core** e exige revisão e `make test-stockman`.

## 5. Outras frentes abertas (não começadas)

- **Onda 2 (CI):** `test-shop` ainda é o caminho crítico (12,5 min por shard); `make install` roda
  13× por evento; falta escopo por diff nos gates caros.
- **Onda 4 (go-live):** cortes de escopo — inclusive derrubar a regra auto-bloqueante
  `PRODUCT-V1-SCOPE-BACKLOG.md:77` ("todas as 11 frentes").
- **WP-5** (trava por dispositivo no PDV) — só quando o atendimento/concierge estiver desenhado.
- `docs/guides/deploy-digitalocean.md:55` ainda diz que "publicar a tag nova já é o deploy" —
  deixou de ser verdade. Está no PR #1292.
