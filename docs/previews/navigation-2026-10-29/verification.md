# Verificação das prévias de navegação

Data: 29/10/2026. Escopo: protótipo local, sem execução dos apps ou escrita em APIs.

## Evidência de interação

A verificação no navegador percorreu os destinos abaixo, nas duas variantes. Em cada
seleção, o título esperado ficou visível nos dois quadros da comparação.

| App | Destinos conferidos |
|---|---|
| Gestor | Em andamento, Saída, Histórico de pedidos, Catálogo, Coleções, Clientes, Grupos de clientes, Unificações, Canais de venda, Catálogo por canal, Rotinas da loja, Postos de trabalho |
| Compras | Visão geral, Reposição, Fornecedores, Custos de compra, Conferência de recebimento, Divergências no recebimento, Insumos, Contagem de estoque |

Outros ensaios e resultados observados:

| Gesto | Resultado observado |
|---|---|
| Compactar a primária no Gestor B | Largura de 76 px, mantendo contextual de 218 px |
| Recolher contextual com primária compacta | Contextual oculta e controle Mostrar opções de Produtos disponível |
| Alternar A/B em Catálogo | Destino e dados mantidos |
| Navegar em um quadro da comparação | Outro quadro muda para o mesmo destino |
| Buscar Geleia, abrir produto, atravessar para Compras | Insumos mostra o mesmo SKU e oferece retorno ao produto |
| Retornar pelo cabeçalho | Detalhe Geleia de frutas vermelhas reaberto e busca Geleia preservada |
| Entrar na Central pelo nome do app e retomar | Central de apps visível; retorno para Divergências no recebimento |
| Navegação rápida móvel → Pedidos → Em andamento | Destino aberto e gaveta fechada |
| Voltar pelo navegador | Catálogo restaurado após sair para Em andamento |
| Resolver falta de manteiga com recebimento parcial | Confirmar entrada passa a estar habilitado; valor recebido continua R$ 1.156,00 |
| Abrir gaveta móvel em dois níveis | Primeiro assuntos, depois destinos, com Todos os assuntos como retorno |
| Abrir gaveta A | Grupos e destinos na mesma árvore |
| Abrir gaveta ou diálogo de detalhe | Fundo inerte; foco na camada aberta |

O recebimento é fictício. Nenhum gesto acima cria entrada, cobrança, cadastro, pedido
ou movimento real. As simulações existem para avaliar a navegação e a consequência
visível das escolhas.

## Perfis observados

As medidas abaixo foram lidas do navegador, não inferidas do nome da captura.

| Perfil | Resultado |
|---|---|
| 390 × 844 | Navegação inferior presente; gaveta em etapas ou árvore; cards de recebimento; largura da página sem transbordamento horizontal |
| 768 × 1024 | Barra lateral permanente oculta e navegação inferior visível; Contagem acessível pela gaveta |
| 1280 × 720 | Conferência B sem transbordamento da página ou tabela; resumo reorganizado em uma coluna, largura observada de 805 px |
| 1024 × 768 | Primária compacta de 76 px; contextual independente; sem transbordamento horizontal da página, da navegação ou da tabela |
| 1440 × 900 | Tabelas e barras laterais disponíveis; Conferência B com resumo ao lado; sem transbordamento horizontal da página ou tabela |

Capturas desktop: 1440 × 900. Capturas móveis: 390 × 844. Nenhuma baseline de CI foi
gerada ou alterada. Zoom de 200% continua fora desta rodada de verificação; não se afirma aprovação
nesse perfil.

## Verificação estática

- `node --check docs/previews/navigation-2026-10-29/preview.js`: sem erro de sintaxe.
- `git diff --check`: sem erro de whitespace.
- `python3 scripts/check_docs_governance.py`: verificação documental aprovada.
- O script não contém fetch, XHR, WebSocket, beacon ou armazenamento persistente.
- Os únicos recursos carregados pela prévia são locais, incluindo a fonte já usada
  pelo projeto. `connect-src 'none'` impede chamadas de dados.
- Arquivos alterados restritos a documentação e `docs/previews/navigation-2026-10-29/`.

Durante a observação dos quadros, a ferramenta de navegador registrou um erro de
`MutationObserver` sem identificar origem no log retornado. O script da prévia não usa
essa API. As interações acima concluíram; este registro não declara o console inteiro
livre de erros nem atribui a causa sem stack. A verificação funcional documentada é
do protótipo, não uma certificação dos apps Nuxt.

## Segunda rodada: atalhos e composição

Conferido no navegador após a revisão das barras:

- Mobile 390 × 844: os seis atalhos de destino da tabela do README foram acionados
  individualmente nas duas variantes. Cada toque abriu o título esperado, com
  `data-drawer=false`. Não houve etapa adicional em B.
- Desktop 1440 × 900 com `quick=1`: repetido o mesmo percurso dos seis atalhos nas
  duas variantes, com os mesmos títulos.
- Composição no celular: mover recortes para baixo ocultou a faixa superior e
  manteve exatamente três controles de filtro, sem duplicação.
- Catálogo: próxima página mudou de 1–6 de 9 para 7–9 de 9 produtos.
- Comparação: os dois iframes receberam `local=bottom` e `quick=1` na configuração.
- Recebimento: resolver a diferença mudou a ação flutuante para Confirmar entrada.
  No desktop padrão, a mesma decisão atualizou a ação do cabeçalho; dock oculto.
- Troca Gestor → Compras pelo cabeçalho abriu Conferência de recebimento. Retorno
  à Central pelo mesmo controle exibiu a Central e seus apps.
- Mobile 320 × 740: largura observada 320, sem transbordamento da página; conteúdo
  rolável com 252 px no estado inicial de Contagem. Ao editar uma quantidade, dock
  oculto e foco preservado no campo. Ao sair, Revisar contagem habilitado e progresso
  de 1 de 6 insumos. Ajustada a posição do estado Registrado para não disputar espaço
  com o nome do insumo.
- Mobile 390 × 844 e desktop 1440 × 900: conteúdo, ação contextual e atalhos ocupam
  regiões sucessivas em fluxo, sem sobreposição fixa.

As capturas individuais de A/B e de Compras mobile foram atualizadas. As capturas
anteriores de comparação e de Central registram a primeira rodada. Não foi executado
ensaio em dispositivo físico com teclado virtual, leitor de tela ou zoom de 200%.
Os perfis tablet da seção anterior pertencem à primeira rodada, sem revalidação nesta.

## Modo sem controles do laboratório

No perfil 390 × 844, `clean=1` resultou em laboratório com display none, aplicação
iniciando em y=0 e conteúdo rolável de 501 px na Conferência. O toque em Reposição
preservou `clean=1` na URL. Captura: `captures/compras-mobile-clean.jpg`.
O script atualizado também foi obtido com sucesso pelo túnel público temporário.

## Estado de aprovação

Prévia entregue para avaliação do dono. Não há preferência aprovada entre A e B.
Implementação e deploy continuam dependendo de autorização explícita posterior.
