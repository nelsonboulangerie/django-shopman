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
