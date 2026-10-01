# NIGHT-REPORT — turno autônomo 30/09 → 01/10/2026

> Coordenador: Claude (sessão `turno-autonomo-coordenacao`). Briefing:
> `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md` (#1297 + #1302).
> **Decisões que são suas: [`PENDING-DECISIONS.md`](PENDING-DECISIONS.md)** (D1–D16).

## Turno de 01/10 (manhã): Frentes 0 a 8

> Coordenador: Claude (sessão `turno-autonomo-go-live`). Entrada única do estado:
> [`../go-live-acceleration-20260929/HANDOFF.md`](../go-live-acceleration-20260929/HANDOFF.md).
> Decisões novas: D17 a D24 em [PENDING-DECISIONS](PENDING-DECISIONS.md).

| Frente | PR | Estado | O que mudou para você |
|---|---|---|---|
| 0 higiene | #1299, #1325, #1327 | mergeados | NIGHT-REPORT, PENDING-DECISIONS e os diagnósticos D4/D5/D14/D16 no `main`; HANDOFF vira entrada única. O #1324 já estava mergeado (09:00) |
| **1 token da Efí no access log (D14)** | spec vivo | ✅ feito 09:21 UTC | `web` agora roda com `--access-log=/dev/null`. Diff de uma linha, 42 SECRET idênticos, drift [OK], sonda com token falso não aparece no log |
| **2 lei da data + 409 de ajuste (D16)** | #1329 | na fila | A sacola da loja **aceitava** itens de datas diferentes; agora recusa e diz "Isso fica para outro pedido". O 409 de ajuste mostra o teto da linha ("Pré-reservar 4 unidades no total") e nunca encolhe a linha |
| 3 "Etapa" (D5) | #1326 | mergeado | Telas dizem "Etapas"; decisão no `suite-vocabulary.md`; duas travas; processo das 11 massas (92 etapas) no repo |
| 4 motivos de recusa (D4) | #1328 | na fila | Lista aprovada de 11, agrupada, "Outros" que foca o texto; ponto final recusado; migração de dados leva a lista ao alpha só se ninguém editou |
| 5 clique nunca inerte (D1) | #1330 | na fila | "Adicionar" ativo desde o primeiro quadro, toque precoce repetido uma vez; `usePendingAction` no kit e na loja; trava que só encolhe |
| 6 custo fixo por request (D12) | #1331 | na fila | Um pool de Redis por processo (bancada TLS: 103 → 3 conexões em 100 requests) e `gc.freeze()` (pausa máxima 86 → 9,7 ms). Degrau 1 (`CONN_MAX_AGE=0`) é seu (D21) |
| 7 referências + nota (D6/D7) | #1332 | na fila | "Referências" (livros, vídeos, artigos) na receita, em `RecipeEntry.meta`, sem upload; nota 0 a 5 por versão com critérios editáveis no Admin (Sabor, Textura, Aparência), um voto por operador |
| D13 fichas com insumo repetido | só leitura | ✅ nada a fazer | No alpha, 72 receitas com versão atual e 74 versões: **zero** com o mesmo SKU em duas linhas |
| 8 picos Cloudflare ↔ DO (D15) | só medição | sem sintoma hoje | 400 requisições 09:23–09:27 UTC, 0 erro, 0 acima de 5 s (detalhe abaixo) |

### Frente 1 em detalhe (D14)
- `make deploy-spec-drift context=shopman-do-app-admin` acusava só o `run_command` do `web`.
- Backup do spec vivo, `sed` em uma linha, `apps update`; SECRET antes × depois: 42 = 42 (chave e hash
  do valor cifrado); `spec get` depois difere do backup só nessa linha. Deployment `50988cd5` ACTIVE.
- Busca no log: só o deployment ativo devolve log pelo `doctl` (347 linhas, 09:05–09:19 UTC; os 59
  anteriores não devolvem): **0** `token=`, **0** `efi/pix`. Depois do deploy, POST com token falso → 401
  e a sonda não aparece; a única linha é do `django.request`, que já grava `token=[redacted]`.
- **Token NÃO rotacionado.** Rotação é OBRIGATÓRIA antes de ligar a Efí de produção (D14).

### Frente 2: o que a apuração achou
- (a) A sacola aceitava datas distintas: cada SKU escolhe a data (pronto = hoje; fila = data da
  fornada) e nada comparava com as datas que a sacola já tinha. Teste escrito antes do conserto: 3 de
  7 cenários passavam com 200.
- (b) ⚠️ **A premissa do balcão não se sustenta.** A comanda tem **uma data por sessão**
  (`session.data["delivery_date"]`), `POSTab` não tem data e as linhas da comanda não carregam data.
  O `TestOneLineOneDate` é teste da **loja** (PUT em `/api/v1/cart/skus/`). Não existe "1 linha = 1
  data" no balcão para vigiar; o teste não foi escrito porque inventaria um contrato (D17).
- (c) O cliente via a linha da fornada com "Lista de espera / Previsto para amanhã" ao lado da de
  hoje, e o checkout seguia liberado.
- Achado de carona: `available_qty` saía como texto `"3.000"` e a folha, que só aceita número,
  sumia com o botão "Levar N". Agora sai inteiro.

### Frente 3: o processo das 92 etapas
Resgatado do artifact `b8cd4fc0-…` ("Fichas dos Pães", 05/09) para
`docs/reference/processo-das-massas-proposta-2026-09-05.md`. ⚠️ **Não é temperatura da casa:** o
artifact chama o processo de "proposta minha, é a parte que eu menos sei" e o rodapé diz que tempos,
temperatura da massa e ponto de fermentação são o que só o dono sabe. Não vai para seed nem banco.

### Frente 8: medições (anônimo, `api.boulangerie.com.br`, rede local, POP GRU)
| Teste | n | p50 | p95 | max | > 5 s |
|---|---|---|---|---|---|
| `shell/` 12 KB, alternado | 45 | 0,418 s | 0,493 s | 0,880 s | 0 |
| `home/` 19 KB, alternado | 45 | 0,644 s | 0,749 s | 0,813 s | 0 |
| identity × gzip | 25 + 25 | 0,714 × 0,710 s | 0,884 × 0,894 s | | 0 |
| IPv4 × IPv6 | 25 + 25 | 0,738 × 0,740 s | 0,802 × 0,877 s | | 0 |
| HTTP/1.1 × HTTP/2 | 20 + 20 | 0,733 × 0,750 s | 0,918 × 1,177 s | | 0 |
Tamanho, encoding, IP e H1/H2 descartados. **Não medidos:** HTTP/3 (curl local sem suporte), outra
rede (sem VPN/VPS), `home/` com sessão. Deployments da madrugada: o início (04:26) e o 525 (04:58)
caem em troca; o **520 das 04:44:41 e o trecho 05:02–05:07 não**. Com troca em ~40% do tempo entre
04:22 e 05:12, 2 de 4 é o esperado por acaso. Chamado na DO só para pedir log do LB da janela
04:26–05:09 (rascunho em D23).

---

## Turno de 30/09 → 01/10 (madrugada)

## Em uma tela

**Resultado de performance, medido no ar (medianas, anônimo):** `catalog/` (a página `/menu`) TTFB
**1,79 s → 1,08 s (−40%)**, projeção 1.466 → 748 ms; `home/` TTFB **1,07 s → 0,69 s**, projeção 775 → 392 ms.

**Produção:** no ar a noite toda. Nenhuma escrita no spec vivo, nenhuma recuperação precisou ser
usada. Deploys saíram sozinhos pelo `deploy-images.yml`. Leia "Observação" abaixo: picos de 15–40 s
na `home/` privada desde ~04:26 UTC; investigados, estão entre a Cloudflare e a DO, não no app (D15).

**Mergeado (28 PRs):**

| Frente | PR | O que mudou para você |
|---|---|---|
| Briefing + 6.2 | #1297, #1302 | Docs da noite no main |
| F1 drift do spec | #1291 | `make deploy-spec-drift` volta a poder ficar verde |
| F2 audit `brace-expansion` | #1298 | "Marketing — cadeia completa" parou de reprovar todo PR |
| **F3 disponibilidade num cálculo só** (Core) | #1309 | **`/catalog/` (página `/menu`): disponibilidade 853 → 396 ms, TTFB 1,79 → 1,44 s no ar** (com a Onda 2a e a F4b: **1,08 s**) |
| F4 consultas da sacola | #1304 | −62 consultas por request com sacola; payload idêntico |
| Onda 2a catálogo fora da disponibilidade | #1314 | 36 → 15 ms na bancada (≈ −350 ms no ar, a medir); Destaques com até 5 min de atraso |
| Onda 2b Server-Timing `connect`/`cache`/`gc` | #1313 | Custo fixo por request agora visível (ver D12) |
| Sitemap pela gêmea pública | #1312 | O `menu/` lento ficou sem consumidor de produção |
| **F5 PWA travado** | #1301 | App instalado sonda versão nova e avisa até atualizar |
| **PWA "Atualizar" não aplicava** (defeito real) | #1311 | O spinner buscava ícone pela rede no meio da troca de worker |
| Ícones empacotados nos 8 apps de operador | #1316 | Mesmo gatilho do #1311, fechado e travado por teste |
| **F6 segundo clique** | #1300 | Bugs A, C, D; **B é sua (D1)** |
| O1 nome/sobrenome no login WhatsApp | #1305 | Divide na entrada; backfill é seu (D8) |
| O3a link de pagamento no balcão | #1306 | `link` só em Encomendas (servidor + tela) |
| **O6.1 cofre sem histórico de receitas** | #1303 | Única perda de dado da lista: versões entram no backup |
| O6.2/3 versão imutável + ficha em sincronia | #1308 | Versão publicada não muda nem se apaga (D11) |
| O5A etapas estruturadas | #1307 | `steps` = `{name, instructions, target_seconds, note}`; migração 0015 aplicada no alpha |
| O8 reputação por versão (leitura) | #1310 | Produção por `version_ref`, com os avisos de perda no dado |
| **BOM: mesmo insumo em duas linhas** (Core) | #1317 | Ficha gravava 100 g de água em vez de 700 g; republicar é seu (D13) |
| FUSO testes 21h–24h | #1315 | 2 testes que reprovavam perto da meia-noite; código estava certo |
| F4b disponibilidade reaproveitada no request | #1318 | `home/` com 6 itens 72 → 51 consultas; revisão independente: seguro |
| O8 Favorita por operador | #1319 | Estrela no inventário de receitas + filtro "Favoritas" |
| P5 payload do cardápio sem cards duplicados | #1321 | `catalog/` 142 → 56 KB (−61%; gzip −47%); tela provada idêntica |
| Onda 2c miúdos | #1322 | PUT da sacola 478 → 198 consultas (reduzir) e 289 → 189 (aumentar); revisão independente: seguro |
| Drift compara `run_command` | #1320 | Contra o vivo acusa exatamente o D14 e nada mais |
| **Sacola perdia a reserva ao ajustar quantidade com fila** (defeito que estava no main) | #1323 | Ajuste ancora na data da linha; reduzir nunca falha nem perde o que existe; sobra que cai no pão pronto vira reserva comum. Duas revisões independentes (a 1ª segurou e achou 2 regressões, corrigidas). Regras abertas em D16 |
| Seguimento: a margem da vitrine não leva o pão que a sacola já segurava | #1324 | Revisão independente com fuzz de 500 cenários: seguro. Limite declarado: com dois quants e a validade preferindo o outro, a unidade ainda pode se perder (pede mudança no Core; nunca vende a mais) |

**Ao encerrar (09:05 UTC):** nada desta noite ficou dormindo. Todas as frentes estão mergeadas; abertos só
ficam este relatório (#1299, entra na fila agora) e o #1293, de outra sessão (`CONFLICTING`).
Saúde final: `/health/live` 200, `/health/ready` 200, `www` 200.

**Na fila / aberto:**

| Frente | PR | Estado |
|---|---|---|
| NIGHT-REPORT | #1299 | na fila (só docs) |
| (outra sessão) contexto doctl nos docs | #1293 | `CONFLICTING`, não é desta noite |

**Precisa de você** (detalhe em [PENDING-DECISIONS](PENDING-DECISIONS.md)):
🔴 **D14 access log do `web` grava o token da Efí (spec vivo)** · 🔴 **D2 Stripe em `cs_test_` no alpha (gate de go-live)** · D15 picos entre Cloudflare e DO (chamado) · D3 link "entregue" sem entrega (ManyChat) ·
D13 republicar fichas com insumo repetido · D12 conexão nova por request (pool) · D1 botão "Adicionar"
inerte até carregar · D4 motivos de rejeição · D5 modo de fazer · D6 storage de anexos · D7 critérios
da nota · D8 backfill de nomes · D9 PWA forçar versão · D10 sugestão no `shell/` · D11 versão não se apaga · D16 regra do 409 de ajuste da sacola.

---

## Observação de produção (não é queda)

- Desde ~04:26 UTC a `home/` **privada** (cliente com sessão; a loja anônima usa a gêmea pública
  cacheada e não sofre: `www` 0,6–0,8 s) tem picos de 15–40 s, timeouts e um 520 da Cloudflare,
  intermitentes (às 05:02–05:07 cerca de metade dos requests; às 05:08–05:09, 16/16 normais).
- O log da origem mostra a `home/` terminada 1–2 s depois do início do request do cliente, mesmo
  quando o cliente esperou 27–35 s: a origem responde, e os bytes empacam entre ela e o cliente.
  Um request recebeu 13 de 19 KB em 40 s. Com URL diferente (`?probe=N`) não reproduziu.
- **Conclusão da investigação só-leitura (D15):** não é o app. Banco/PgBouncer, loop do daphne e CPU
  descartados com prova; o processo atendia outros requests no mesmo instante. A assinatura bate com
  perda de pacote ou MTU no salto Cloudflare ↔ load balancer da DO (passa o que cabe na janela TCP
  inicial, ~14 KB; um 525 de TLS Cloudflare → DO às 04:58). Próximo passo é chamado na DO (D15).
- **Achado lateral de segurança (D14):** o `web` vivo roda sem `--access-log=/dev/null` e grava a URI
  crua (token do webhook da Efí). O drift não comparava o comando; passa a comparar no #1320.
- Os "000" de saúde durante a noite coincidem com cada troca de deployment: o `web` é **1 instância
  de 1 vCPU com um processo daphne**, então cada deploy dá alguns segundos de indisponibilidade.

## Medições de produção

| Quando (UTC) | Deployment | `catalog/` TTFB | availability | `home/` TTFB | Nota |
|---|---|---|---|---|---|
| 02:33 | `5462dcc7` | 1,79 s | 853 ms | 1,07 s | base (F4/F5/F6 no ar) |
| 02:45 | `acbfc026` | **1,44 s** | **396 ms** | 1,13 s | F3 no ar |
| 04:25 | `16676254` | 1,41–1,87 s | 370–440 ms | 1,2–2,2 s + picos | Server-Timing novo |
| 05:54 | main `95678415a` | **1,08 s** | **302 ms** | **0,69 s** | + Onda 2a, F4b, Favorita |

Custo fixo por request (#1313, medido no ar): `connect` 30–65 ms (sempre 1 conexão nova),
`cache` ~25 ms **por chamada** ao Redis (3–7 chamadas), `gc` normalmente < 10 ms com picos de 265–325 ms.

---

## Detalhe das frentes

### F1 — #1291
`test_nuxt_deploy_config.py` exigia `deploy_on_push` ligado; o PR desliga como o vivo. O teste passou a
exigir desligado. 38 testes do spec/drift passam.

### F2 — #1298
Troca cirúrgica de `brace-expansion` nos 10 locks (2.1.4→2.1.7, 5.0.9→5.0.12). `npm audit fix` foi
descartado: re-resolvia locks inteiros (≈10 mil linhas, bindings nativos sumindo).

### F3 — #1309 (Core)
Uma leitura de estoque por request (eram 4). `availability_for_skus_on_dates` no Stockman;
`availability_for_skus` é o caso de uma data. Prova: oráculo antigo congelado, 48 recortes × 6 datas,
mutação (32 e 48 testes reprovam), JSON idêntico, digest do Continuum igual. **P7 não aplicado; trava
intacta.** Revisão independente: "seguro".

### F4 — #1304 e F4b — #1318
F4: `keywords.names()` do taggit 6.1 ignorava o prefetch (~55 consultas por sacola); uma leitura de
`Product`; holds planejados em lote. `home/` com 1 item 166 → 104 consultas. F4b: memo por request
(só GET/HEAD, desligado em qualquer escrita SQL) para catálogo, sacola e sugestão não recalcularem o
mesmo SKU; `home/` com 6 itens 72 → 51. Revisão independente: mecanismo seguro.

### Onda 2a — #1314 · Onda 2b — #1313 · Sitemap — #1312
Ver tabela. A medição que originou as três: ~60% do que sobra no `catalog/` é custo fixo por request
(conexão de banco e Redis novas a cada request sob ASGI), não código do catálogo → D12.

### F5 — #1301 · PWA real — #1311 · ícones — #1316
F5 portou do operator-kit: registro do SW num plugin, sonda a cada 30 min, aviso persistente (some no
checkout/pedido/login), `app_version` no relatório de erro. O e2e novo pegou um **defeito real**: o
spinner do "Atualizar" buscava `line-md` pela rede no instante em que o Chromium desliga o worker
antigo, o que o reinicia e adia a ativação. Ícones empacotados na loja (#1311) e nos 8 apps de operador
(#1316), com teste-trava. Sem recarga automática (D9).

### F6 — #1300
A: sem semente de CSRF no navegador antes do 1º clique; semente do BFF que cai não derruba a mutação;
`csrf;dur` no Server-Timing. C: `refreshCart` descarta resposta anterior à mutação. D: decremento em
`finally`. B → D1.

### O1 — #1305 · O3a — #1306
O1: `split_full_name` desceu para `packages/utils`; divide no ponto único de escrita do ManyChat, guarda
o texto cru, não sobrescreve campo preenchido. Vale conferir em 1 minuto se o Flow manda `{{Last Name}}`.
O3a: `link_requires_order_mode` no `close_sale`; a projeção publica `sales_modes`; `is_counter_takeaway`
intocado.

### Receitas — #1303, #1307, #1308, #1310, #1317
- #1303 cofre: abas `recipe_entries` e `recipe_versions` (`is_current` restaura a atual).
- #1308: versão fechada recusa reescrita e exclusão por qualquer caminho do ORM (inclusive cascata);
  o restore do cofre usa um caminho nomeado (`restoring_recipe_versions()`); `execution_in_sync` na
  projeção com impressão digital da ficha.
- #1307: etapas estruturadas; migração `craftsman 0015` (aplicada no alpha às 04:51 sem erro; eu
  acrescentei a guarda que para a migração se `steps` não for lista, em vez de virar uma etapa por letra).
- #1310: produção por versão, com balde "sem versão" e avisos de perda contábil/estimada.
- #1317: análise da fórmula sobrescrevia a linha anterior do mesmo SKU; a ficha recebe a soma certa.

### FUSO — #1315
Os testes liam o relógio duas vezes e pegavam a meia-noite no meio. Código já usa o calendário da loja.
Relógio congelado às 12h e 23h30 de Brasília, com prova por mutação.

## Divisão do trabalho
- Coordenador: briefing, F1, F2, O6.1, sitemap, conflitos do #1307, guarda da migração 0015, fila,
  medições de produção, relatório.
- Um agente por frente, cada um na sua worktree e no seu branch `night/*`; duas revisões
  independentes (F3, F4b) antes do merge; um agente só de medição (catálogo) e um de investigação (picos).
