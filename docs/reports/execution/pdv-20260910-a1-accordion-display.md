# PDV — acordeão de linhas e verificação da Tela do Cliente

2026-09-10, continuação local de `ead45be7a`, mesma worktree isolada. Pedido do usuário: projetar linha compacta com todos os indicadores ativos, detalhes sob expansão, preservar informação operacional essencial; localizar e verificar Tela do Cliente existente.

## Linha de venda

Quantidade, produto e total permanecem na primeira faixa. Uma segunda faixa reserva posições para observação, desconto, autoria, estado da cozinha e seta de expansão. Slots sem informação preservam a geometria sem acender ícones inativos; não são ações separadas. Títulos explicam os ícones e a descrição acessível informa os tópicos ao leitor de tela. Observações ficam por extenso: o domínio ainda não distingue instrução crítica de nota secundária, então ocultá-las poderia esconder algo importante.

Uma linha pode ser expandida por clique, Enter ou Espaço; abrir outra recolhe a anterior. Região nomeada e aria-expanded descrevem o estado. Detalhes incluem desconto/motivo/preço anterior, preço unitário, controles, criador/último editor/horário disponíveis e cancelamento de envio quando autorizado. Estado da cozinha não é repetido em um segundo selo. A expansão não redefine o contrato de seleção múltipla, o preço nem os comandos de domínio.

O alvo do teclado é independente da expansão e aparece como “Teclado: produto”. Recolher detalhes não o troca silenciosamente. A seleção múltipla usa seu botão próprio e não expande a linha. Nenhum indicador ou resumo de auditoria é inventado para histórico sem evidência.

Componente real, CSS real, cenário sintético completo: observação longa + desconto automático + cozinha pronta + criador diferente do editor, ao lado de linhas com tópicos ausentes. Capturas compacta/expandida em `.artifacts/pdv-20260910-a1/accordion-{compact,expanded}.png`; geometria em 320/390/768/1024/1366 px sem overflow horizontal. Expansão por teclado conferida. Isso é inspeção de componente, não aceite humano do PDV em todos os equipamentos.

## Tela do Cliente — já existia

A rota é `/display` no mesmo endereço do PDV. Na página **Sessão de caixa**, o ícone de monitor no cabeçalho abre uma janela nomeada, reutilizada nos próximos cliques. Nesta alteração o botão ganhou texto “Tela do cliente” quando há espaço, mantendo ícone e nome acessível no estreito.

Para experimentar a implementação atual:

1. No computador do caixa, usar um único PDV de venda aberto no navegador.
2. Em Sessão de caixa, acionar o monitor/Tela do cliente; permitir a janela se o navegador bloquear.
3. Arrastar essa janela ao segundo monitor e colocá-la em tela cheia pelo navegador.
4. Voltar à janela do operador e à venda. A tela acompanha os itens, total, etapa de pagamento/PIX e resultado/troco conforme o estado publicado pelo PDV.
5. Fechar a janela do display ao terminar o ensaio.

Transporte atual: BroadcastChannel da mesma origem e perfil de navegador, sem servidor. Não é pareamento de tablet/PC: abrir `/display` em outro dispositivo ou outro perfil não recebe a venda. O canal é global dentro da origem; várias janelas publicadoras podem se misturar. Não há expiração geral/heartbeat de snapshots: fechar o operador pode deixar o último estado visível. O resultado tem retorno temporizado às boas-vindas, mas isso não cobre todas as fases. Essas limitações preexistentes impedem considerar PDV-020 concluído e permanecem no plano maior (escopo, versão, expiração e disputa de publicador).

Novo E2E testa página Nuxt real em duas janelas Chromium e BroadcastChannel real, com snapshots sintéticos: handshake inicial, itens/total, ausência do login no display e transição para troco. Não usa gateway, pagamento, impressora nem monitor físico; não valida sessão real do backend ou entrega de QR por provider. Testes de presentation existentes cobrem montagem do snapshot. O teste de navegador não transforma simulação em aceite de operação real.

## Validação e publicação

846 testes frontend passam; 30 testes do componente passam após ajuste final; typecheck/ESLint e diff check passam. Quatro E2E passam (login, rede e display), com build Nuxt. Uma primeira execução paralela de Vitest/build conflitou nos arquivos gerados do Nuxt; repetida sequencialmente, passou sem skips. Não houve alteração de backend ou necessidade de repetir testes PostgreSQL nesta fatia.

Logs locais `accordion-{all-tests,tests,types,lint,e2e,geometry}.log`. Sem alteração de tema, migration, push, PR, merge, deploy ou efeito operacional. O código desta worktree ainda não está online; a existência de `/display` foi confirmada no código da base, não por inspeção do deploy atual.

