# Runbooks operacionais

Runbooks curtos para incidentes P1/P2 de operacao real. Eles assumem que o
operador nao executa Docker diretamente: use os wrappers `make`.

## Regra de leitura

- `result=OK`: nao ha achado critico naquele diagnostico.
- `WARN`: ha risco ou ambiente incompleto; confirmar contexto antes de agir.
- `FAIL`: ha acao operacional pendente. Preserve evidencia antes de corrigir.

## Runbooks

### Marketing — decisão e recuperação

Todos começam pelo mesmo snapshot seguro: `make marketing-diagnose`
(`receipt=<UUID>` e `platform=<canal>` são filtros opcionais). Ele é read-only,
não chama provider e não exibe PII. O gate sintético inteiro é um comando:
`make marketing-drills`.

- [Command, outbox ou worker travado](marketing-stuck-command.md)
- [Entrega parcial e retry seletivo](marketing-partial-retry.md)
- [Efeito do provider desconhecido](marketing-unknown-provider-effect.md)
- [Readiness de canal indisponível](marketing-channel-readiness-outage.md)
- [Incidente de consentimento ou privacidade](marketing-consent-or-privacy-incident.md)
- [Conteúdo, oferta, mídia ou link incorreto](marketing-bad-content-or-link.md)
- [Cancelamento, duplicidade e reconciliação](marketing-cancel-and-reconcile.md)
- [Rollback e rollout interrompido](marketing-rollout-rollback.md)
- [Canário unitário de publicação pública](../operations/marketing-publication-canary.md)

Execução automatizada não fecha sozinha o gate: antes do piloto, um operador que
não implementou deve percorrer as oito decisões e assinar a evidência do MKT-044.

### Demais domínios

- [Webhook falhando](webhook-falhando.md)
- [Pagamento divergente](pagamento-divergente.md)
- [Pedido pago sem confirmacao](pedido-pago-sem-confirmacao.md)
- [Redis fora ou SSE sem fanout](redis-fora.md)
- [PostgreSQL lento ou indisponivel](postgres-lento.md)
- [Directive worker parado](directive-worker-parado.md)
- [Estoque divergente](estoque-divergente.md)
- [Loja aberta/fechada em estado errado](loja-estado-incorreto.md)
- [Pedido remoto preso](pedido-remoto-preso.md)
- [Rollback de deploy quebrado](rollback-de-deploy.md)
- [Alpha tecnico pronto-para-virar](alpha-technical-readiness.md)
- [Alpha DigitalOcean - handoff operacional](alpha-digitalocean-handoff.md)
- [Ativar Focus NFe (NFC-e): homologação → produção](ativar-focus-nfe.md)
- [Pré-flight de go-live (switches antes do alpha/produção)](go-live-preflight.md)

## Procedimentos

- [Go-live — checklist de cutover (staging → produção)](go-live-cutover.md)
- [Ligar o Sentry (error tracking)](ativar-sentry.md)
- [Conferir o spec antes de `doctl apps update`](conferir-spec-digitalocean.md)
- [Branch protection do `main` — decisões pendentes](branch-protection-pendencias.md)
