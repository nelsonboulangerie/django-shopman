# WP-UX-8, Fase 2: camadas e foco canônicos

**Data:** 05/10/2026

**Escopo:** B.I., Marketing, Gestor, PDV, Compras e `operator-kit`

## Resultado

As superfícies de operador deixam de possuir imports diretos de Reka e overlays manuais
inventariados. Menus, popovers, sheets, diálogos, captura em tela cheia e scrims passam pelo
contrato Shopman do `operator-kit`, sem alterar contratos de API ou regras de negócio.

| evidência mecânica | antes | depois |
|---|---:|---:|
| imports diretos de Reka nos apps | 8 | 0 |
| overlays manuais reais | 8 | 0 |
| árvores locais `components/Ui` | 0 | 0 |

O detector também deixou de contar comentários, seletores CSS e componentes canônicos como
implementações diretas. A trava continua bloqueando um novo `fixed inset-0` usado como camada
fora do kit.

## Decisões

### Estrutura

- `UiPopover` é o contrato de menus contextuais pequenos e ancorados.
- `UiSheet` é o contrato de ações adaptativas: inferior no celular e lateral no desktop.
- `UiDialog` recebe a variante `fullscreen` para scanner e câmera, preservando focus trap,
  Escape, portal, scroll lock e retorno de foco.
- `UiScrim` representa apenas um anteparo semântico e não interativo. Ele não finge ser
  diálogo e não cria outra pilha de foco.

### Aparência

Veredito: **refinar**. A identidade Shopman, os tokens e a densidade foram mantidos. O ganho
visual está na anatomia previsível, no espaçamento interno, na camada única e na adaptação do
mesmo gesto ao dispositivo. Nenhum default de tema do Nuxt UI entrou na superfície.

## Paridade e dispositivos

- Gestor mantém todas as ações de cartão, fila, canal, ordenação, catálogo e detalhe.
- PDV mantém scanner em tela cheia e o fechamento táctil do carrinho.
- Compras mantém contagem, confirmação e captura de nota fiscal.
- B.I. e Marketing mantêm períodos, páginas, gráficos e ações contextuais.
- No desktop, popovers ancorados preservam densidade, teclado e retorno de foco.
- No tablet, sheets e diálogos suportam giro sem depender de hover.
- No celular, ações extensas usam sheet inferior e captura usa `100dvh` com área segura.
- Em estação, Escape e fechamento explícito voltam ao controle disparador.

## Evidência visual

A tela real de Pedidos foi executada contra o backend de demonstração na largura móvel. O menu
do cartão abriu uma vez, com três ações alcançáveis, alvos de 48 px, contraste correto e sem
colisão com o gesto principal. A inspeção mediu o conteúdo ancorado em 240 px de largura e
141,8 px de altura, dentro do viewport. A validação encontrou e eliminou um duplo acionamento
antes desta entrega.

## Testes e build

- `python3 scripts/check_operator_component_ledger.py`: 8 apps, 60 telas e 241 variantes;
  zero import direto, overlay manual ou componente UI local.
- `operator-kit`: 1.224 testes e lint aprovados.
- B.I.: 91 testes, lint, typecheck e build aprovados.
- Marketing: 441 testes, lint, typecheck e build aprovados.
- Gestor: 625 testes, lint, typecheck e build aprovados.
- PDV: 1.604 testes, typecheck e build aprovados; avisos de lint preexistentes preservados.
- Compras: 156 testes, lint, typecheck e build aprovados.

Nenhum contrato de backend mudou. Não há exceção estrutural retida nesta fase.
