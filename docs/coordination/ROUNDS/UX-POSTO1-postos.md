# UX-POSTO1 · Postos de trabalho

Branch `claude/ux-posto1-postos`, PR #1429.

Objetivo (SUITE-UX §9, §16, L6, L7; decisão do dono, 03/10): o posto deixa de ser
"um caixa" e vira objeto próprio (Caixa, Expedição, estações da Cozinha, salas da
Produção, Escritório), com o Caixa amarrado ao `Terminal` para gaveta e turno e os
demais postos sem gaveta nem turno. Provisionar em todos os apps de operador, com os
postos adequados a cada app e um posto só por dispositivo. Rótulos e copy numa fonte
única, para renomear em uma linha.

## O que mudou

### Modelo (backstage, Core intocado)

- `shopman/backstage/models/workstation.py`: `Workstation` (`ref`, `label`, `kind`,
  `terminal` OneToOne opcional, `metadata`, `is_active`). `kind` sem `choices` de
  propósito: o rótulo mora na fonte única e renomear não vira migração.
- Tipos: `cash_desk` (Caixa), `service` (Atendimento), `dispatch` (Expedição),
  `kitchen_station` (Estação da Cozinha), `production_room` (Sala da Produção),
  `office` (Escritório). Não existe Doca.
- **O cookie não mudou.** `TrustedDevice.subject_id` passa a ser lido como
  `Workstation.ref`; o posto de um caixa tem o mesmo ref do `Terminal`. Por isso todo
  tablet já provisionado continua reconhecido sem refazer nada, e todo código que
  procura a gaveta por `Terminal.objects.filter(ref=station_ref)` continua certo.
- **Posto sem caixa nunca abre gaveta nem turno**: as mutações de dinheiro já exigem
  que o ref da estação seja um `Terminal` ativo (`_terminal_do_pedido`), e o ref de um
  posto sem caixa nunca é: `Workstation.clean` recusa a colisão e um `pre_save` em
  `Terminal` recusa um caixa novo com o ref de um posto sem caixa.
- Todo `Terminal` novo ganha o seu posto Caixa (`post_save`), inclusive o
  `Terminal.default()`.
- Migração `backstage.0081_workstation`: cria um posto por `Terminal` existente (mesmo
  ref; terminal autônomo vira Sala da Produção, os demais Caixa) e leva
  `Terminal.metadata["gestor_board"]` para `Workstation.metadata["gestor_board"]`
  (reversível). Numeração conferida contra `origin/main`.
- Desativar um posto solta todos os dispositivos dele.

### Fonte única das palavras

- `shopman/backstage/workstation_vocabulary.py`: `KIND_LABELS`, `SURFACE_KINDS` (que
  postos cada app oferece) e `COPY` (tela de fixar, contexto do rail, cadastro).
- Espelho tipado só das CHAVES em `surfaces/operator-kit/app/presentation/workstation.ts`,
  com teste que confere contra o Python.
- Copy proposta (em validação pelo dono): "Este dispositivo fica em qual posto?",
  "Escolha uma vez. Depois ele abre direto no trabalho deste posto e pede só o PIN de
  quem for operar.", "Fixar neste posto", "Agora não", "Posto Expedição", "Soltar
  deste posto".

### Provisionar em todos os apps (kit)

- `GET/POST/DELETE /api/v1/backstage/operator/station/` agora fala de posto
  (`?surface=<app>`, `workstation_ref`); a segunda palavra (D-007) só vale para o
  Caixa, que divide gaveta e turno.
- A antessala (`operator/session/`) devolve `workstation` (com `context_label`).
- `OperatorStationSetup` (kit) reescrito: overlay de tela cheia, botões crus (o kit não
  alcança a `UiButton` de cada app), copy do servidor, estado vazio que aponta para o
  cadastro, e `unavailable` no 403.
- `useStationSetupOffer` (kit): a mesma regra nos oito apps; "Agora não" lembrado no
  navegador.
- Ligado no PDV, Central, Cozinha (fora do painel de retirada), Gestor, Produção (fora
  do Letreiro), Marketing, Compras e B.I.
- O rail mostra o posto como contexto ("Posto Expedição"), lido da antessala.
- Oferta por app: Central todos; PDV Caixa e Atendimento; Cozinha Estação e
  Expedição; Gestor Expedição e Escritório; Produção Sala; Marketing, Compras e B.I.
  Escritório.

### Cadastro em Ajustes: Gestor › Postos

- API `GET/POST /api/v1/backstage/workstations/`, `PATCH .../<ref>/`,
  `DELETE .../<ref>/devices/<id>/`, permissão `cashman.manage_operators`.
- Página `surfaces/orders-nuxt/app/pages/workstations.vue`: criar, renomear, mudar o
  tipo, desativar/reativar, ver dispositivos e "Soltar deste posto". Aba "Postos" na
  barra do Gestor só para quem gere operadores (pergunta à antessala, como Clientes).
- **Por que no Gestor e não na Central:** a Central é launcher e fila ("Precisa de
  você"), sem cadastro; o Gestor já é onde o escritório ajusta a operação (Catálogo,
  Canais, Clientes) e é onde o §15/§16 põem a Expedição. O posto Caixa não nasce aqui:
  nasce com o caixa (config de gaveta e hardware, no Admin do terminal).

## Ficou de fora (e por quê)

- **Abrir direto no trabalho do posto (L6, item 5 do brief):** fica para o PR
  seguinte. O posto agora existe e chega à tela (`session.workstation.kind`); falta
  cada app escolher a rota inicial por tipo, o que depende da decisão do dono sobre o
  nome e a casa da Expedição.
- **Modo autônomo por posto:** o bloco `station` (atendida/autônoma) continua em
  `Terminal.metadata`. Uma Sala da Produção nova, sem caixa, é sempre atendida. Mover
  isso para o posto é revisão de segurança própria (ver `PRODUCTION_API_PREFIX`).
- **Workstation no Admin:** não registrado (o gate canônico do Unfold pede inventário
  próprio); o operador não precisa, e o Admin do terminal segue listando os
  dispositivos do caixa.
- O rótulo da aba "Postos" na barra do Gestor é literal no front (a aba precisa
  existir antes de qualquer leitura); todo o resto da copy vem do servidor.

## Evidência

(preenchida no fechamento)
