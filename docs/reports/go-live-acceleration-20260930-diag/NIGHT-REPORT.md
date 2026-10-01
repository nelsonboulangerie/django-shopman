# NIGHT-REPORT — turno autônomo 30/09 → 01/10/2026

> Coordenador: Claude (sessão `turno-autonomo-coordenacao`). Briefing:
> `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md` (PR #1297).
> Decisões que são suas: [`PENDING-DECISIONS.md`](PENDING-DECISIONS.md).

## Em uma tela

| Frente | PR | Estado | Uma linha |
|---|---|---|---|
| Briefing + HANDOFF | #1297 | ✅ mergeado | Só docs |
| Briefing 6.2 + 5 diagnósticos | #1302 | ✅ mergeado | Só docs |
| **F1** drift do spec (`deploy_on_push`) | #1291 | ✅ mergeado | Teste exige DESLIGADO, como o vivo |
| **F2** `brace-expansion` no audit | #1298 | ✅ mergeado | "Marketing — cadeia completa" deixa de reprovar todo PR |
| **F5** PWA travado | #1301 | ✅ mergeado | Sonda + aviso persistente do operator-kit; sem recarga automática (D9) |
| **F6** segundo clique | #1300 | ✅ mergeado | Bugs A, C, D corrigidos; **B é decisão sua (D1)** |
| **O6.1** cofre sem histórico de receitas | #1303 | ✅ mergeado | Única perda de dado da lista; versões entram no backup |
| **F4** consultas da sacola | #1304 | 🚦 na fila | −62 consultas por request com sacola; payload idêntico (A/B, 15 pares) |
| **O3a** link de pagamento no balcão | #1306 | 🚦 na fila | `link` só em Encomendas: trava no servidor + botão some no Balcão |
| **O1** nome+sobrenome no login WhatsApp | #1305 | ✅ mergeado | Divide na entrada, guarda o texto cru; backfill é decisão sua (D8) |
| **O5A** etapas das receitas estruturadas | #1307 | 🛠️ checks | `steps` com modo de fazer/tempo/nota; nota do item chega à ficha |
| **F3** P2 disponibilidade (Core) | — | 🛠️ em andamento | Um cálculo por request; mede `/catalog/` (O2); equivalência obrigatória |
| O2 rota `/menu` | — | ✅ não mexer | Veredito: não procede |

**Precisa de você (detalhe em [PENDING-DECISIONS](PENDING-DECISIONS.md)):**
🔴 **D2 Stripe em `cs_test_` no alpha (gate de go-live)** · D3 link "entregue" sem entrega (ManyChat) ·
D1 botão "Adicionar" inerte até carregar · D4 motivos de rejeição · D5 modo de fazer das receitas ·
D6 storage de anexos · D7 critérios da nota · D8 backfill de nomes · D9 PWA forçar versão nova ·
D10 trilho de sugestão no `shell/`.

**Produção:** no ar a cada verificação (monitor a cada 90 s). Deploys da noite saindo pelo
`deploy-images.yml`, causa `manual`, sem intervenção. Nenhuma escrita no spec vivo.

---

## Detalhe por frente

### Briefing (#1297)
PR aberto do branch `dsh/handoff-onda1-e-p7-20260930` e enfileirado. Nenhum arquivo alterado.

### F1 — #1291 vermelho → corrigido
- **Causa:** o PR desliga `deploy_on_push` nos 8 componentes de imagem, mas
  `shopman/shop/tests/test_nuxt_deploy_config.py` (`assert_image`) ainda exigia `enabled is True`.
  Derrubava `Testes (test-shop)` (obrigatório), `Shop rest` e `Coverage Gate`.
- **Correção:** o teste passa a exigir que NÃO esteja ligado, com a mensagem apontando o
  `deploy-images.yml` (um deployment por run). Docstring atualizada.
- **Prova:** `pytest test_nuxt_deploy_config.py test_do_spec_drift_check.py` → `38 passed`.
- Commit empurrado no próprio branch do #1291 (mesma frente); auto-merge já estava ligado.

### F2 — `brace-expansion` (#1298)
- **Causa:** `npm audit --audit-level=high` do operator-kit reprova o check *Marketing — cadeia
  completa* em todo PR. Os **10** locks de `surfaces/` tinham a versão vulnerável.
- **Correção:** só as entradas `brace-expansion` (2.1.4→2.1.7, 5.0.9→5.0.12), com `balanced-match`
  conferido por script no caminho de lookup de cada entrada.
- **Por que não `npm audit fix`:** re-resolvia o lock inteiro em 6 apps (≈10 mil linhas, bindings
  nativos do `@oxc-parser` sumindo porque a resolução roda no macOS). Descartado.
- **Prova:** `npm audit --audit-level=high` OK nos 10; `npm ci` limpo no operator-kit e no
  storefront; `check_surface_versions.py` ✓.

---

## Saúde da produção (medições)

| Hora (UTC) | Loja `www.nelsonboulangerie.com.br/` | API `/health/live/` | `/health/ready/` | Deployment ativo |
|---|---|---|---|---|
| 01/10 00:0x | 200 (2,5 s) | 200 | 200 | `405e3f25` manual, ACTIVE 30/09 23:12 |

### O6 fatia 1 — cofre (#1303)
- **Defeito:** `shopman/shop/backup/resources.py` levava `Recipe`/`RecipeItem`, nada de
  `RecipeEntry`/`RecipeVersion`. Restore devolvia a última ficha e perdia todo o histórico.
- **Correção:** abas `recipe_entries` e `recipe_versions` (chave `entry__ref`+`number`; coluna
  `is_current` restaura a `current_version`). Sem migração, sem `packages/`.
- **Prova:** 2 testes novos (apaga tudo → restaura cada campo; versão reescrita → volta);
  `test_backup.py` 16 passed, `_drive` 4, `_sheet_domain` 4, backstage `_backup_api` 3.

### F6 — segundo clique (#1300)
- A: o navegador não faz mais a semente de CSRF antes do 1º clique (era um GET da sacola inteira
  com erro engolido); a semente do BFF que cai na rede não derruba mais a mutação; `csrf;dur` no
  `Server-Timing`. C: `refreshCart` descarta resposta anterior à mutação (época). D: decremento
  único em `finally`. 6 testes novos vermelhos no código antigo, verdes agora.
- B ficou de fora: muda o que o cliente vê na carga. → D1.

### F4 — consultas da sacola (#1304)
| endpoint | sem sacola | 1 item antes → depois | 5 itens antes → depois |
|---|---:|---:|---:|
| `home/` | 45 | 166 → **104** | 199 → **134** |
| `catalog/` (página `/menu`) | 66 | 72 → 72 | 72 → 72 |
| `menu/` | 66 | 187 → **125** | 220 → **155** |
| `shell/` | 3 | 118 → **56** | 151 → **86** |
| `cart/` | 1 | 117 → **55** | 150 → **85** |

`catalog/` não monta a sacola (por isso não muda). Maior culpado: `keywords.names()` do taggit 6.1
ignora o prefetch (~55 consultas por sacola). Prova: JSON idêntico, código velho × novo no mesmo
processo e banco, 15 pares sacola × endpoint. Teste de orçamento novo trava o ganho. O que ainda
cresce com a sacola é a fila de espera (`waitlist.py`), que é da F3.

### O3a — link no balcão (#1306)
Trava `link_requires_order_mode` no `close_sale` (422, mesma frase na tela e no servidor); a
projeção publica `sales_modes` por forma de pagamento e o PDV esconde o link no Balcão.
`is_counter_takeaway` intocado. Fora: O3b (entrega pelo ManyChat, D3) e O3c (Stripe, D2).

### O1 — nome no login WhatsApp (#1305)
Regra da casa (`split_full_name`) desceu para `packages/utils` (o guestman não pode importar do
`shop`); as duas cópias do orquestrador foram apagadas. Divide no ponto único de escrita do
ManyChat, nunca sobrescreve campo preenchido, guarda o texto cru em
`metadata.manychat_name_raw`. `entrar.vue` manda nome e sobrenome. Limitação dita: "Ana Maria
Silva" vira Ana / Maria Silva. Vale conferir em 1 minuto se o Flow do ManyChat manda a variável
certa.

### F5 — PWA (#1301)
Registro do SW num plugin (vale também na tela de erro), sonda a cada 30 min e ao voltar ao app,
aviso persistente sem fechar (some no checkout, pedido e login), `app_version` no relatório de
erro, e2e do fluxo inteiro. Fora: recarga automática (D9), timeouts de fetch (medir antes),
registro de troca de versão (precisa endpoint). Ponto a conferir: se o build da loja na DO expõe
`SOURCE_VERSION`; se não, `app_version` sai `local`.

## Divisão do trabalho
- Coordenador (eu): briefing, F1, F2, relatório, fila de merge, saúde da produção.
- Agente F5 (worktree própria, branch `night/f5-pwa-storefront`).
- Agente F6 (worktree própria, branch `night/f6-segundo-clique`).
- Agente F4 (`night/f4-sacola-consultas`), sem tocar arquivos da F3.
- Agente O3a (`night/o3a-link-so-encomenda`) e agente O1 (`night/o1-nome-na-entrada`).
- Eu fiz O6.1 (#1303) direto.
- F3: depois, sozinha, nunca junto com F4.
