# ROADMAP — Django Shopman

> Atualizado em 2026-09-29. Este documento registra prioridades e direção.
> Arquitetura existente fica em [status](status.md); a única fonte de estado de
> go-live é a
> [matriz canônica de prontidão](plans/GO-LIVE-READINESS-PLAN.md).

## Prioridade imediata

| Prioridade | Resultado | Fonte / owner |
|---|---|---|
| P0 | Fechar os gates humanos de domínio, fases, escopo v1 e GO/NO-GO sem inferir aprovação a partir de CI | [Matriz canônica](plans/GO-LIVE-READINESS-PLAN.md) · owner comercial |
| P0 | Produzir evidência externa sanitizada: gateways, fiscal, QA física, backup/PITR e restore | [Pré-flight](runbooks/go-live-preflight.md) · owners na matriz |
| P0 | Executar cutover apenas depois de autorização contextual e evidência completa | [Cutover](runbooks/go-live-cutover.md) · incident commander |
| P1 | Resolver hardening humano de Admin/operadores (2FA, recuperação e ingress aprovado) | [Operator security](guides/operator-security-hardening.md) |
| P1 | Validar impressão e operação física em equipamento real | [Matriz canônica](plans/GO-LIVE-READINESS-PLAN.md) |
| P1 | Definir inclusão comercial de iFood, ManyChat/Concierge, Machine, fiscal e Marketing | [Matriz de credenciais](plans/GO-LIVE-CREDENTIALS-MATRIX.md) · owner de produto |

## Depois da decisão de lançamento

| Frente | Direção |
|---|---|
| Fiscal | concluir NF-e mod. 55 e validação do contador em janela própria |
| Compras | avançar as fases posteriores a recebimento e reposição sem misturar com o corte |
| Operação | fechar QA de dispositivo, impressão, gaveta, som e rede degradada |
| Marketing | promover provider por shadow/canário com consentimento e reconciliação |
| Dados | definir storage persistente para uploads antes de depender de filesystem de container |
| Plataforma | ensaiar restore e registrar RTO/RPO reais antes de afirmar recuperabilidade |

## Direção de produto

Os itens abaixo são intenção, não compromisso de release:

- Hub cross-channel e feeds de catálogo;
- Concierge de WhatsApp com ferramentas determinísticas;
- POS offline-first, tela do cliente e split por item;
- tempo de forno como fato de servidor;
- telas passivas e menuboard;
- evolução de B.I., previsão e operação de compras.

Os planos detalhados e seu ciclo de vida ficam no
[índice de planos](plans/README.md). Nenhum item desta seção entra no escopo v1
sem decisão explícita registrada na matriz canônica.

## Regra de conclusão

Um gate técnico verde demonstra somente o contrato que executou. Lançamento
comercial exige, cumulativamente:

1. commit candidato e deployment técnico identificados;
2. migrations e runtime prontos no ambiente alvo;
3. integrações necessárias exercidas no nível exigido;
4. QA física e recuperação verificadas;
5. escopo, domínio e fases aprovados pelo owner;
6. decisão GO/NO-GO registrada no momento do corte.