## Refinamento após revisão visual do usuário

O usuário apontou falta de padding e organização. O resumo ganhou inset de 12 px, espaçamento consistente e borda discreta por linha. Os detalhes agora ocupam toda a largura, com inset de 16 px e blocos separados para valor/quantidade, desconto e autoria. Controles de quantidade formam um único grupo; remoção fica apartada no rodapé. Observação perde ícone repetido e itálico, passando a uma nota com margem e régua lateral. Indicadores fixos, ações, seleção e preços preservados.

Validado com 30 testes existentes do componente, typecheck, ESLint e diff check. Inspeção de resumo/expansão em 320/390/768/1024/1366 px sem overflow horizontal, cenário completo com desconto, observação, cozinha e dois operadores. Capturas: `spacing-compact.png`, `spacing-expanded.png` e `spacing-line.png` em `.artifacts/pdv-20260910-a1/`. Nenhuma publicação nesta revisão.

## Estudo com quantidade sempre acessível

Após nova solicitação de prévia, −/quantidade/+ ficam visíveis na linha recolhida. O número central seleciona a linha e o modo quantidade no teclado, sem expandir. Remove-se a quantidade duplicada antes do produto; preço unitário acompanha o controle. Desconto ganha rótulo numérico compacto e autoria usa lápis+nome em uma faixa conjunta, sem espaços vazios entre indicadores. Cozinha mantém selo separado. A mudança substitui o estudo anterior de slots fixos, seguindo a discussão posterior.

31 testes do componente, typecheck, ESLint e diff check passam. Browser com componente real e parent sintético confirmou incremento de 2 para 3 com zero regiões de detalhes abertas; geometria em 320/390/768/1366 px sem overflow. Captura `quantity-line.png` em `.artifacts/pdv-20260910-a1/`. Prévia local, não publicada.

## Seleção separada da expansão — decisão após benchmark

Usuário aprovou retorno a linhas compactas: tocar no nome seleciona a linha e exibe somente nela os controles +/−; a seta separada expande detalhes. Quantidade fica no resumo das linhas inativas e no controle da ativa, sem duplicação. Seleção múltipla mantém checkbox independente. Resumo perdeu bordas por cartão e parte do espaçamento vertical do estudo anterior; observações e cozinha continuam aparentes.

Comparação interativa local em `http://127.0.0.1:43021`, com painel completo (lista, teclado e rodapé), largura de 320 px e altura de 720 px, cenários de 3/10/20 linhas e opção de observações/autoria. Anterior usa o componente da base `696f5410`; novo usa o componente real da worktree. Dados e eventos são sintéticos, compartilhados entre painéis. Teclado físico no harness é encaminhado apenas ao painel focado; não existem comandos de caixa/venda nessa prévia. O servidor foi mantido ativo para revisão do usuário; não é um deploy. Harness em `.artifacts/pdv-20260910-a1/visual-app/`.

Medição local: linhas anteriores simples com 60 px; novas inativas com 54–61 px; selecionada com 104 px para controle de toque. Nos cenários de 10/20 itens cabem quatro linhas completas antes da rolagem em ambos os painéis nesta configuração. É evidência de geometria, não de velocidade humana. Teste browser confirmou seleção sem abrir região, um único stepper, edição pelo teclado e expansão pela seta. Capturas `density-{3,10,20,rich}.png` e log `density-geometry.log`.

847 testes frontend passaram, com repetição focada de 31 testes após reforço das asserções de seleção/expansão; typecheck, lint e diff check passam. Mudança local, sem publicação.

## Alternativas exploratórias — decisão pendente do usuário

A pedido do usuário, a proposta **A — lista de conferência + editor fixo** fica registrada como **plausível, não aprovada para incorporação**. A lista mantém quantidade, produto, total, notas e resumos operacionais; selecionar um item troca o editor inferior de altura fixa, sem expandir a linha. O editor reúne quantidade (+/− e campo direto), desconto e detalhes. Checkboxes aparecem no modo de seleção. O teclado numérico permanente foi retirado neste estudo. O usuário não acolheu a sugestão posterior de numpad contextual; essa sugestão não deve ser tratada como decisão aprovada.

Motivação de A: separar conferência de edição, reduzir repetição e evitar deslocamento das linhas. Risco principal: digitação por toque sem numpad permanente; o espaço reservado ao editor também disputa altura com a lista. Verificação sintética local: alteração de quantidade, nota e estabilidade da altura das linhas ao trocar abas; cinco linhas simples completas na janela de 320×720, contra quatro na comparação anterior. Não representa teste de produtividade humana.

