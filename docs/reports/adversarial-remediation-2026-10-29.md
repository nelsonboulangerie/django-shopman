# Revisão factual da avaliação de 22/10

A avaliação original está preservada no branch `origin/dsh/avaliacao-repositorio-20261022`, arquivo `docs/reports/2026-10-22-avaliacao-repositorio-shopman.md`. Esta revisão corrige as conclusões que dirigem trabalho, sem repetir a nota numérica sem rubrica verificável.

## Cobertura

O workflow `.github/workflows/runtime-gate.yml` já combina cinco artefatos e aplica `coverage report --fail-under=75`. O zero nos shards permite medir partes da suíte; não desliga o piso agregado. A medição isolada do Offerman não representa esse contrato, que mede `shopman`.

A consulta à API de proteção de `main` em 29/10 confirmou a fragilidade real: `Coverage Gate` não era obrigatório. Esta alteração acrescenta o contexto ao espelho e à proteção remota, preservando os demais checks e seus app IDs. O job existe em `pull_request` e `merge_group`.

Verificação reproduzível: `python3 scripts/check_canonical_docs.py --live-required-checks`. O comentário de `make test` em `CLAUDE.md` deixa de declarar uma contagem estática já obsoleta.

## Limites e trabalho restante

Tamanho de módulo e quantidade de exceções são sinais para investigação, sem demonstrar falha ou ausência de testes úteis. Não justificam refatoração ampla antes do go-live sem identificar dependências, efeitos e invariantes. Formatação em massa também criaria conflitos nas frentes ativas.

Contagens de documentação, testes, branches e worktrees não provam qualidade ou abandono. Integrações opcionais entre kernels precisam ser distinguidas do núcleo independente. CSP, OTP e confiança de dispositivo demonstram controles presentes; a comparação de segurança com o mercado não apresentou evidência.

A triagem de trabalho dormente e de dependências é coordenada na frente global de go-live. As atualizações maiores de dependências permanecem sujeitas aos checks e à decisão de freeze existente; este relatório não as aprova por contagem ou idade.
