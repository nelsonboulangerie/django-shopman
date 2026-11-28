# Prompt de execução — Gestor de Pedidos

Texto para uma futura sessão de execução:

---

Leia integralmente e execute o plano:
`docs/plans/ORDERS-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md`.

O plano contém o escopo, as evidências, os contratos, as dependências, os budgets, os testes, os gates humanos e a Definition of Done. Siga esses critérios sem substituí-los por este prompt.

Se o plano não estiver no checkout, encontre-o em `/Users/pablovalentini/Dev/Claude/django-shopman-orders-plan`, branch `codex/orders-operational-excellence-plan`. Transporte somente os documentos necessários para um **novo worktree e branch `codex/` isolados**. Preserve mudanças de terceiros.

Antes de implementar, leia as instruções locais e as referências indicadas na seção 2, confira sua proveniência e compare o código atual com a base auditada do plano. Revalide os achados: defeito corrigido vira proteção de regressão; hipótese exige prova; decisão humana permanece pendente. Não copie diagnósticos antigos nem recrie soluções maduras, regras, superfícies ou fontes de verdade.

Execute os work packages conforme o DAG, com mudanças mínimas e commits revisáveis. Para cada pacote, registre evidência anterior, implementação, testes, resultado, migração e rollback. Use ambientes e adaptadores isolados; reporte falhas de preparação, skips e limites dos ensaios.

Faça de **omotenashi** o critério de aceite: antecipar necessidades, eliminar memória e redigitação, preservar contexto e oferecer a próxima ação autorizada no recurso certo. Demonstre os budgets e as jornadas antes/depois, incluindo concorrência, resposta perdida e falha parcial. Não suprima confirmações ou permissões para reduzir esforço.

Este mandato autoriza implementação técnica, testes e preparação do piloto. **Não autoriza produção nem efeitos reais**: deploy, reconciliação de dados reais, comunicação externa, despacho, emissão fiscal ou movimentação financeira exigem autorização específica. Ao alcançar um gate, apresente a decisão concreta com evidências e impacto; suspenda apenas o trabalho dependente e continue os pacotes independentes autorizados. Silêncio não é aprovação.

Entregue o estado dos pacotes, commits, testes efetivamente executados, comparação de esforço, migração/rollback e gates pendentes. Distinga **implementação técnica, piloto e rollout** conforme a DoD. Só declare a fase concluída com sua evidência; teste local não comprova ganho em campo.
