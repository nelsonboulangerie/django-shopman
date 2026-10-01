# HANDOFF — aceleração de go-live

> 🚪 **Este é o documento de ENTRADA ÚNICA** da aceleração de go-live. Sessão nova (Claude, Codex,
> DSH, quem for) começa aqui e só depois abre os outros, na ordem da seção 0.2. O
> `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md` aponta para cá.
>
> **Atualizado em 2026-10-01, ~09:35 UTC** (estado depois da Frente 0 do turno de 01/10).
> As seções 1 a 5 são o registro de 30/09 e ficam como histórico: valem as armadilhas, não a fila.

---

## 0. Estado agora (01/10, depois da Frente 0)

### 0.1 Onde as coisas estão

| O quê | Estado | Onde |
|---|---|---|
| Turno autônomo 30/09 → 01/10 | encerrado; 28 PRs mergeados | NIGHT-REPORT (abaixo) |
| NIGHT-REPORT + PENDING-DECISIONS (D1–D16) | **na fila de merge** (PR #1299; até entrar, leia no branch `claude/turno-autonomo-coordenacao-76dc5f`) | `docs/reports/go-live-acceleration-20260930-diag/` |
| Diagnósticos D4, D5, D14, D16 (turno DSH de 01/10) | **na fila** (PR #1325); estavam só na worktree do DSH, o D16 nem commitado | `docs/reports/go-live-acceleration-20261001/` |
| #1324 (margem da vitrine comia a unidade da sacola) | ✅ mergeado 01/10 09:00 UTC | `main` |
| **D14 token da Efí no access log** | ✅ **FECHADO** 01/10 09:21 UTC (detalhe em 0.3) | spec vivo |
| D13 republicar fichas com insumo repetido | ✅ **nada a fazer**: no alpha, 72 receitas com versão atual e 74 versões no total, **zero** com o mesmo SKU em duas linhas (consulta só-leitura, conexão direta 25060) | — |
| D15 picos Cloudflare ↔ DO | medido 01/10 09:23–09:27 UTC: **não reproduz** (400 requisições, 0 erro, 0 acima de 5 s; tamanho, encoding, IPv4/6 e H1/H2 descartados; H3 e outra rede não medidos). Deployments explicam no máximo 2 de 4 picos; o 520 das 04:44:41 caiu fora de troca. Chamado na DO só para pedir log da madrugada | NIGHT-REPORT |

### 0.2 Ordem de leitura

1. **Este arquivo** (estado, em voo, armadilhas).
2. `docs/reports/go-live-acceleration-20260930-diag/NIGHT-REPORT.md` (o que entrou no turno, medições de produção).
3. `docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md` (D1–D16: o que é do dono).
4. `docs/reports/go-live-acceleration-20261001/` (D14, D4, D5, D16: diagnósticos com caminho:linha).
5. Só para regras de convivência e deploy: `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md` §1 a §5.

### 0.3 D14, como foi fechado (não refaça)

- `make deploy-spec-drift context=shopman-do-app-admin` acusava **uma** divergência: o `run_command`
  do `web` sem `--access-log=/dev/null` (a flag está em `.do/app.alpha-subdomains.yaml` desde 05/09).
- Backup do spec vivo, edição textual de **uma linha**, `apps update`. SECRET antes × depois:
  **42 = 42, idênticos** (chave e hash do valor cifrado). `spec get` depois: diff de uma linha só.
- Deployment `50988cd5` ACTIVE 09:24 UTC. Drift agora: **[OK]**. `/health/live/` e `/health/ready/` 200.
- Prova: POST no webhook da Efí com token **falso** (sonda) → 401, e a sonda **não** aparece no log;
  a única linha é a do `django.request`, que já grava `token=[redacted]`.
- Busca no log antes do update: só o deployment ativo tem log recuperável pelo `doctl` (347 linhas,
  09:05–09:19 UTC): **0** `token=`, **0** `efi/pix`. Os 59 deployments anteriores não devolvem log.
- ⚠️ **O token NÃO foi rotacionado.** É de sandbox (`EFI_SANDBOX=true`, Pix no simulador), mas é a
  mesma variável `EFI_WEBHOOK_TOKEN` que irá para produção, onde é a autenticação **única** do
  webhook (sem mTLS, allowlist de IP vazia). **Rotacionar é OBRIGATÓRIO antes de ligar a Efí de
  produção** (item de checklist do corte do Pix). Ver `d14-token-efi.md` §7.

### 0.4 Em voo (turno de 01/10, uma frente = um branch = um PR, no máximo dois PRs de código ao mesmo tempo)

| Frente | Branch / PR | Estado |
|---|---|---|
| 2: lei da data por superfície (loja: 1 pedido = 1 data; balcão: 1 linha = 1 data) + 409 de ajuste mostra o teto da linha | `night/f2-lei-da-data-por-superficie` | em execução |
| 3: "Etapa/Etapas" nas telas + guardrails + processo das 11 massas (92 etapas) resgatado | #1326 | na fila |
| 4: motivos de recusa (lista de 11 + "Outros", agrupada) | `night/f4-motivos-de-recusa` | em execução |
| 5: botão que nasce inerte (D1) + estado pendente | — | aguarda vaga |
| 6: D12 pool de Redis e GC | — | aguarda vaga |
| 7: D6 referências externas + D7 critérios de nota editáveis | — | aguarda vaga |

⚠️ **O processo das 92 etapas NÃO é dado da casa.** O próprio artifact de origem (claude.ai
`b8cd4fc0-…`, 05/09) o chama de "proposta minha, é a parte que eu menos sei". Ele está no repo para
não se perder, não para ir ao seed.

⚠️ **D12, degrau 1 (`CONN_MAX_AGE=0`) pede escrita no spec vivo** (`DATABASE_CONN_MAX_AGE="60"` está
no spec, e o deploy não escreve spec). Fora da autorização deste turno: é do dono.

---

## Histórico de 30/09 (seções 1 a 5)

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
2. ⛔ **Sempre** `--context shopman-do-app-admin` (o antigo `shopman-spec-update` foi renomeado). O default do doctl agora é vazio e **falha alto**
   de propósito — não "conserte" isso pondo um token no default.
3. **Antes de aplicar qualquer spec:** `make deploy-spec-drift context=shopman-do-app-admin`.
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

### ATUALIZAÇÃO 2026-09-30 ~22:00 UTC — parte segura ENTREGUE (PR #1295, na fila)

P3 + P8 + P4 feitos, **nada em `packages/`**. Medição **local** (a de produção sai depois do deploy):

| | antes | depois |
|---|---|---|
| `menu/` consultas | 93 | **65** |
| `home/` consultas | 97 | **57** |
| `shell/` consultas | 4 | 2 |
| consultas a `shop_channel` | menu 9 / home 11 | **2 / 2** |

**Contrato do `home/` provado intacto:** 0 diferenças em **14.513 campos** contra 5 payloads do main.
E existe um teste que **falha se a home voltar a chamar `build_catalog`** — **não desfaça esse teste**.
De carona: a promoção ignorava o prefetch dos canais e fazia 1 consulta por promoção.

**MEDIDO EM PRODUÇÃO** (30/09, medianas de 5 amostras; deploy `405e3f25` ACTIVE às 23:17 UTC,
causa `manual` — **o caminho por push funciona**):

| | antes | depois |
|---|---|---|
| `home/` TTFB | 3,13 s | **~1,29 s** ✅ |
| `menu/` TTFB | 2,63 s | 2,51 s |
| `menu/` projection | 2.292 ms | 2.155 ms |
| `menu/` availability | 1.395 ms | 1.294 ms |
| `menu/` db | 396 ms | 292 ms |
| `menu/` query_count | 83 | **55** |

O `response_bytes` ficou **idêntico** (136.681 B antes e depois) — prova em produção de que o JSON
não mudou. E a produção tinha **83** consultas, não as 93 da bancada.

**O `menu/` quase não caiu (−6% de tempo, com −34% de consultas)** porque o que resta é a
**disponibilidade: ~1,3 s, 60% da projeção**. Isso é o **P2, no Core** — é o próximo grande ganho.

---

## ⛔ P7 — NÃO FAÇA (provado perigoso em 30/09)

A recomendação de aplicar `_quantity__gt=0` em `tracked_skus`
(`packages/stockman/.../services/availability.py:432`) **estava ERRADA** — veio do relatório 13 e foi
refutada por quem tentou executá-la.

Com o filtro, **um SKU esgotado deixa de ser "rastreado"** (o quant zerado nunca é apagado), e o gate
aprova SKU não rastreado com disponível `999999` — **venderia sem limite justamente o que acabou de
esgotar**. O executor provou na bancada e deixou a trava
`shopman/shop/tests/test_sold_out_sku_stays_tracked.py`, que reprova com o filtro aplicado.
**Não remova essa trava e não reaplique o filtro.** Resolver isso exige a frente do Core.

## ❌ P9 — NÃO VALE A PENA (medido)

O laço por item custa **~1,5 ms por request**, não os 100–250 ms que o relatório 13 estimou.
Medido com profiler. O custo real está na disponibilidade.

🔎 **Descoberta fora do escopo, para a próxima frente:** **com sacola**, `home/` e `menu/` fazem
**~200 consultas**, e o custo está na **projeção da sacola**, não no catálogo. Isso **não** está no
relatório 13.

Ordem sugerida (P1, P6, P3, P8 e P4 já foram feitos):

| # | Ação | Ganho | Risco |
|---|---|---|---|
| **P7/P9** | `tracked_skus` com `_quantity__gt=0` · higiene do laço por item | −100 a −250 ms | baixo |
| **P2** | Disponibilidade 1× por request (waitlist re-chama o batch por data; bundle faz 3ª passada) | **−0,9 a −1,3 s** — `availability` mede ~1,4 s em produção | **ALTO — é Core** |
| **NOVO** | Projeção da sacola (~200 consultas com sacola) | não medido | a medir |
| P5 | Cortar duplicação do payload (120 cópias de card; 85 KB de 135 KB são `sections`) | −100 a −200 ms | médio (BE+FE atômico) |

**Antes de atacar: MEÇA a produção depois que o #1295 entrar.** O ganho de P3+P8+P4 pode já ter
comido parte de P2 — e não se otimiza o que não se mediu.
**P2 toca o Core** e exige revisão própria e `make test-stockman`.

## 5. Outras frentes abertas (não começadas)

- **Onda 2 (CI):** `test-shop` ainda é o caminho crítico (12,5 min por shard); `make install` roda
  13× por evento; falta escopo por diff nos gates caros.
- **Onda 4 (go-live):** cortes de escopo — inclusive derrubar a regra auto-bloqueante
  `PRODUCT-V1-SCOPE-BACKLOG.md:77` ("todas as 11 frentes").
- **WP-5** (trava por dispositivo no PDV) — só quando o atendimento/concierge estiver desenhado.
- `docs/guides/deploy-digitalocean.md:55` ainda diz que "publicar a tag nova já é o deploy" —
  deixou de ser verdade. Está no PR #1292.
