# WP — Reconstrução da verdade documental canônica de Go-live

- **Status:** pronto para execução autônoma até os checkpoints humanos declarados
- **Data-base da auditoria:** 2026-09-28
- **Objetivo:** eliminar instruções contraditórias e fazer cada documento responder uma única pergunta, com data, ambiente e evidência verificáveis.

## 1. Problema confirmado

- `docs/status.md` descreve deploy de código como manual, enquanto a esteira atual publica imagens no push de `main`, acompanha a troca de contêineres e roda smoke pós-deploy.
- `docs/status.md` declara Django `>=6.0,<6.1`; o `pyproject.toml` atual exige `>=6.1,<6.2`.
- `GO-LIVE-READINESS-PLAN` ainda afirma que a execução não começou e usa uma auditoria de junho.
- Documentos diferentes descrevem Machine como inexistente e construída.
- Credencial presente, integração configurada e integração exercida aparecem misturadas.
- Contagens históricas de testes parecem estado corrente.
- O domínio vivo de pré-go-live pode ser confundido com produção comercial aprovada.

## 2. Arquivos prioritários

- `docs/status.md`
- `docs/ROADMAP.md`
- `docs/plans/GO-LIVE-READINESS-PLAN.md`
- `docs/plans/GO-LIVE-CREDENTIALS-MATRIX.md`
- `docs/runbooks/go-live-preflight.md`
- `docs/runbooks/go-live-cutover.md`
- `docs/runbooks/rollback-de-deploy.md`
- `docs/runbooks/README.md`
- `docs/reference/runtime-dependencies.md`
- `docs/guides/deploy.md`
- `.env.example`

## 3. Modelo de autoridade

- `docs/status.md`: arquitetura e capacidades existentes, sem checklist de corte.
- `GO-LIVE-READINESS-PLAN`: estado corrente dos critérios, owners e bloqueios.
- `GO-LIVE-CREDENTIALS-MATRIX`: significado e escopo das variáveis; não afirma existência sem inspeção datada.
- `go-live-preflight`: verificações antes do corte, sem cronologia extensa.
- `go-live-cutover`: sequência operacional do dia D.
- `rollback-de-deploy`: resposta a incidente.
- `runtime-dependencies` e `pyproject.toml`: compatibilidade; o arquivo executável é a autoridade.
- Reports: história e evidência de uma data; nunca procedimento operacional vigente.

## 4. Estados permitidos

Toda afirmação operacional deve conter, diretamente ou por referência canônica:

- `verificado_em`;
- ambiente;
- fonte/evidência;
- owner;
- próximo evento;
- estado entre `VERIFICADO`, `PENDENTE`, `BLOQUEADO`, `DESCONHECIDO` e `N/A`.

Ausência de acesso ou evidência vira `DESCONHECIDO`, não suposição otimista.

## 5. B1 — Coleta da verdade

Usar somente fontes verificáveis:

1. SHA atual da `main` e tag `go-live-v1`.
2. Workflows, checks e proteção do branch.
3. Makefile, `pyproject.toml`, lockfiles e registry de superfícies.
4. Últimos Deploy Images e Pre-go-live Smoke.
5. Spec vivo da DigitalOcean em leitura, com secrets sempre redigidos.
6. Nomes e tipos das variáveis, nunca valores.
7. Estado real das migrations e política ADR-015.
8. Estado dos gateways por probes seguros e não mutantes.
9. Evidências de QA com data, aparelho e ambiente.
10. Estado de backups/PITR e último ensaio de restore.

## 6. B2 — Correções obrigatórias

1. Descrever corretamente o fluxo atual de publicação, deployment e smoke.
2. Alinhar a versão de Django ao `pyproject.toml`, ou apontar para a mudança de dependência que a corrigirá.
3. Substituir “execução não iniciada” por uma matriz atual de concluído, pendente e bloqueado.
4. Recalcular contagens de testes ou rotulá-las como históricas com data.
5. Resolver a contradição Machine inexistente/construída.
6. Separar claramente:
   - credencial declarada;
   - adapter configurado;
   - boot gate aprovado;
   - integração exercida em sandbox;
   - integração exercida em produção.
7. Identificar `www.nelsonboulangerie.com.br` pelo ambiente que efetivamente representa, sem inferir aprovação comercial.
8. Definir sem ambiguidade alpha, beta, soft launch, produção técnica e lançamento oficial.
9. Atualizar o estado de migration reset/squash e o trigger real da ADR-015.
10. Distinguir capacidade construída de item incluído no escopo v1.

## 7. B3 — Redução de duplicação

1. Mover cronologias longas e incidentes encerrados para reports históricos.
2. Manter nos runbooks apenas pré-condições, passos, rollback e evidência mínima.
3. Fazer documentos derivados apontarem para a matriz canônica, em vez de copiar valores.
4. Remover hosts, app IDs e comandos obsoletos ou marcá-los explicitamente como históricos.
5. Inserir banner “não usar para operação atual” em planos superseded que precisem permanecer.
6. Evitar repetir o mesmo status em três documentos; repetir somente o link à fonte canônica.

## 8. B4 — Trava automática de drift

Criar `scripts/check_canonical_docs.py` ou testes equivalentes para verificar:

- versão Django documentada contra `pyproject.toml`;
- nomes de workflows, targets e runbooks existentes;
- links internos;
- ausência das contradições conhecidas;
- data de auditoria obrigatória nas matrizes operacionais;
- ausência de segredo literal;
- ausência de hosts antigos proibidos;
- descrição da tag e da ADR-015 compatível com a implementação;
- presença de owner/próximo evento em todo bloqueio.

O WP de CI faz o wiring bloqueante; este WP entrega conteúdo e teste.

## 9. Gates humanos

O executor deve parar e pedir confirmação quando faltar:

- nomenclatura oficial das fases;
- decisão sobre qual domínio é produção comercial;
- escopo v1 de iFood, ManyChat, Machine, fiscal ou Marketing;
- confirmação de uma credencial ou integração que não possa ser provada de forma segura;
- decisão de manter ou arquivar documento histórico.

Segredos nunca são solicitados no chat. O owner os insere no console apropriado; a documentação registra apenas o nome, tipo e prova sanitizada.

## 10. Validação

- Executar o novo verificador de drift.
- Validar todos os links locais.
- Comparar versões contra fontes executáveis.
- Revisar cada afirmação de ambiente contra evidência datada.
- Rodar busca por tokens, chaves, certificados e valores sensíveis.
- Revisão cruzada entre status, readiness, preflight, cutover e rollback.

## 11. Critérios de aceite

- Existe uma única matriz canônica de prontidão.
- Não há contradição de versão, deploy, migration ou integração.
- Todo bloqueio tem owner, evidência e próximo evento.
- Dados sensíveis estão ausentes.
- Links e doc-drift gate ficam verdes.
- Owner confirma domínio, fases e escopo v1.
- Documentos históricos estão claramente separados dos operacionais.
- Nenhum texto declara Go-live apenas com base em CI ou smoke superficial.
