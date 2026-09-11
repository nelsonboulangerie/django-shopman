# Maquininhas individuais — execução de 11/09

Plano: `docs/plans/ORDERS-DELIVERY-DEVICES-2026-09-11.md`, extensão transmitida
pela tarefa PDV com autorização de Pablo. Não autoriza publicação nem efeitos reais.
Fonte de implementação: c1063c850; teste de corrida reforçado em47e9c657a.
Resultados de desempenho abaixo são limites reais do ensaio, não autorização de capacidade.

## Implementação e integração

- c42296798: escopo/DAG e contrato de integração com PDV.
- 0c61d69ab: cadastro nativo Admin e migration aditiva backstage0061.
- 5d68d8646: alocação exclusiva e integração seletiva dos pagamentos de e3c1267a5.
- 6f0f38145: disponibilidade no Gestor, seleção no despacho e devolução independente.
- 6e1e6dd84: proteção do rollback populado, acesso pela Configuração e legado distinto.
- 3b9d8150d: KDS informa a próxima ação no Gestor antes de tentar despachar.
- c1063c850: adaptador shop→surface, seed sintético compatível e configuração preservada.
- 47e9c657a: duas conexões observam disponibilidade antes de competir pelo lock; filtro testa apenas cards.

Não houve cherry-pick da branch PDV inteira. Os arquivos de PDV/contrato e testes
foram integrados seletivamente; em operator_orders a integração preserva os locks,
revisões e recibos mais recentes do Gestor. A copy de pagamento em lote conserva o
cache por leitura. A UI do PDV continua pertencendo à tarefa PDV, não foi duplicada.

`DeliveryDevice` representa um aparelho físico (UUID estável, nome, identificação
única, ativa/inativa). `current_order` tem vínculo exclusivo no banco. O lock do
pedido precede o do aparelho; selecionar e vincular acontece na mesma transação
do despacho. A consulta de disponibilidade da UI não reserva nada. Admin não edita
custódia; salvar formulário antigo não sobrescreve um despacho concorrente.

`dispatch.equipment` conserva os tipos legados; device_ref/device_label são trilha
do despacho. Disponibilidade individual tem um único dono: a relação do aparelho.
Um registro antigo sem identificação não equivale a um aparelho físico identificado
nem é contado como tal. Não houve backfill presumindo qual maquininha saiu.

Order e Fulfillment têm barreira na transição ORM de despacho. KDS encaminha a
escolha ao Gestor; courier não aloca automaticamente ao receber o fato de coleta.
Testes cobrem as quatro entradas. SQL/bulk_update administrativo não é interface
operacional autorizada, assim como reconciliação manual de dados reais não foi feita.

Devolver não captura pagamento; acertar não devolve automaticamente. O checkbox
conjunto começa desmarcado e a devolução independente fica visível com pagamento
pendente. Cartão/misto seguem Payman; somente cash movimenta a gaveta; PIX Efí
permanece antecipado. Credenciais e rascunhos não recebem armazenamento adicional.

## Evidência e esforço

Antes: todos selecionavam o mesmo tipo `card_machine`, sem identidade física nem
exclusividade entre entregas. Depois: seleção identificada, uma alocação por aparelho,
conflito conserva o pedido pronto e orienta escolher outro/aguardar devolução.
Nenhum aparelho disponível bloqueia somente a entrega que precisa dele.

Desenho da jornada mantém abrir despacho→selecionar→confirmar. Evita memorizar
quem levou qual aparelho; o vínculo leva ao pedido. No navegador, resposta perdida
foi provocada depois do commit: um POST, consulta do recibo, despacho confirmado
sem repetir. Devolução posterior deixa o pagamento pendente. Concorrência de duas
conexões PostgreSQL resulta em um vencedor; corrida devolução/acerto conserva os
dois fatos. Falha na sincronização reverte dispositivo e pedido na mesma transação.
Não há medição humana de economia de tempo ou prova de ganho em campo.

## Testes efetivamente executados

| Ensaio | Fonte / resultado | Evidência local |
| --- | --- | --- |
| Contratos PostgreSQL: aparelho, pagamento, custódia, replay, projeção e courier | c1063c850: **90 passaram**, sem skips,254,52s | device-contracts-c1063c850.txt |
| Corrida forçada: ambos enxergam livre antes do lock | 47e9c657a: **1 passou**, duas conexões, um vencedor | device-forced-race.txt |
| Navegador integrado Gestor/Admin | c1063c850: **31 passaram**,1,6min | device-browser-final.txt |
| Unidade Orders | **303 passaram** | device-ui-verified.txt |
| Typecheck/build | Ambos passaram | device-typecheck-verified.txt / device-build-final.txt |
| Gate nativo Admin | **264 passaram**, strict canonical passou | device-admin-final.txt |
| Revisão focada de API/projeção/persona | **69 passaram**,13 subtests | device-backstage-review.txt |
| Arquitetura, navegação Admin e debug adapters | **37 passaram** | device-failure-fixes.txt |
| Suíte ampla isolada fixa | **23 falharam,9452 passaram,79 skips**,38 subtests,569,41s em6f0f38145 | broad-negative-summary.txt |
| Todos os23 nós que falharam, após correções | **23 passaram**,1139,81s emc1063c850 | device-failures-retest.txt |
| Estilo Python | Ruff completo passou; teste posterior também verificado | device-ruff-all.txt |

