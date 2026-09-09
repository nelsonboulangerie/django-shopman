# Marketing capacity gate

O gate do MKT-043 prova o pico acordado mais a margem de 2× sem elevar o limite
operacional, sem internet e sem executar adapter de provider. Ele cria somente o banco
descartável do pytest e o remove ao final.

Execute na raiz de uma worktree isolada:

```console
make marketing-capacity
```

Não é preciso lembrar flags, paths de pacote ou settings, e os logs de correlação em
volume ficam silenciados somente na apresentação do teste. A saída traz duas linhas JSON
copiáveis, `MARKETING_CAPACITY_AUDIENCE` e `MARKETING_CAPACITY_WORKERS`, seguidas do
resultado do pytest.

## Contratos que não podem ser afrouxados

| Fluxo | Fixture | Budget/gate |
|---|---:|---:|
| Audience | 100.000 elegíveis em 200.000 candidatos | p95 ≤ 2 s; ≤ 30 queries; ≤ 256 MiB |
| Fan-out | 20.000 targets em 4 commands legais | 5.000 por command; chunk 100; conclusão de cada lane ≤ 10 s |
| Claims | 2 workers sobre o mesmo backlog | 100 por worker; ≤ 10 queries; ≤ 1 s; interseção zero |

O teste nunca muda `MAX_TARGETS_PER_COMMAND=5_000`: o pico usa quatro commands válidos.
Ele para em `claim_due_targets`; não chama `execute_target`, ManyChat ou qualquer outro
boundary externo.

Os testes pequenos do mesmo arquivo rodam na suíte comum e guardam os planos indexados e
a reversibilidade da migration. O teste volumétrico só é habilitado pelo alvo acima para
não esconder uma execução cara no feedback cotidiano.

## Como interpretar uma falha

- Latência acima de 2 s: não aumente o budget; compare query count, plano de índice e
  materializações intermediárias.
- Queries acima de 30: procure N+1 ou batches menores que 20.000. Nunca substitua a busca
  de coorte por `get_marketable_customers()`, que varre todos os consentimentos.
- Workers com sobreposição: trate como falha de fencing/lease e não execute provider.
- Mais de 5.000 por command: o harness está furando o safety cap; corrija o harness.
- Plano sem `customer_ins_*_idx`: migration/índice não foi aplicado; não prossiga ao
  piloto.

Esta medição local é evidência de engenharia, não o baseline autorizado de 7–14 dias e
não fecha G-H08. Capacidade da instância real, nomes do on-call, paging e canary continuam
dependendo de autorização humana antes do piloto.
