# IFOOD-E — ensaio na loja de teste

- **id:** IFOOD-E
- **sessão:** frente 6, turno 2 de 19/10/2026 (Codex)
- **branch:** `codex/ifood-ensaio`
- **PR:** #1929 (draft)
- **estado final:** esperando decisão do dono, PR draft #1929
- **início / fim:** 2026-10-19 / aguardando autorização material

## Entrega

O roteiro completo está em `docs/runbooks/ifood-catalog-test-rehearsal.md`. Ele cobre baseline,
pausa, retomada, preço, alterações rápidas, descrição, categoria, foto, confirmação por leitura e
restauração integral. Nenhuma chamada externa foi executada.

## Bloqueio

Para rodar o ensaio, o dono precisa:

1. confirmar o UUID do merchant de teste que entra em
   `SHOPMAN_IFOOD_CATALOG_WRITE_POLICY.merchant_allowlist`;
2. digitar `client_id` e `client_secret` no ambiente isolado do ensaio;
3. liberar um item de teste e uma categoria de teste.

Sem os três pontos, a frente permanece corretamente bloqueada. Nenhuma credencial deve ser escrita
no PR, documento, teste ou repositório.
