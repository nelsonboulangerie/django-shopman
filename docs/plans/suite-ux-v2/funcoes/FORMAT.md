# Engenharia reversa por FUNÇÃO — formato comum (leia inteiro)

Contexto: Shopman é a suíte de operação de uma padaria/boulangerie (Nelson Boulangerie). Oito apps
de operador (Nuxt, em `surfaces/*-nuxt`, layer comum `surfaces/operator-kit`) falam com um backend
Django (`shopman/backstage/api/`, `shopman/backstage/projections/`, `shopman/backstage/services/`,
`shopman/shop/services/`, e os pacotes de domínio em `packages/*`). Repositório:
`/home/user/django-shopman/.claude/worktrees/ux-reform-plan` (SOMENTE LEITURA para você).

O dono pediu: **"não olhe para o rosto; primeiro função; forma segue função; minimalismo na sua
essência mais profunda e cruel, não como preguiça de resolver a complexidade; encontre os padrões
comuns das necessidades das funcionalidades."** Portanto: ignore cores, layout, componentes. Descubra
**o que cada funcionalidade existe para fazer no mundo real**, para quem, em que situação, com que
informação mínima, e qual o caminho mais curto possível. Leia o código do front E do back (actions,
projections, services, modelos) para entender a função verdadeira, as regras, os bloqueios e as
exceções. Desconfie do nome da tela: descreva o trabalho.

## Saída
Escreva UM arquivo markdown no caminho que lhe foi indicado, com:

### 1. Mapa das funcionalidades (tabela)
`ID | trabalho (verbo + objeto, na língua do operador) | quem | onde/dispositivo | gatilho | frequência | urgência | padrão`

### 2. Ficha de cada trabalho (um bloco por ID; seja denso, sem enrolação)
- **ID e trabalho**
- **Quem** (papel: atendente de balcão, cozinheiro, padeiro/forneiro, gerente, dono, comprador, recebedor, entregador…)
- **Onde** (posto físico e dispositivo hoje; e o dispositivo que faria mais sentido)
- **Gatilho** (evento que chama a ação: cliente chegou, pedido entrou, forno apitou, hora do turno, alerta, rotina diária…)
- **Frequência** (por turno/dia) e **urgência** (segundos, minutos, horas, dias) · **cliente esperando?** (sim/não)
- **Objetivo real** (o que precisa acontecer no mundo; uma frase)
- **Informação mínima para decidir** (só o indispensável) · **o que a tela mostra hoje que sobra** · **o que falta**
- **Entrada do operador** (tipo: escolher de uma lista curta, digitar número, digitar texto, ler código/câmera, contar, assinar/autorizar, confirmar)
- **Efeito** (o que muda no sistema e no mundo) · **reversível?** · **custo do erro** (baixo/médio/alto e por quê)
- **Exceções e bloqueios** (o que pode dar errado e como o sistema trata hoje)
- **Caminho hoje** (passos/toques/telas aproximados) → **caminho mínimo possível** (quantos passos, e qual o único passo que não dá para eliminar)
- **Fronteira** (de que app/etapa o trabalho vem, para qual vai; dado que atravessa)
- **Padrão** (um ou mais rótulos da lista abaixo; proponha rótulo novo se nenhum servir, explicando)
- **Evidência** (arquivos principais, com caminho)

### 3. Padrões que você enxerga neste app
Lista curta: que padrões se repetem, que trabalhos são o MESMO trabalho com nomes diferentes,
onde o app obriga o operador a fazer o que o sistema poderia fazer sozinho, e onde a informação
necessária para decidir não está no lugar da decisão.

### 4. Cobertura
Lista de TODAS as telas/estados do app (rota, estado, diálogo que funciona como tela) e, para cada
uma, em que dispositivo ela faz sentido de verdade (desktop / tablet / celular / parede) e por quê.

## Vocabulário provisório de padrões (use, critique, estenda)
- **VIGIAR** — manter consciência de um fluxo que muda sozinho (fila, quadro, monitor)
- **TRIAR** — decidir o que fazer com um item que chegou (aceitar/recusar/encaminhar)
- **AVANÇAR** — mover um item para a próxima etapa de um ciclo de vida (preparo → pronto → entregue)
- **REGISTRAR-QUANTIDADE** — informar um número que aconteceu no mundo (produzido, contado, recebido, pago)
- **COMPOR** — montar uma transação com várias partes (venda, nota de entrada, campanha, receita)
- **CONFERIR** — comparar o esperado com o real e resolver a diferença (caixa, NF × recebido, fechamento)
- **CONFIGURAR** — ajustar regras/cadastros que valem por muito tempo (catálogo × canal, mínimos, custos)
- **PLANEJAR** — decidir quantidades/ações para o futuro (plano de produção, compras, campanhas)
- **LOCALIZAR** — achar um registro para agir nele (cliente, encomenda, pedido, insumo)
- **ENTENDER** — ler números para decidir (B.I., relatórios)
- **APROVAR** — dar o "sim" de quem tem autoridade (anúncio, desconto, cancelamento pago)
- **CORRIGIR** — desfazer/ajustar algo já feito (estorno, cancelamento, devolução, unificação)
- **AUTORIZAR** — provar quem é (PIN, crachá, gerente)
- **EMITIR** — produzir um documento físico/fiscal (via, etiqueta, NFC-e, comprovante)
- **AVISAR** — chamar a atenção de alguém (alerta, push, som)

Seja exaustivo nos trabalhos (não pule os raros: fechamento, estorno, unificação, configuração),
mas denso na escrita. Responda na sua mensagem final APENAS: caminho do arquivo, número de
trabalhos mapeados e os 5 achados mais importantes (máx. 250 palavras).
