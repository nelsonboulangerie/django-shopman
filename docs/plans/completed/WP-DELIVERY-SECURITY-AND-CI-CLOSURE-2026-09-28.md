# WP — Fechamento de supply chain, segurança e gates de release

- **Status:** pronto para execução autônoma até os checkpoints humanos declarados
- **Data-base da auditoria:** 2026-09-28
- **Objetivo:** eliminar os alertas de dependência conhecidos e transformar segurança, cobertura, imagens agrupadas e contrato de produção em verificações contínuas e bloqueantes, sem permitir que CI sintética toque provedores reais.

## 1. Estado inicial comprovado

- 10 alertas Dependabot `medium`: `undici` em nove superfícies e `devalue` no BI.
- PR #1193 falha em oito jobs frontend/imagem; PR #1190 falha praticamente todo o backend.
- Code scanning responde `404 no analysis found`; não existe evidência de SAST ativo.
- Secret scanning não apresenta alerta aberto, mas push protection não foi comprovada.
- `coverage.fail_under = 75` existe no `pyproject.toml`, porém cobertura não bloqueia merge.
- `production-readiness` existe no Makefile, mas não roda no CI.
- `Operator Groups Gate` não é required porque usa filtro de paths.
- A proteção da `main` exige 23 checks, mas não exige review nem resolução de conversas e usa `strict=false`.

## 2. Princípios e limites

- Atualização de dependência deve ser mínima, reproduzível e explicada por advisory.
- CI de PR nunca recebe credenciais reais nem chama pagamento, fiscal, mensageria, logística ou marketplace.
- Ausência de análise não equivale a zero vulnerabilidade.
- Threshold não é reduzido para deixar um gate verde.
- Settings externos do GitHub exigem checkpoint humano; o WP entrega a proposta e a evidência antes de aplicá-los.
- Nenhum alerta pode ser ignorado sem owner, justificativa e prazo.

## 3. A1 — Remediação mínima das dependências

1. Consultar novamente os alertas no início e registrar pacote, manifest, advisory, versão atual e `first_patched_version`.
2. Abandonar agrupamento amplo quando trouxer upgrades sem relação com os advisories.
3. Atualizar apenas:
   - `undici` ou a cadeia transitiva que o instala nas superfícies afetadas;
   - `devalue` ou a cadeia transitiva correspondente no BI;
   - dependências estritamente necessárias para resolver os lockfiles.
4. Regenerar lockfiles com scripts desabilitados quando possível e revisar toda mudança de resolução.
5. Para cada surface afetada, executar:
   - `npm ci`;
   - `npm test`;
   - `npm run lint`;
   - `npm run typecheck`;
   - `npm run build`;
   - `npm audit --audit-level=high`.
6. Executar integralmente o Surfaces Gate e o Operator Groups Gate.
7. Confirmar pela API do GitHub que os dez alertas fecharam ou registrar advisory sem patch aplicável.
8. Fechar PRs Dependabot substituídos com referência ao PR consolidado.

### Proibições

- Não usar `npm audit fix --force`.
- Não fazer major upgrade apenas para “limpar tudo”.
- Não reduzir nem pular gate existente.
- Não aceitar lockfile alterado sem explicar sua origem.

## 4. A2 — Security Gate e SAST

1. Adicionar workflow CodeQL para Python e JavaScript/TypeScript em:
   - pull request;
   - merge group;
   - `main`;
   - agenda semanal.
2. Fixar permissões mínimas: `contents: read` e `security-events: write`.
3. Executar a primeira análise como baseline não obrigatória.
4. Classificar os achados como correção, falso positivo documentado ou risco aceito com owner e prazo.
5. Criar job agregador estável, por exemplo `Security Gate`, sempre presente.
6. Torná-lo candidato a required apenas depois de dois runs verdes consecutivos na árvore integrada.
7. Verificar o estado de secret scanning e push protection sem expor valores.

### Gate humano A2