As famílias se sobrepõem; não somar os números como testes únicos. A suíte ampla
não foi inteiramente repetida no HEAD posterior. Seus23 negativos foram: navegação
sem entrada para o Admin novo (1), seed que enviava tipo genérico de aparelho (20)
e fronteira shop→surface direta (2). Correções: entrada canônica em Configuração,
seed escolhe o aparelho demo identificado e import passa pelo adaptador existente
como padrão arquitetural. O reteste abrange os mesmos23 IDs. O seed conserva
configuração nativa no flush; nenhum seed foi executado em dados reais.

Negativos anteriores preservados na .orders-lab: fixture Fulfillment em transição
inválida (corrigida para in_progress), contratos antigos com card_machine genérico,
expectativa de devolução oculta enquanto pagamento pendente e mensagem de seleção
quando o aparelho já estava ocupado. Não eram contratos novos aprovados por silêncio:
o requisito explícito exige devolução independente e identidade física. Também houve
buscas de caminhos inexistentes e uma edição abortada antes de escrever por cwd
incorreto; corrigidas. Ambiente Python/npm reutilizado; não houve instalação limpa.

Os79 skips da suíte ampla permanecem limite dessa execução. Na rodada SQLite
focada, duas provas de concorrência foram puladas por exigir PostgreSQL; a rodada90
PostgreSQL e a corrida reforçada não tiveram skips. O log amplo bruto fica privado
porque stdout de seed contém credenciais sintéticas; resumo exportado registra seu
SHA256 e todos os nós negativos. Não foram exportados cookies, dumps ou payloads.

Screenshots do despacho e cadastro foram inspecionados: controles nativos, texto
legível, sem sobreposição no diálogo/formulário. Console do ensaio Admin sem erros JS.
Não equivale a ensaio físico de touch/tecnologia assistiva. Na resposta perdida,
o backend já tinha aplicado o despacho: um POST, recuperação por recibo, sem repetir.
A falha parcial reverte aparelho e pedido; devolver e acertar mantêm fatos separados.

## Migração e rollback

0061 é aditiva, sem alteração de Core ou reconciliação. Aplicada somente em bancos
sintéticos. Banco separado `orders_device_migration_lab_6e1e`: migração completa,
0061→0060→0061 com cadastro vazio, depois tentativa de remover inventário populado
recusada; linha e registro de migração preservados. O guard impede apagar cadastro
inclusive sem aparelho em trânsito. Cadastros reais continuam exigindo conferência
física e autorização de ambiente/coorte.

Para liberar: migration, backend com exclusividade e frontend compatível, com
capacidade supervisionada. Cliente antigo com referência genérica é recusado para
nova alocação; custódia histórica continua retornável. Rollback suspende despachos
dependentes e conserva backend seguro, inventário, alocações e recibos; não remover
0061 populada ou reativar código antigo sem exclusividade. Nada foi publicado.

## Estado e limites

M00–M03 implementados. M04 tem validação funcional e migration executadas;
aceite de capacidade depende do resultado de desempenho abaixo. Nenhuma medição
nova será substituída pela rodada antiga que passou em922fb522c. A fixture atual
contém500 pedidos ricos e10 aparelhos (3 em trânsito,6 disponíveis,1 inativo).
Ambiente loopback, PostgreSQL55439/Redis56389 sintéticos; Apple M2,8 CPUs lógicas,
8GiB, macOS15.4.1, Python3.12.5/Django6.0.5/Daphne4.2.1/Node22/Chromium.
Processos de outras tarefas foram preservados. Somente nossos leitores HTTP foram
encerrados após os ensaios; bancos de laboratório continuam disponíveis.

A extensão mantém G02/G06/G07 aplicáveis ao uso real, identificação física e
capacidade; nenhuma decisão humana foi presumida. T/P/R do plano principal não
são declarados concluídos por este incremento. Retenção pós-reload permanece
opcional e não implementada; C07 permite contexto em memória e saída protegida,
portanto essa persistência, por si só, não é bloqueio obrigatório da fase técnica.

## Budgets da versão integrada: não aprovados

| Rodada, mesma fonte47e9c657a | Backend p95,1/2/10 clientes (ms) | Browser p95 (ms) |
| --- | --- | --- |
| Inicial, host compartilhado |322,670 /289,835 /954,286 |1857 |
| Repetição após testes pesados PDV encerrarem |229,419 /519,819 /2035,579 |1695 |
| Fases separadas:5 leitores backend encerrados antes de1 leitor+Nitro browser |241,280 /230,099 /1058,243 |1620 |