Preservação local: `.artifacts/pdv-20260910-a1/visual-app/app/FocusPosCartPanel.vue`, capturas `focus-{3,10,20,rich}.png` e `focus-checks.log`. São artefatos locais de estudo, sem integração ao componente de produção. O protótipo ainda não expõe todas as ações/formatos de desconto e auditoria do produto; não há paridade funcional declarada.

A alternativa **B — console com numpad permanente** explora outra prioridade: usar um único console para operar o item selecionado, com nome e valor em edição junto ao teclado, modos quantidade/desconto e acesso a observação. A comanda mantém linhas enxutas. Benefício proposto: acesso imediato por toque, sem abrir teclado nem repetir controles em cada linha. Custo: o console ocupa espaço permanente; desconto e detalhes ainda aumentam sua altura neste estudo. B também não está aprovada e não é uma implementação final. Não deve ser apresentada como uma nova arquitetura completa da tela de venda: é uma alternativa de interação do painel do pedido.

A comparação local ganhou seletor A/B, preservando A para reflexão. B está em `ConsolePosCartPanel.vue` no mesmo harness. Nenhuma venda ou comando operacional é registrado; sem publicação online. A avaliação deve considerar o PDV completo e equipamentos reais antes da escolha definitiva.

## C/D — preferências visuais fornecidas pelo usuário

Preservadas A/B. Novos estudos locais C (quantidade antes do produto) e D (produto primeiro, quantidade perto do total), ambos com divisórias simples, numpad permanente e coluna lateral Qtd/Desc %/Desc R$/Obs. Desconto fixo usa vírgula no numpad. Backspace e remoção usam cor danger; Enviar/Transferir recuperam bordas e ícones. Cabeçalho mantém contagem e modo Selecionar. Seta dedicada abre um acordeão por vez; tocar no nome apenas seleciona para o teclado. Observações, desconto e cozinha permanecem no resumo; autoria e preço unitário ficam no acordeão. Abrir detalhes também seleciona a linha correspondente.

C/D são variações da mesma interação, não duas arquiteturas diferentes. A expansão ocupa a área rolável da lista e pode reduzir bastante os itens simultaneamente visíveis: tradeoff a avaliar pelo usuário. Protótipos ainda não têm paridade operacional com o produto; nenhum comando de venda é executado nesta comparação.

Verificação em Chromium: quantidade, desconto percentual, desconto em reais com vírgula, abertura/fechamento de acordeão em ambas as versões, sem erros de página. Inspeção visual de C expandida e D com notas/autoria. Artefatos locais `ReceiptPosCartPanel.vue`, `TablePosCartPanel.vue`, `refine-check.cjs`, capturas `C/D-{rich,expanded}.png` no diretório de estudos. Nenhuma alteração ao componente de produção ou publicação.

## E — C compacta, ainda exploratória

Usuário prefere C como base, sem considerá-la definitiva. E preserva C e remove o bloco “editando”, apresenta quantidade sem fundo como “2 × Produto” e mantém preço unitário sempre visível em todas as linhas. Linha ativa ganha +/− e lixeira mesmo recolhida. Acordeão usa o mesmo fundo do item, sem bloco contrastante interno. Rodapé mantém acabamento de C com Enviar/Transferir empilhados à esquerda e Pagamento à direita. Reduzidos padding do cabeçalho, console e rodapé; teclas numéricas mantêm 44 px de altura. Seleção visual da linha identifica o alvo do teclado; a ausência de identificação junto ao teclado precisa ser avaliada quando a linha ativa sai da área visível.

Protótipo `CompactPosCartPanel.vue`, seletor E no harness. Chromium exercitou incremento, tecla numérica e acordeão; conferiu preço unitário nas três linhas e ausência de erros de página. Capturas `E-{compact,expanded}.png`, inspeção visual do acordeão. Não é teste de operação real nem incorporação ao produto.

### Refinamento de E — ações e teclado

Preço unitário usa “cada” por leitura mais natural. A faixa da linha ativa agrupa −/quantidade/+ em um controle com borda e separa Remover com ícone e rótulo danger. Seleção múltipla recebe contagem, Limpar, botões de Enviar/Remover e cancelamento de envio quando permitido. F4 voltou ao botão Pagamento; handler restrito ao painel emite o mesmo evento prepare do botão (harness sem operação real).

