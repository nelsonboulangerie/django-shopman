# Faxina pré-alpha — varredura de 2026-08-13

> Pedido do Pablo: "corrigir divergências entre código e documentação, limpar o
> obsoleto, revisar decisões de design, naming, organização e estrutura — a casa
> precisa ter fundação extremamente sólida". Tudo abaixo foi **medido**, não
> lembrado; cada correção diz de onde saiu o fato.

## 1. Divergências código ↔ documentação (corrigidas)

| Doc dizia | Código/repo diz | Corrigido em |
|---|---|---|
| Suíte ~5.000 testes (~2.150 cores + ~2.870 framework) | **~6.500** (2.184 cores + 4.248 framework + 31 tools) — o framework cresceu 48% desde julho | CLAUDE.md, ROADMAP, status.md |
| "6 apps Nuxt" | **7** (o marketing-nuxt nasceu e três docs não notaram) | CLAUDE.md, ROADMAP, docs/README |
| `surfaces/broadcast-nuxt` no status.md | o app é **marketing-nuxt** (absorveu o broadcast) | status.md, tiktok-app-submission.md |
| Glossário: Order `new → confirmed → …` | o rename `confirmed`→`accepted` está no main desde 01/08 (`3b973a98`) | glossary.md, order-operational-contract.md, ifood-outbound-verification.md, qa-seed-scenarios.md, commands.md |
| ACCEPTED-STATUS-RENAME "não executado" | executado | header corrigido + arquivado |
| PAYMENT-TRACKING-MERGE "aguardando OK" | deployado e verificado ao vivo | header corrigido + arquivado |
| status.md parado em 2026-07-11 | um mês de trabalho invisível | atualizado (marketing, passkey, gaveta/crachá, funcionário pickup-only, reset de migrações) |

⚠️ **Armadilha que pegou até o relatório de alpha:** a última linha do log do
`make test` é o resumo do **bloco do framework**, não o total da suíte — o total
é a soma dos blocos. Registrado no status.md para não morder de novo.

## 2. Regressões e buracos fechados (código)

### `RuleConfig.params` com chave órfã não desliga mais a regra

O incidente `da69c714` (parâmetro renomeado no código sem migrar o JSON → a
regra de desconto de funcionário apagou em silêncio) estava **documentado mas
não guardado** — o docstring de `EmployeeRule` descrevia o buraco aberto.
`load_rule` agora ignora a chave desconhecida **em voz alta** (WARNING nomeando
a chave e o provável rename) e a regra segue viva com o que conhece. Teste
reproduz o incidente. Racional: para regra de **dinheiro**, o modo de falha
correto é degradar avisando, nunca sumir calado.

### Webhooks: a mesma pergunta tinha duas respostas

Token inválido respondia **401** em efi, ifood_events, manychat (guestman) e
machine — e **403** no ifood. Os dois lados estavam "documentados como
deliberados", o que só prova que divergência documentada continua sendo
divergência (violava one-question-one-owner). Unificado em **401** (falha de
autenticação); docstrings, testes e textos do `SHOPMAN_E004` acompanham.
**Exceção deliberada:** Stripe responde 400 para assinatura inválida porque é a
convenção que a própria Stripe documenta para o retry dela — contrato externo
manda.

### TODO real fechado

`dashboard.py` esperava "PR #110" para apontar o atalho do catálogo de copy à
tela própria — a rota `admin_console_copy_catalog` já existia. Apontado.

## 3. Verificado e SÃO boas notícias (nada a fazer)

- **Só existia 1 TODO real** em todo o código de produção (o de cima). O resto
  do grep é "TODO"="todos" em português.
- **Cobertura falsa do `test_persona_3_employee` já tinha sido consertada** — o
  fixture cria a `RuleConfig` de verdade e o docstring documenta o erro antigo.
- **Reset de migrações executado e são**: 19 iniciais + append (35 arquivos);
  RBAC nasce em `setup_groups`.
- **`_quarantine/` e `copy-wiring-backlog.txt` são deliberados** — o primeiro é
  quarentena documentada no README de planos; o segundo é artefato de gate lido
  por teste. Não são lixo.
- **Build artifacts (`packages/*/build/`, `*.egg-info`) não estão no git** — só
  no disco (gitignored; `make clean` os remove). Poluem grep local, nada mais.
- **Spec do staging sem env morta**: o diff spec↔settings só acusou
  falso-positivo de leitura multilinha.

## 4. Obsoleto removido / arquivado

Seis planos concluídos saíram do diretório de planos vivos para `completed/`
(headers corrigidos antes, referências cruzadas atualizadas): rating-loop,
catalog N+1, accepted-rename, payment-tracking-merge, discount-audit,
seed-data-quality.

## 5. Decisões revisadas (registro)

- **401 vs 403 em webhook**: decidido e aplicado — 401 para autenticação; 400 na
  Stripe por contrato externo. Fim da pendência
  `project_webhook_status_code_inconsistency`. A rigor a decisão já tinha se
  tomado de facto: três webhooks novos entraram desde o registro da dívida e
  todos escolheram 401; o ifood estava 4 a 1.

- ⚠️ **REVISÃO DE DECISÃO DOCUMENTADA — chave órfã em `RuleConfig.params`.**
  Existia uma decisão anterior, fixada em teste
  (`test_the_obsolete_param_kills_the_rule_quietly`): dado velho DESLIGA a regra,
  e o conserto de rename é migração de dados. A faxina **reverte o primeiro
  termo e mantém o segundo**: a chave órfã agora é descartada com WARNING nomeado
  e a regra segue viva (NÃO é alias — `group` não vira `price_tier`); a migração
  de dados continua sendo o conserto correto (0010 existe e segue testada).
  O que mudou de entendimento: (a) regras **validator** morrem do mesmo jeito, e
  um guarda de horário comercial evaporado por typo é a loja aceitando pedido de
  madrugada; (b) o incidente `da69c714` provou que o "silêncio" dura semanas.
  Guarda não pode evaporar por chave órfã. A lápide antiga virou o teste do
  contrato novo, com o racional dos dois lados no docstring. **Se o Pablo
  discordar, o revert é pequeno e o teste antigo está no git.**
- **Nada encontrado que justifique rename ou reorganização estrutural** nesta
  passada: a regra de dependência (storefront → shop ← backstage, cores nunca se
  importam) está respeitada nos pontos amostrados; vocabulário do glossário bate
  com o código após as correções acima.

## 6. Fica com o dono (não é código)

- **Lixo local na raiz** (gitignored, invisível ao git, mas no disco):
  `broadcast_demo*.mp4`, `tiktok_demo_video.mp4`, `dump.rdb`, `temp/`,
  `.tunnel*.log`, `.coverage` e **`guia-credenciais-broadcast.pdf`** — este
  último o GO-LIVE-READINESS já manda mover ao gerenciador de segredos e apagar.
- **`NUXT_PUBLIC_PRODUCTION_URL` segue ausente do spec** — o link "Resolver na
  produção" do fechamento do PDV (`closing.vue:124`) segue escondido por `v-if`.
  Uma linha no spec LIVE (`https://prod.boulangerie.com.br`) resolve.
- **Gaveta/crachá**: código pronto; falta instalar o agente no balcão e QA
  físico.

## Verificação

`make test` e `make lint` verdes após todas as mudanças (ver PR).
