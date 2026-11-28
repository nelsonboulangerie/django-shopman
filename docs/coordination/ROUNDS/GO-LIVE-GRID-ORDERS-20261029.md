# Catálogo e ordens locais: reconciliação de 29/10/2026

## Código do tabelão

Os seis arquivos modificados no checkout principal pertencem à correção já entregue pela PR #1980, commit `6a960e3cb490f4500f284dd48debd12ec2524631` (21/10). A PR descreve os mesmos três comportamentos: vírgula decimal na colagem, preservação de rascunho e marcação das células com falha, fechamento apenas após aplicação integral.

O parser local `surfaces/operator-kit/app/presentation/gridEdit.ts` é idêntico ao de `origin/main`. Os cinco demais arquivos são versões anteriores da implementação entregue: o main inclui o teste de desfazer após confirmação parcial, os `base_revisions` esperados no teste do componente, ajuste de tipagem dos campos conflitantes e `NuxtAlert` canônico. Também há melhorias posteriores em `useCatalogMatrix.ts` e `catalog.vue`. Copiar os arquivos locais inteiros de volta retiraria essas melhorias.

Não há comportamento útil inédito a recuperar nesse conjunto. Não foi aplicado patch, iniciado novo desenho de UX ou removido qualquer original.

## As sete ordens locais

| Arquivo não rastreado | Resultado |
|---|---|
| `next.md` | Vazio. Nenhuma instrução perdida. |
| `next-6.md` | Cópia exata de `ORDERS/2026-10-19-frente6-ifood.md`. |
| `next-arquivar.md` | Cópia exata de `ORDERS/2026-10-19-arquivar.md`. |
| `next-claude.md` | Retomada ManyChat antiga. A ligação da encomenda foi entregue pela #1956. As demais necessidades de modelos e flows permanecem na coordenação atual e não são autorizadas por este arquivo antigo. |
| `next-consertos.md` | Correções de foto/categorias/arquivamento e resolvedor. #1905, #1931 e #1948 mergeados; resolvedor entregue pela #1951. |
| `next-ensaio.md` | Ensaio iFood já encerrado pelas #1962/#1965; prova complementar na #1966. Não repetir escritas remotas. |
| `next-onda4.md` | Todas as seis frentes e os dois seguimentos entregues. Conferência em [ONDA4-ENCERRAMENTO](ONDA4-ENCERRAMENTO.md). |

As quatro ordens únicas foram preservadas integralmente como [evidência histórica](../EVIDENCE/20261029-local-orders-archive/README.md), fora do canal de ordens ativas. Seus hashes permitem reproduzir a comparação. Os sete originais continuam no checkout principal.

## Verificação e estado

- Comparação do diff local com `origin/main`, do commit `6a960e3cb` e do corpo da PR #1980.
- `git log origin/main` confirma as entregas citadas; os registros de encerramento preservam as evidências de execução.
- Nenhum teste funcional foi repetido: a entrega desta triagem altera somente documentação e arquiva instruções históricas; não muda código.
- PR #2042 publicada e encaminhada à fila. Não resta trabalho útil inédito nos seis arquivos de código nem instrução única sem preservação nas sete ordens examinadas. Isso não declara encerradas as pendências operacionais ManyChat do BOARD.
