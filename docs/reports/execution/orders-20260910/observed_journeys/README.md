# WP08 — correlação durante jornadas integradas

Código ddd8f981a, Django/Daphne em 8014, Nitro em 3004, PostgreSQL próprio em
55439, Redis próprio em 56389. Seed sintético novo; nenhum fornecedor real.
`SHOPMAN_JSON_LOGS=1` usa JsonLogFormatter/operational_event existentes.
**25 cenários integrados passed (~1 minuto)**; build de produção local aprovado.
Roda junto de suíte ampla SQLite em checkout imutável: tempos não são benchmark
isolado e não substituem os ensaios de carga/latência com amostra definida G06.

`events.jsonl` contém somente allowlist de eventos operacionais da rodada
sintética. Cookies, corpo de request, texto digitado e logs gerais ficaram fora.
Refs/digests são para trilha controlada; não se tornam labels de métricas.
O sumarizador lê logs, não escreve banco nem introduz nova fonte de estado:

```
python summarize.py events.jsonl --cohort synthetic-integration --version ddd8f981a
python test_summary.py
```

Duas provas do sumarizador passaram: receipt não soma uma nova aplicação e dados
extras sensíveis não aparecem no agregado; aceite conclui apenas a tentativa
observada. Ruff aprovado. O JSON registrado foi gerado do log integral privado,
então non_json_lines inclui linhas de acesso/servidor (não são falhas de comando).
Regerar a partir da allowlist dá os mesmos indicadores, com non_json_lines=0.

Rodada: 17 comandos aplicados, 1 não aplicado, 9 leituras de receipt aplicado,
1 acerto de caixa. Os 25 HTTP403 incluem sondagens iniciais sem sessão/autorização
nos testes; não são todos falhas inesperadas da jornada. GET view p95 152,120ms,
POST view p95 191,794ms, PATCH view p95 96,915ms. View exclui render/transporte.
Nove consultas ao resultado seguiram seu commit: p95 do intervalo entre eventos
122,268ms; não é tempo humano de recuperação nem mede resposta percebida.
Uma tentativa de efeito ficou failed no log, portanto segue pendente observada;
não é sucesso nem desaparece com ack. Backlog canônico inteiro é outra consulta.

**Placar ainda parcial:** métricas de draft, descarte/staleness, mismatch de livros,
backlog canônico completo, compreensão e esforço em campo estão explicitamente
unmeasured. Ausência de evento não é zero. As provas de rascunho/leitura estão nos
cenários de navegador, mas não são contadores contínuos de produto. Runbook de
pedido remoto foi atualizado no caminho existente, com responsabilidade por
papel (nomes/SLA dependem G01/G03). Nenhum alerta pessoal/audiência novo foi criado.
Sem migration. Rollback do relatório apaga apenas artefatos derivados; preservar
logs/chaves/livros de acordo com G08, sem cleanup automático.