Habilitar Code Security/CodeQL, push protection ou alterar settings do repositório pode exigir owner, licença ou impacto operacional. O executor deve preparar workflow, evidência e comando/API exato, mas parar antes da mudança externa sem autorização explícita.

## 5. A3 — Cobertura bloqueante

1. Medir a cobertura real da `main` sem mudar o threshold.
2. Preservar `fail_under=75`.
3. Preferir coleta de `.coverage.*` nos shards já existentes, upload de artifacts e combinação em job agregador; evitar executar novamente a suíte inteira.
4. O agregador deve:
   - falhar abaixo de 75%;
   - publicar sumário e XML;
   - reprovar se faltar artifact de qualquer shard;
   - reprovar se a combinação estiver vazia ou incompleta.
5. Se o baseline estiver abaixo de 75%, não baixar o piso. Manter o resultado visível, nomear módulos responsáveis e completar testes antes de propor o check como required.

## 6. A4 — Contrato de produção no CI

Separar duas perguntas:

- **Contrato hermético:** configuração sintética de produção, sem rede externa e sem dados reais.
- **Prontidão viva:** credenciais, provedores e banco reais; pertence ao WP de cutover comercial.

Entregáveis:

1. Criar `make production-contract` ou opção equivalente que valide:
   - `DJANGO_DEBUG=false`;
   - hosts, cookies, CSRF e domínios;
   - Postgres e Redis obrigatórios por contrato;
   - ausência de flags de mock, debug e autopilot;
   - adapters de produção configurados por classe;
   - `check --deploy`;
   - migration safety;
   - zero chamada externa.
2. Rodar o contrato em pull request e merge group com segredos falsos estruturais.
3. Manter `production-readiness` real fora do CI comum.
4. Criar teste que falhe se o contrato sintético passar a chamar provider externo.

## 7. A5 — Required checks e governança

1. Criar agregador sempre presente para Operator Groups:
   - fora dos paths relevantes, resultado validado como `not applicable`;
   - nos paths relevantes, router e as duas imagens precisam ficar verdes.
2. Criar nomes estáveis:
   - `Security Gate`;
   - `Coverage Gate`;
   - `Production Contract`;
   - `Operator Groups Contract`.
3. Executar todos na merge queue antes de alterar proteção.
4. Preparar proposta de branch protection para:
   - adicionar os quatro checks;
   - avaliar `strict=true`;
   - exigir conversation resolution;
   - exigir ao menos uma revisão somente se houver revisor humano sustentável.
5. Não aplicar settings do GitHub automaticamente.

### Gate humano A5

Apresentar o diff completo de proteção, impacto esperado e runs verdes. A alteração só ocorre após autorização do owner.

## 8. Validação

- Testes unitários específicos das mudanças.
- Full Runtime Gate, Surfaces Gate, Omotenashi Gate e Operator Groups Gate.
- Merge-group dry run com nomes finais dos checks.
- Consulta Dependabot antes/depois.
- CodeQL nas duas linguagens.
- Cobertura combinada com todos os shards.
- Teste negativo do Production Contract com cada flag proibida.

## 9. Critérios de aceite

- Zero alertas `medium` conhecidos, ou exceções documentadas com prazo e owner.
- CodeQL produz análise válida para Python e JavaScript/TypeScript.
- Cobertura combinada é pelo menos 75%, sem shard ausente.
- Production Contract falha com qualquer affordance de teste.
- Nenhum teste do contrato faz chamada externa.
- Todos os novos checks passam em PR e merge group.
- Proteção só é alterada após aprovação humana.
- PRs Dependabot substituídos são encerrados com rastreabilidade.

## 10. Evidência

Publicar artifact sanitizado contendo:

- alertas antes/depois;
- matriz de versões;
- hashes dos lockfiles;
- URLs/IDs dos runs;
- relatório de cobertura;
- SHA testado;
- proposta de branch protection.

Tokens, secrets, certificados e payloads pessoais nunca entram no artifact ou no log.
