# Protocolo preparado — piloto não iniciado

Fonte normativa: `docs/plans/ORDERS-OPERATIONAL-EXCELLENCE-PLAN-2026-09-10.md`,
§§6–11. Este documento é instrumento de coleta e decisão, não aprovação de T/P/R.
Nenhum operador, ambiente real, canal, fornecedor ou janela está autorizado aqui.

## Condições de entrada

WP09 deve apresentar aceite técnico antes de WP10. Na rodada922fb522c, os budgets
locais passaram com cinco leitores (backend p95451,290 ms em10 clientes; tela500
p951329 ms). Quatro leitores falham; topologia/rede reais não homologadas. Evidências
em performance_completion/README.md. Retomada pós-reload aguarda G05/G08, e demais
limites da matriz CURRENT-STATUS permanecem abertos; não se declara T.
Operações deve identificar 3–5 participantes representativos, ou toda a equipe se
menor, com papéis aprovados por G01. Não registrar seus dados pessoais nesta pasta.

| Gate | Decisão concreta a registrar | Evidência/impacto a revisar |
| --- | --- | --- |
| G01 | Papéis, responsáveis nominais, permissões e audiência/ack | Projeções e recusas por persona; não ampliar audiência sem decisão |
| G02 | Custódia, terminal/turno e responsáveis financeiros | Ensaios de dupla custódia/turno fechado; fato remoto não comprova dinheiro físico |
| G03 | Consulta homologada por fornecedor, owner e SLA de unknown | Crash de notificação deixa um aceite e nenhum replay; worker antigo é incompatível |
| G04 | Critérios de urgência e som | Preservar política atual até decisão; medir compreensão e carga de alertas |
| G05 | Publicação sensível e escopo de draft | Prévia exata, autorização por destino, sem persistência adicional implícita |
| G06 | Aparelhos, rede, personas, simultaneidade e budgets | Distribuições brutas; não alterar 500/800 ms ou 30% após resultado sem aprovação |
| G07 | Ambiente, capacidade, coorte, janela, suporte e parada | Restore populado e cliente antigo testados; drenar worker incompatível antes da capacidade |
| G08 antecipado | Retenção de contexto e trilhas | Draft em memória não promete retomada após reload; não apagar chaves |

Cada aprovação deve conter pessoa responsável, data, ambiente, versão, capacidade,
condições e referência à evidência. Campo vazio é pendência. Autorizar leitura não
autoriza courier/COD/publicação. Homologação não autoriza comunicação a clientes.

## Ensaio controlado pareado

Usar versões e dados sintéticos fixados, fakes externos isolados e livros canônicos.
Por participante, executar 10 pares por jornada crítica aplicável de J01–J15;
alternar antes/depois entre pares. Registrar a ordem real e todas as tentativas,
inclusive abandono, erro e preparação falha. Casos perigosos/raros são simulados.
Nunca induzir timeout, cancelamento ou pagamento em pedido real para este ensaio.

Para cada execução, preencher uma linha do CSV ao lado. A/N/R/M/X/T seguem §6.1:
ativações, navegações, redigitação de informação conhecida, fatos memorizados fora
da interface, recurso a outro aplicativo/suporte e tempo humano ativo. Digitação
legítima inicial não é R. Login, confirmação, segunda assinatura e entradas físicas
obrigatórias ficam separados para análise **e incluídos no total**. Registrar espera
remota separadamente; não remover abandono ou recuperação da distribuição.

Os quatro contadores draft/refresh ao final do CSV são observações explícitas:
restaurado sem redigitar, perdido, leitura stale observada e resposta descartada.
Deixar vazio quando não foi observado; zero só após verificar o cenário.
Conferir descarte de resposta com trace do ensaio, sem inferi-lo de uma tela igual.
São coleta supervisionada, não telemetria automática já instalada no produto.

No instante da falha, perguntar sem explicar antes: “O que ocorreu?”, “O que falta?”
e “Como continuar?”. Registrar resposta/classificação sem texto sensível. Exigir
≥95% de acerto e 100% nos casos de dinheiro, cancelamento e unknown. Qualquer erro
crítico bloqueia a capacidade; não compensar por média de jornadas fáceis.

Conferir antes/depois Order, eventos, recibo da intenção, Directive e livros
financeiros/estoque aplicáveis. Resposta perdida exige commit comprovado antes do
corte e consulta com a mesma chave. Concorrência exige duas sessões independentes;
falha parcial deve identificar o efeito faltante sem repetir o já aceito. Outro
operador autorizado deve retomar só pela interface/runbook, sem explicação oral.

Comparar distribuição completa e p50/p95 de T, recuperação agregada ≥30% menor,
R=0 nos dados conhecidos e nenhum passo extra em J01. Os números automatizados
existentes não preenchem T humano, clareza ou ganho em campo.

## Cinco turnos e expansão — somente após autorização

Após aprovação do ensaio controlado e G07 específico, observar no mínimo cinco
turnos completos incluindo abertura, pico e fechamento. Registrar por turno a
versão/coorte, responsáveis, recursos pendentes, conciliação, incidentes, suporte,
budgets e assinatura de Operações. Sem falso sucesso, duplicação, perda de draft
ou dinheiro sem origem. Uma pendência precisa de owner e próxima ação autorizada.

Um incidente crítico suspende novas mutações da capacidade afetada. Confirmar a
parada por ausência de novas mutações, preservando leitura, recibos, drafts e logs;
reconciliar comandos em voo antes de redirecionar tráfego. Meta proposta de parada
≤5 minutos depende de ensaio do ambiente em G07. Não retornar a worker antigo que
reenvia resultado desconhecido; manter capacidade suspensa até versão segura.
Usar o runbook existente `docs/runbooks/pedido-remoto-preso.md` e os artefatos
`restore_lab/` e `notification_unknown/`, sem editar payload de Order manualmente.

WP11 requer nova autorização por expansão e pelo menos pico/fechamento conciliado
em cada etapa. WP12 requer pelo menos sete dias e dois fechamentos após rollout
total, janela real de retorno e G08 de remoção. Nenhum desses períodos foi executado.

## Encerramento da coleta

Anexar CSV preenchido, distribuições, falhas, limites, reconciliação e assinaturas.
Não colocar nota de cliente, endereço, telefone, token ou cartão na coleta. Referências
de recursos ficam em trilha controlada, não em labels de métricas. Retenção depende
de G08. Esta preparação não tem migration; rollback documental não apaga evidência.

## Decisão de retenção apresentada — pendente

Proposta G05/G08: rascunhos e chaves na aba atual, retomados somente pela mesma
pessoa autenticada; limpar ao salvar, descartar ou fechar; sem PIN/senha e sem
compartilhamento entre aparelhos. Alternativa: memória e confirmação antes de
sair, mantendo retomada após reload pendente. Sem resposta registrada, a persistência
não foi implementada. Essa decisão não autoriza piloto ou efeitos reais.