↑/↓ com foco dentro da lista selecionam e focam a linha anterior/seguinte e a trazem à área visível; param nas extremidades. Não alteram quantidade nem abrem acordeão. Campos, menus nativos, diálogos e combinações modificadas são preservados; fora da lista, setas não são interceptadas pelo handler. Navegação não muda seleção múltipla por checkbox.

Chromium validou foco/seleção pelas setas, limite superior, preservação fora da lista, incremento, preços em todas as linhas, rótulo F4 e seleção múltipla sem erros de página. Capturas inspecionadas `E-polished.png` e `E-batch.png`. Teste não executa pagamento. Continua estudo local, sem alteração no componente de produção.

### Navegação de E como operação do item

Foco visual agora contorna o `li` inteiro (resumo, ajustes e acordeão), sem outline parcial no botão do nome. Alt+I, indicado no cabeçalho e acionável por clique, leva à linha ativa (ou primeira disponível). Código físico KeyI também é aceito para layouts com Option/dead keys. Setas ↑↓ navegam; Enter no botão principal alterna o acordeão; → abre e ← fecha. +/− ajustam a linha focada; Delete usa a confirmação de remoção existente. Esc fecha detalhes ou devolve foco ao cabeçalho. Uma dica compacta aparece enquanto a lista tem foco. Botões internos preservam Enter para sua ação nativa. Seleção por checkbox permanece distinta da linha ativa para edição.

Chromium validou Alt+I, Enter, ←→, ↑↓, incremento por +, Delete abrindo confirmação e Esc retornando ao cabeçalho, sem erros de página. Contorno completo inspecionado em `E-navigation.png`; roteiro `nav-check.cjs`. Atalho precisa de avaliação nos navegadores/equipamentos do piloto; estudo continua local.

## Incorporação da versão E ao componente real

Após autorização “pode prosseguir”, E foi incorporada a `PosCartPanel.vue`, mantendo A–D como estudos locais. A opção E do harness agora importa o componente real. Permanecem as regras de preço/maior desconto, transparência de preço anterior, autores e horário disponíveis, cancelamento de cozinha, remoção confirmada/undo e o F4 existente da página (sem handler concorrente no componente). O teclado lateral atende desconto percentual e em reais, com motivo e valor em edição também em lote. Ações de cozinha respeitam presença/habilitação das affordances; gravação/carregamento bloqueiam mutações do teclado e dos controles.

No modo seleção, clique em qualquer área da linha marca/desmarca; o checkbox impede propagação para não alternar duas vezes. Edição e expansão da linha ficam ocultas nesse modo. Espaço na linha focada inicia seleção múltipla e alterna sua marcação; setas navegam sem mudar o conjunto, Enter alterna a marcação quando o modo está ativo. Fora dele, Enter mantém a expansão. Clique na marcação e navegação não executam comandos operacionais.

O contorno de foco foi reduzido a 1 px a pedido do usuário, assim como a régua lateral. A dica de atalhos ocupa uma faixa estável: quando surgia só ao ganhar foco, deslocava o botão entre mousedown/mouseup e podia impedir o clique na seta. O navegador real revelou esse problema, corrigido antes da conclusão.

Validação inclui 37 testes do componente (seis novos para linha inteira, seleção por teclado, navegação/expansão, bloqueio durante gravação, desconto em lote e ação de cozinha desabilitada). O harness Chromium com componente real verifica Alt+I, Espaço, foco por setas, clique no preço/checkbox, desconto em reais com vírgula em lote, quantidade, confirmação, acordeão e cenários 3/10/20 com notas/autoria. Capturas `real-cart-{3,10,20,rich,batch}.png`; roteiro/log `real-cart-check`. Prévia local em `http://127.0.0.1:43021/` mantida para revisão. Não é teste com hardware/backend real nem publicação online; pendências gerais do plano PDV continuam no relatório de continuação.

Resultado final desta incorporação: 853 testes frontend em 49 arquivos passaram; typecheck, ESLint dos arquivos alterados e `git diff --check` passaram. Logs `integrated-{all-tests,types,lint}.log`. Nenhum teste de backend foi repetido nesta alteração exclusivamente frontend. Sem push, PR, merge ou deploy.

### Rodapé durante seleção

Refinamento solicitado: modo explícito de seleção oculta apenas os botões gerais de Enviar/Transferir/Pagamento, preservando Total parcial e sua linha fina de separação. Ações sobre o lote permanecem na barra da seleção. Mesmo sem marcações, o modo continua sem botões gerais até Concluir seleção; navegação normal não os oculta. Trata-se de visibilidade, sem alteração do atalho F4 da página. Validado por 38 testes do componente, lint e Chromium (entrada, marcação e saída), captura `footer-selection.png`. Sem publicação.
