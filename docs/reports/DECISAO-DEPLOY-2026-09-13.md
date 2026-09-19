# Decisão de publicação — 13/09/2026

## Restrição iFood — instrução de Pablo em 14/09/2026

Os produtos locais são exemplos ainda não revisados; o catálogo iFood real pode estar mais correto, inclusive fotos. Não tratar dados locais como fonte de verdade na reconciliação.

Nenhuma escrita ou atualização no iFood real está autorizada sem revisão prévia de Pablo sobre as alterações concretas. Isso abrange preço, pausa, categoria, foto, descrição e sincronizações automáticas acionadas por deploy, configuração ou edição local. Aprovação de PR não autoriza envio real.

Leitura/comparação e desenvolvimento isolado podem continuar. Na revisão de merge/deploy, inclusive das PRs #640, #649, #660, #661 e #662, verificar efeitos indiretos e preservar a ausência de publicação automática no iFood. Se a entrega puder provocar escrita remota, separar/desabilitar esse caminho e apresentar o diff remoto concreto para revisão antes de habilitá-lo.

## Resultado confirmado após retomada

PR #631 integrado pela merge queue em `c24a9ca73c51013e5adda00803fde2edc57cdbc4`; três gates da fila aprovados. Deploy Images `34797438855` concluiu com sucesso para as sete superfícies. Deployment `03f1b682-3fd0-4f05-9025-69fb477d3057` ACTIVE, 47/47 etapas, sem outro deployment em andamento. O gate de correlação da imagem do run com o deployment passou.

Health, ready, menu, PDV, Gestor e readiness Marketing responderam HTTP 200. Manifesto publicado em `output/coordination-20260913/pr631-published/published.json`; consultas HTTP em `output/coordination-20260913/pr631-health.json`.

Smoke `34797592455` falhou no mesmo problema anterior à atualização: 43 SKUs, 8 disponíveis, mínimo exigido de 10. Não declarar smoke completo aprovado. A frente B15 do laudo tratará o contrato canônico; nenhum piso foi reduzido e nenhum produto foi ativado nesta execução.

Dependabot fechou os 31 alertas tratados pelo #631. Restam cinco no Storefront (#336, #335, #314, #309, #300); Marketing recebeu a extração das correções de dependências do draft #614 para PR técnico separado.

Liberada publicação dos PRs do laudo por ondas após rebase local dos 19 heads sobre a nova main. Merges/deploys continuam centralizados e dependem dos gates remotos. Seção C permanece adiada. Os relatos abaixo documentam estados históricos anteriores, superados por este resultado.

## Retomada após ajuste das permissões

O arquivo do projeto foi alterado por Pablo para `approval_policy = "on-request"`. Na retomada, a comunicação entre sessões e a chamada ao GitHub voltaram a funcionar. O GitHub recusou merge direto por exigir merge queue; a regra foi respeitada, colocando #631 na fila com head esperado `95eb6e796fa746c30aa0ba759b5a861172c71c20`.

Grupo de integração: `c24a9ca73c51013e5adda00803fde2edc57cdbc4`. Runs: Runtime `34796673500`, Surfaces `34796673502`, Omotenashi `34796673491`. Status nesta atualização: aguardando os checks da fila; ainda sem deploy novo confirmado.

Marketing retomou apenas implementação técnica de maioridade (L3), e a frente do laudo retomou apenas aplicação local dos patches. Ambas receberam instrução de não fazer merge/deploy concorrente. Os bloqueios de ferramenta descritos abaixo são histórico anterior a esta retomada.

## Recomendação

Publicar em etapas. O PR #631 é o primeiro candidato técnico revisado nesta rodada. O lote funcional do laudo ainda requer CI remoto após os patches locais. Não aguardar integrações opcionais para entregar correções prontas, nem promover staging para produção comercial nesta etapa.

## PR #631

- Head confirmado: `95eb6e796fa746c30aa0ba759b5a861172c71c20`, aberto e sem conflito.
- Runtime Gate, Surfaces Gate e Omotenashi Gate: sucesso para esse head, reconsultados nesta rodada.
- Reviews e review threads: listas vazias. Não há aprovação independente registrada nem pedido de alteração registrado.
- Diff revisado: 14 arquivos, apenas `package.json` e `package-lock.json` de BI, Hub, KDS, Pedidos, PDV, Produção e Compras; nenhuma migration, regra comercial, segredo ou configuração de provider.
- Integração simulada sobre `main f8658f374bed04dafba1ed048cd443121f557924` sem conflitos; árvore resultante `ee57d00319bc813ca7d5ad7f4cfaeba0ab3fd507`.
- `npm audit --package-lock-only --ignore-scripts` executado nos sete locks resultantes: zero vulnerabilidades reportadas em todos eles. A consulta não instalou pacotes nem executou scripts. Isso não equivale a declarar todo o sistema livre de vulnerabilidades.
- [Resultados da auditoria](../../output/coordination-20260913/pr631-audit.json).
- [Referências de imagens para rollback](../../output/coordination-20260913/pr631-rollback.json): sete digests atuais do registry, capturados antes da tentativa.

Deploy esperado: rebuild das sete superfícies afetadas pelo fluxo automático após merge. Backend, migrations e ativação comercial não pertencem ao diff. Depois da publicação é necessário confirmar digests/versões das superfícies e executar o smoke pertinente.

O default branch ainda não recebeu essas correções nesta execução. Não declarar o gate L8 encerrado: o #614 contém a parcela Storefront e o fechamento exige recontagem no main após integração.

## Tentativa e bloqueio

Usada a autorização prévia de Pablo para publicar entregas tecnicamente seguras. A chamada de merge do #631 informou explicitamente o head esperado, sem opção de bypass de proteção.

A ferramenta recusou a chamada antes da execução: `MCP tool call requires approval, but approval policy is never`.

**Nenhum merge nem deploy foi realizado.** A ação não foi tentada por caminho alternativo. Revalidar PR/head/CI e ausência de deploy concorrente quando a política permitir apresentar a aprovação.

## Demais candidatos

| Pacote | Decisão |
|---|---|
| SQL / Maps / lote funcional do laudo | Prioritário após publicar branches e obter CI remoto nos commits corrigidos; 791 testes locais aprovados não substituem esse gate |
| #613 | Remoto continua com Runtime Gate vermelho; patch local ainda não incorporado |
| #614 | Continua draft; CI verde não conclui L1/L3/L7 nem autoriza descarte real de dados |
| #634 | CI verde e sem conflito, mas possui migração/novo adapter; revisar e publicar em etapa separada mantendo TikTok desligado |
| Seção C / produção comercial | Continua adiada conforme histórico; não é pré-requisito para atualizar tecnicamente o staging |

O deployment observado antes da tentativa continuava `d3bd232b-6eb6-4676-a87f-f002800282da`, ACTIVE, 47/47 etapas, sem deployment em andamento. Não há justificativa para republicar simplesmente a imagem antiga sem incorporar código novo.