São60 amostras por configuração backend e20 navegações browser por rodada. Todas
as amostras e primeiras leituras frias estão nos JSON; não removemos outliers nem
substituímos resultados negativos pela melhor rodada. Os3 testes browser passaram
funcionalmente em cada rodada (filtro e ida/volta por link/history), mas esses testes
registram latência: **exit0 não implica budget aprovado**. Backend≤500ms e interação
≤1500ms continuam reprovados para500 pedidos/10 clientes nesta versão/topologia.
A leitura usa15 consultas, com batch Hold único; a distribuição exata de queries,
payload e RSS consta em cada amostra. Não há medição nova de todos os demais budgets:
comando/SSE anteriores permanecem provas de suas fontes, não ganho de campo atual.

O perfil instrumentado de uma leitura totalizou299ms: montar opções de equipamentos
somou aproximadamente15ms; não mostrou N+1 de aparelho. Isso não prova a causa das
caudas de latência. O host registrou cerca de11,7GiB de swap utilizado e carga
concorrente; snapshots antes/entre/depois estão anexados. A rodada por etapas
reduziu processos nossos ociosos; não encerrou processos de terceiros. A comparação
com fonte anterior serve apenas ao diagnóstico, sem equivalência de payload de
inventário e sem alterar o gate. Repetições adicionais no mesmo host sem uma mudança
controlada não constituem plano de aprovação.

**Decisão concreta de gate:** capacidade integrada não pronta para publicação/piloto.
Manter testes sintéticos e integração técnica; homologar ambiente/recursos/rede/coorte
em G06/G07 e repetir estes limites antes de liberar500 pedidos/10 clientes. Não
propomos aumentar o limite para tornar a rodada verde. O trabalho de capacidade
continua aberto; não confundir essa pendência com a opção de persistir rascunhos.

**Esforço:** antes e depois do despacho usam abrir→escolher→confirmar (3 ativações
no subfluxo; acesso/login/identificação são parcelas separadas, não removidas). Antes
o tipo genérico exigia memória externa sobre o aparelho; depois identidade e pedido
aparecem juntos. Resposta perdida:0 ativações adicionais para consulta automática,
1 efeito. A devolução pode ser feita sem acerto e vice-versa; a confirmação conjunta
continua opt-in. R=0 foi demonstrado nessas jornadas automatizadas, não em todas as
pessoas/cenários. T humano e redução agregada≥30% ainda não foram medidos.

### Gates e fases

| Item | Estado / impacto |
| --- | --- |
| M00 proveniência / M01 modelo / M02 domínio / M03 UI | Implementados e validados funcionalmente nos commits acima |
| M04 validação | Funcional, concorrência e migration executadas; budget de capacidade reprovado, aceite aberto |
| G02 | Inventário físico, responsável e custódias legadas requerem conferência/autorização; nada reconciliado |
| G06 | Homologar hardware/rede/topologia/capacidade e repetir distribuição; não aprovado pela fixture local |
| G07 | Coorte/janela/suporte/parada e liberação específica pendentes |
| Fase técnica global T | Não concluída; herda critérios abertos do plano principal e budget atual |
| Piloto P | Preparado documentalmente; não iniciado, sem cinco turnos reais |
| Rollout R | Não autorizado nem executado nesta tarefa |

Integração PDV recebida por coordenação em40e3b8539 (sobre fc0aa9d29/09f8983d6
sobre47e9c657a). Os testes da tarefa PDV são relato daquela tarefa; não foram
reexecutados aqui nem incorporados aos nossos totais. Esta entrega não altera
contratos após47e9c657a. O checkout original permaneceu em b589e22c5 com arquivos
não rastreados de terceiros preservados, verificação somente leitura no fechamento.


### Contraprova da base anterior no mesmo host

Leitura somente, fonte fixa922fb522c, mesmo banco sintético, middleware/60 amostras,
5 processos e1/2/10 clientes: backend p95301,938 /2679,025 /2290,033ms. A fonte que
havia passado451,290ms antes também reprova agora. Isso impede atribuir a diferença
observada exclusivamente ao incremento de aparelhos ou declarar regressão causal
com estas rodadas sequenciais. Payload da fonte antiga não inclui inventário físico;
não é teste de equivalência funcional. O resultado sustenta a necessidade de uma
comparação estável, não autoriza a versão nova. Base e atual foram apenas lidas;
nenhum writer antigo foi habilitado, nenhuma migração foi revertida neste banco.

Próxima decisão G06 é indicar ambiente de ensaio representativo e estável (aparelho,
rede e recursos/topologia disponíveis) e responsáveis; executar a mesma distribuição
sem relaxar budgets. O laboratório atual não prova capacidade integrada, tampouco
justifica refatorar regras maduras por uma cauda de latência não isolada.
