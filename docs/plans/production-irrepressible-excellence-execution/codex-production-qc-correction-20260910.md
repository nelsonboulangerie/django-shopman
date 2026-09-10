# Execução — confirmação imediata e correção pós-fechamento de QC

**Data:** 10 de setembro de 2026

**Worktree exclusivo:** `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-production-integration-20260909`

**Branch:** `codex/production-qc-correction-20260910`

**SHA-base:** `696f54105` (`origin/main`)

**Escopo:** corrigir a falsa impressão de clique duplo nos modais de Produção e implementar a correção gerencial, auditável e segura do QC de uma fornada concluída.

## Contrato fechado com o usuário

1. Os graus continuam sendo exatamente Ótimo, Normal (padrão), Razoável e Mínimo.
2. Grau e motivo são ortogonais. Grau governa preço/markdown e elegibilidade; motivo explica a divergência.
3. A partição admite vários graus na mesma fornada, mas cada grau aparece no máximo uma vez. Um mesmo grau com motivos diferentes não cria subpartições.
4. Razoável/Mínimo exigem um motivo principal. Perda é um único número com um único motivo, sem grau nem lote.
5. Canais remotos aceitam somente Ótimo/Normal; o PDV local pode consumir lotes com markdown conforme sua política congelada.
6. Na correção de QC, o rendimento físico é imutável: total produzido e total de perda não mudam. Corrigir rendimento exige outro fato de domínio.
7. A correção nunca apaga o fechamento original: cria evento, lotes e movimentos compensatórios versionados.
8. Comunicação de uma conclusão não é reemitida. Conteúdo ainda reversível e incompatível é substituído; conteúdo já enviado permanece como fato e gera impacto operacional explícito.
9. A permissão é gerencial. O gesto exige revisão otimista, prova assinada, chave idempotente e justificativa.

## Risco reproduzido

- Os POSTs observados continham um único request; a mutação já tinha trava de repetição. O modal, porém, continuava exibindo `Confirmar` durante o primeiro request. O primeiro toque funcionava e o segundo era ignorado, criando a impressão de que dois cliques eram necessários.
- O QC original era imutável de forma absoluta: não havia maneira segura de corrigir uma classificação posterior ao fechamento, apesar de estoque, disponibilidade, campanhas e BI dependerem dela.

## Implementação e invariantes

- Os modais de planejamento e início entram em estado síncrono `Confirmando…`, ficam desabilitados antes do `await` e recusam reentrada.
- Novo evento `quality_corrected`, permissão `backstage.correct_production_qc`, action projetada `correct_qc` e endpoint tipado de correção.
- A partição efetiva é o último evento de correção ou, na ausência dele, as linhas originais de OUTPUT/WASTE.
- Reclassificação comercial cria novos `Batch`/`Quant`, credita os lotes novos, reancora reservas compatíveis e debita os antigos na mesma transação. Lotes/itens originais permanecem intocados.
- Falha fechado quando o saldo já saiu, está distribuído entre posições, perdeu rastreabilidade ou uma reserva ativa ficaria incompatível.
- Reservas permissivas recebem primeiro o melhor grau compatível; reserva remota nunca é movida para Razoável/Mínimo.
- Leitores de QC, disponibilidade, espera, campanhas e BI usam a qualidade efetiva/congelada. O snapshot histórico de `DayClosing` não é reescrito.

## Evidências

Preencher ao fechar a rodada:

- [x] migrações sem deriva (`makemigrations --check --dry-run`) e grafo completo aplicado em banco vazio (`check-migrations: passed`, 3/3 provas aplicáveis);
- [x] 327 testes backend das suítes afetadas aprovados, 1 skip ambiental; o recorte integrado novo de QC/comunicações teve 17/17 aprovados;
- [x] contrato TypeScript regenerado pelo exportador canônico e seus 6 testes aprovados;
- [x] superfície Production: 31 arquivos/225 testes; ESLint, Ruff, `git diff --check` e typecheck com Node 22 aprovados;
- [x] revisão adversarial de permissão, retry concorrente, conservação, uma perda, lote imutável, reserva remota/local, anúncio pendente/fila/em execução/publicado e handler tardio;
- [x] `manage.py check --deploy` concluiu com sucesso; os avisos de adapter mock/Redis local e do schema são preexistentes ao diff;
- [x] gate da meia-correção aprovado para os 23 arquivos Python tocados; o import opcional de OfferMan recebeu justificativa explícita de silêncio deliberado;
- [ ] publicação autorizada e smoke test online.

Commits locais:

- `e5f20ff14` — slice vertical de correção pós-fechamento, interface, integrações, migrações e provas;
- `f5b7f2430` — declaração explícita do único silêncio opcional apontado pelo gate adversarial.

## Rollback

O código pode ser revertido sem apagar os fatos já gravados. Eventos `quality_corrected`, lotes versionados e movimentos compensatórios devem permanecer como auditoria; um rollback operacional de uma correção é uma nova correção para a partição anterior, nunca edição/destruição de histórico. A migração de permissão/status é backward-compatible.
