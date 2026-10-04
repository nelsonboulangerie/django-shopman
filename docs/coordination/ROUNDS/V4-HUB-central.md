# V4-HUB: a Central igual à prévia v4

- **id:** V4-HUB
- **branch:** claude/v4-hub
- **estado:** PR aberto, auto-merge (onda V4, merge autorizado pelo dono)
- **início (UTC):** 2026-10-04

## Objetivo
Onda V4 ("quero tudo igual à v4"): a Central (`surfaces/hub-nuxt`) veste a camada visual da
suíte (`data-suite="v3"`, UX-KIT-V1/V2) e fica igual à prévia `docs/plans/suite-ux-v2/v4/hub.jpg`
(`fontes/v4/hub4.html`, "a fila das filas"), em desktop, tablet e celular, claro e escuro.

## O que entrou
**Central:** `data-suite="v3"`; `OperatorSuiteRail` no lugar do `OperatorRail` + `RailToggle`
("Início" como única seção, Avisos e o menu do operador no pé, sem Bloquear: a Central não trava
operador); cabeçalho de 76px com a saudação (`op-heading`) e a linha fina com o ponto ao vivo, a
hora, o dia e a assinatura "Shopman · Nelson"; "Precisa de você" com as medidas da prévia (linha
de 56px, ícone de 28px, coluna do app, tempo de 108px, gesto de 164px com seta); blocos dos apps
com o desenho da prévia (raio 14px, ícone de 40px, estado no pé do bloco, seta de link externo na
Loja) e a frase "Quem tem um app só..."; rodapé calmo com avisos neste dispositivo numa linha e a
versão. O rail começa aberto (o `railDefaultState: "collapsed"` da Central saiu). O ícone que
falha antes da hidratação agora cai no Lucide (antes ficava o ícone quebrado do navegador).

**Kit (aditivo):**
- `OperatorSuiteRail`: prop `lockable` (padrão `true`); `false` esconde Bloquear e mantém as iniciais.
- `OperatorPushSettings`: prop `variant` (`card` padrão, `line` novo): a linha do rodapé, com o
  gesto que cabe ao estado (ativar aqui, ou abrir o que chega e os dispositivos logo abaixo).
- `OperatorStationSetup` (#1429): cartão da suíte atrás de `suite:` (vale para quem migrou: Gestor
  e Central).

## Função (não regride)
Avisos do dispositivo: ativar, categorias e remover dispositivo seguem a um toque (linha do
rodapé). Tema, giro e ocultar a barra no menu das iniciais; "Mostrar a barra" no cabeçalho quando
oculta. Sino de avisos (novo na Central, peça do kit) no rail e, no celular, no cabeçalho. Login,
falhas classificadas, oferta de posto, poll da fila e reconexão intactos.

## Fora daqui (com nome e motivo)
- Busca da suíte no cabeçalho: recurso novo (também fora no Gestor).
- Atalhos no rail: não há painel de atalhos no kit.
- Estado dos blocos de Compras, Marketing, B.I. e Loja: `hub_queue.py` não tem fonte para eles.
- Ponto verde de estado positivo: o contrato do bloco só tem "pede alguém" e "resto calmo".

## Prova visual
`scratchpad/ux/v4-hub/index.html` da sessão coordenadora (+ `img/`).
