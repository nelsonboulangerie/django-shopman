# Execução — lifecycle do polling de Produção

- Data: 14 de setembro de 2026
- Worktree exclusivo: `/tmp/shopman-production-polling.azjhh4`
- Branch: `codex/production-polling-lifecycle-20260914`
- SHA-base: `84e07c01d04eba4ed0deabdae0d2df18dde77c53`
- Escopo: WP-P1.1 / PROD-011, somente `useAdaptivePoll` e regressões focais

## Risco reproduzido

O fallback de polling tinha intervalo fixo sem jitter ou backoff. A atualização disparada por
`visibilitychange` não tratava uma Promise rejeitada. Se o componente fosse desmontado enquanto
um refresh periódico ainda estivesse em voo, o `finally` implícito do callback voltava a agendar
um timer depois do descarte.

## Contrato implementado

- cada agendamento recebe jitter positivo de até 20%;
- falhas consecutivas aplicam backoff exponencial com teto de 8× e sucesso restaura a cadência;
- somente um refresh fica em voo;
- refresh ao voltar para a aba passa pelo mesmo tratamento de erro/backoff;
- dispose cancela o timer e impede qualquer rearm posterior, inclusive após resposta tardia.

## Evidência

- Node 22.23.2, regressão focal: 1 arquivo / 10 testes aprovados;
- Node 22.23.2, Produção Nuxt completa: 37 arquivos / 285 testes aprovados;
- typecheck com Node 22: aprovado;
- ESLint focal com Node 22: aprovado;
- build Nuxt/Nitro de produção: aprovado (warnings conhecidos de sourcemap do Tailwind);
- `git diff --check`: aprovado.

Nenhum provider, deploy, push, PR ou dado externo foi acionado.
