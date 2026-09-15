# L7 — replay seletivo de R10 e R12

**Estado:** implementação técnica preparada e validada localmente; não publicada

**Branch:** `codex/marketing-r10-r12-replay-20260915`

**Commit funcional:** `9d3eebb67`

**Base composta:** `943f437de`, reconciliada sem conflito com `origin/main`
`6f66f3754` pelos merges locais `8e9078491`, `747fbef17` e `372e9fd34`.
As atualizações posteriores à primeira validação trouxeram somente o reparo do
ícone PWA do Storefront e o gate de capacidade determinístico já aprovado no
PR #683; não sobrepuseram os arquivos funcionais de R10/R12.

**Efeito externo:** nenhum

## Decisão de composição

O branch histórico `codex/data-retention-l7-contract-20260914` não foi tratado
como superset. A auditoria mostrou que sua integração integral reabriria gates
já fechados de cancelamento e maioridade. Por isso não houve cherry-pick nem
merge do branch L7.

Foram replayadas por unidade apenas as três consequências aprovadas:

1. **R10:** `auth_cleanup` aceita somente a retenção fixa de sete dias, tem
   dry-run em português sem PII e executa as três etapas de forma isolada;
2. **R12:** a redação canônica cobre logs JSON e humanos, Sentry e telemetria do
   cliente, reduzindo URLs livres à origem;
3. **R12/OTP:** `ConsoleSender` e `LogSender` não expõem código nem destino, e o
   startup de produção recusa qualquer emissor local presente na cadeia efetiva.

Google OAuth, retenção de IP de consentimento, contrato PWA, cancelamento e
maioridade da base composta foram preservados. A documentação recebeu somente
as linhas R10/R12, o inventário técnico e o contrato L7; não foram importadas
versões antigas de outras seções.

## Verificação local final

- 60 testes passaram: comandos R10, emissores Doorman, redação/formatters,
  Sentry, telemetria Backstage e dry-run R01–R15;
- Ruff passou em todos os arquivos Python tocados;
- `git diff --check` passou;
- `data_retention --dry-run --json` foi executado em SQLite recém-migrado,
  retornou `mode=dry-run`, `mutations=0`, `pii=false` e as 15 regras; o banco
  descartável foi removido depois da prova;
- nenhum provider, segredo, destinatário, job, `--apply`, ambiente remoto ou
  produção foi acessado.

## Gates mantidos

- R10 ainda precisa de agendamento real e alerta de falha aprovados;
- R12 ainda precisa de TTLs e acessos comprovados em DigitalOcean/Sentry,
  classificação das tabelas persistidas, job monitorado, teste PostgreSQL,
  idempotência e restore;
- descarte de dados e ativação de jobs em produção continuam bloqueados por
  dry-run revisado e gate humano separado;
- a branch não deve ser publicada como PR concorrente enquanto o draft #614
  não tiver base definitiva e os gates L1/L7 resolvidos.
