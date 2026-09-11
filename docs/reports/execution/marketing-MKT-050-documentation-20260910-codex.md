# MKT-050 — documentação factual vinculada ao HEAD

**Estado:** concluído na branch isolada

**Última verificação:** 2026-09-10

**Efeito externo:** nenhum

## Resultado

A documentação operacional, de arquitetura, superfície, contratos e deploy do
Marketing passou a refletir a implementação corrente. O contrato canônico está em
[`docs/reference/marketing-surface-contract.md`](../../reference/marketing-surface-contract.md)
e declara ownership, semântica dos canais, rotas, projeção gerada, capacidades, flags,
gates e estado real de rollout.

O `marketing-nuxt` permanece o único cockpit. Admin/Unfold é somente auditoria
agregada. Instagram, Facebook e Google Meu Negócio representam publicação pública;
WhatsApp representa entrega direta por pessoa elegível. Mensagem direta no Instagram
continua fora do contrato atual.

## Deriva encontrada e corrigida

O blueprint de subdomínios usado para produção ainda verificava a raiz `/` do serviço
Marketing. O serviço expõe probes separados, portanto o spec passou a usar
`/health/ready` para readiness e `/health/live` para liveness, igual ao blueprint alpha.
Nenhum outro serviço, segredo ou configuração viva foi alterado.

Também foram corrigidos inventários desatualizados de superfícies, portas e apps,
descrições antigas do design system e lacunas de documentação sobre rollback, WhatsApp
transacional, projection v2, comandos de diagnóstico e configuração segura.

## Gate contra nova deriva

`scripts/check_marketing_docs.py`, exposto por `make marketing-docs` e pelo workflow
`runtime-gate.yml`, compara:

- as seis rotas Nuxt com os arquivos reais em `surfaces/marketing-nuxt/app/pages`;
- as 31 rotas Django com `shopman/backstage/api/urls.py`;
- os blocos de rotas no README e no contrato canônico;
- readiness e liveness dos dois blueprints DigitalOcean.

`CLAUDE.md` aponta para o contrato factual e registra a decisão do envelope de segurança
para que outras sessões não enfraqueçam o Marketing nem copiem a política para outros
apps sem inventário e testes próprios.

## Provas locais finais

- `make marketing-docs`: **6 rotas Nuxt, 31 rotas Django e 2 specs de deploy**;
- `manage.py export_marketing_client --check`: projeção, OpenAPI e cliente sem deriva;
- testes focados de deploy/client: **9 passed**;
- contratos de segurança Marketing: **2 arquivos / 4 testes**;
- typecheck do Marketing: verde;
- Ruff e compilação do novo checker: verdes;
- YAML dos dois blueprints e do workflow: válido;
- links Markdown dos documentos alterados: válidos;
- `git diff --check`: verde.

Não houve push, PR, merge, deploy, staging, alteração de ambiente, provider,
destinatário, envio real ou escrita externa.
