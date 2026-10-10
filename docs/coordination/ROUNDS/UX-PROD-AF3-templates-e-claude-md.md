# UX-PROD-AF3: avisos de produção no banco vivo e rotas do CLAUDE.md

**Estado:** pronto (PR aberto, auto-merge ligado). Seguimento do UX-PROD-AF (#1433).

## O que mudou

1. **Migração `shop.0088_avisos_de_producao_por_lote`.** O #1433 trocou no seed o texto de
   dois modelos de mensagem ao operador; o alpha só os veria com reseed. A migração leva o
   texto novo ao banco vivo:

   | evento | campo | antes | depois |
   |---|---|---|---|
   | `production_low_yield` | assunto | "Yield baixo na produção {work_order_ref}" | "Aproveitamento baixo no lote {work_order_ref}" |
   | `production_low_yield` | mensagem | "A produção … fechou com yield de {yield_percent}%. …" | "O lote … fechou com aproveitamento de {yield_percent}%. …" |
   | `production_forgotten` | assunto | "Produção {work_order_ref} não foi iniciada" | "Lote {work_order_ref} não foi aberto" |
   | `production_forgotten` | mensagem | "… nunca foi iniciada. Conclua, reagende ou estorne no planejamento." | "… nunca foi aberto. Abra, reagende ou cancele no planejamento." |

   Reescreve campo a campo, só onde o texto no banco ainda é EXATAMENTE o antigo do seed
   (edição no Admin fica intacta); sobe a `version` operacional junto, para um formulário do
   Admin aberto antes não gravar por cima sem aviso; reversível; roda em banco vazio.
   O #1433 não mudou outro texto de seed (OmotenashiCopy, RuleConfig ou outro template):
   o diff dele em `config/` é só esse; a migração `craftsman.0017` dele cuida dos rótulos
   de status.

2. **CLAUDE.md**: a linha das apps Nuxt de operador deixa de citar `/expedite` e "rotas
   pt-br antigas respondem 301 (PR #68)". Passa a listar as rotas atuais e a regra vigente
   (pré go-live, rota renomeada não ganha redirect), e nomeia os 301 que ainda existem
   (Cozinha `/estacao/**`, `/cliente`, `/retirada`; PDV `/tickets`, `/preorders/panel`,
   `/preorders/today`, `/preorders/week`), sem removê-los. `/showcases` saiu da lista:
   não existe em nenhum app.

3. **`docs/plans/SUITE-UX-V2-PLAN.md` §4.4** (plano ativo): a frase "endereço antigo
   responde 301" e a linha da Produção (`/expedite`, `?queue=quality`) atualizadas.

## Fora, de propósito

- Os 301 remanescentes de Cozinha e PDV ficam (o brief pede só descrever).
- `/expedite` segue em ROUNDS, relatórios e fichas de engenharia reversa
  (`docs/plans/suite-ux-v2/funcoes/*`, `ADMIN-ROLE-PLAN`, `PRODUCTION-IRREPRESSIBLE-*`):
  são retrato do código na data, história.
