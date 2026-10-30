# Modo padrão e modo compacto: regras comuns e diferenças (proposta para decisão)

Somente proposta. As prévias que a acompanham não autorizam implementação.

## Um sistema visual, duas composições

A peça, a cor, o botão, o badge, o card, o aviso e o diálogo são os mesmos nos dois modos.
O que muda é **quanto do topo e da base o cromo ocupa** e **o que fica permanentemente à
vista**. O modo vem da tarefa e do posto, não do app inteiro. Por isso o Compras é híbrido:
o Receber é compacto e os cadastros são padrão.

## Regras comuns aos dois modos

1. **Celular primeiro.** O desenho parte de 320px. Os alvos têm 44px e não há rolagem
   horizontal. Texto que muda de sentido ao ser cortado não se corta.
2. **Três alcances, três lugares.**
   - **Navegação global:** o selo do app leva à Central e troca de app. A barra inferior,
     com posições fixas, e a lateral levam às seções. "Mais" abre a gaveta completa.
   - **Opções da página:** o ⋮ do grupo de ferramentas.
   - **Ações do registro:** o ⋮ na extremidade da linha, do card ou da linha de contexto do
     rodapé. Opções de card e fechar não têm borda.
3. **Ferramentas na ordem Filtro → Busca → Opções**, num grupo só, com a busca elástica.
   Busca ou filtro ativos ficam sempre identificáveis, com contagem e Limpar acessível,
   mesmo depois de rolar.
4. **Alertas críticos e erros explícitos no topo**, com cor, ícone e texto. O dismiss fica
   no canto superior direito. Um aviso inteiro, o resto em "e mais N".
5. **Conexão é estado real** e nunca depende só da cor. No desktop fica o OperatorLiveStatus
   já maduro.
6. **Abas com rolagem horizontal** quando não cabem, com a ativa sempre à vista.
7. **Rodapé fixo, ação flutuante, barra secundária, paginação e menus** existem quando a
   tarefa pede, não por padronização. Uma confirmação aparece uma vez só.
8. **Desfazer nativo preservado.** Sair durante a janela diz a consequência.
9. **Identidade do registro nunca some.** Detalhe, conferência e venda mostram o que
   identifica o registro: código, fornecedor, NF, comanda.

## Diferenças, e por que existem

| | Padrão (gerencial) | Compacto (operação contínua) |
|---|---|---|
| Quem e onde | Gestor sentado: Marketing, B.I., Compras/Base | Balcão, cozinha, saída, doca: PDV, KDS, Gestor de pedidos, Receber |
| Topo no celular | Título da seção visível + linha de ferramentas | **Uma linha**: selo com chip · Filtro/Busca/⋮ · Avisos |
| Título da seção | Visível, porque há muitas telas parecidas e o título orienta | Não se repete: é a vaga ativa da barra inferior (fica no h1 acessível) |
| Cadência e última leitura | Selo de texto permanente aceitável | Primeira linha das Opções; chip no selo |
| ☰ | Pode existir | Não: a gaveta abre pelo "Mais" (exige que o app tenha "Mais") |
| Densidade | Respiro, descrições curtas, tabela e paginação | Fila e ação da base em primeiro lugar; aviso denso opcional |
| Desktop | Igual nos dois: lateral, OperatorLiveStatus, ferramentas na linha do título | idem |

**Por que o compacto tira o título:** no posto contínuo, a pessoa já sabe onde está pela
barra inferior. Os 56 a 80px economizados viram mais um pedido ou o card inteiro. A medida
está no KDS: a 320×568 o card em foco ganha 32px úteis só com o cabeçalho, e 178px com o
aviso denso.

**Por que o padrão mantém o título:** no trabalho gerencial a pessoa navega entre muitas
telas de aparência parecida (Insumos, Fornecedores, Custos), e o título é a âncora. A altura
pesa menos ali do que no posto contínuo.

**Continuidade no híbrido: ainda não está garantida.** Na prévia do Compras, a barra
inferior e o Avisos ficam no mesmo lugar ao ir da Base (padrão) para o Receber (compacto).
O resto troca: o ☰ e o título somem, o ⋯ solto vira ⋮ dentro do grupo e aparece o selo.
Para haver continuidade de verdade, o modo padrão teria de adotar o mesmo selo e o mesmo
grupo Filtro/Busca/⋮, ganhando só a linha do título por cima. Isso fica para decisão (item 5
abaixo).

## Ainda precisa de decisão

As conclusões por app estão nos READMEs de cada pasta. As decisões transversais:

1. Avisos como controle próprio (recomendado) ou dentro das Opções. Dentro das Opções só
   serve se o ⋮ ganhar a contagem.
2. Aviso denso no celular compacto (`?aviso=denso`): a descrição sai da vista e fica só
   para o leitor de tela.
3. O chip de conexão no selo: entender "↻ periódico" pede aprendizado. O estado completo
   está no nome acessível e na primeira linha das Opções, mas não aparece num toque no chip.
4. Na mesa, filtro no grupo **e** recortes na toolbar fazem o mesmo papel.
5. O modo padrão adota o selo e o grupo do compacto, mais a linha do título, para dar
   continuidade ao híbrido? Ou aceita-se o salto ao entrar numa tela de tarefa?
6. **"Mais" na barra inferior (regra 7).** Gestor e Compras não têm "Mais". Sem o ☰, o
   Gestor perde Histórico, Catálogo, Clientes, Canais e a troca de operador no celular.
   Há três saídas: "Mais" fixo na barra inferior do compacto (recomendado), "Menu completo"
   no fim das Opções (feito na prévia do Compras), ou manter o ☰.
7. **Tom de leitura sob demanda.** O Compras não tem leitura periódica: lê ao abrir e em
   Atualizar. O chip ↻ diz "atualização periódica", o que não é verdade ali. O kit precisa
   de um tom próprio, ou o chip some nessas telas.
