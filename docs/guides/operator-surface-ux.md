# Guia canônico de UX/UI para superfícies Nuxt de operador

Este guia é o contrato para uma superfície Nuxt de operador nascer com a
apresentação correta do Shopman. Ele vale para Central, PDV, Cozinha, Gestor,
Produção, Marketing, Compras e B.I., e para qualquer app novo criado nesse
perímetro.

O Storefront fica fora: é superfície de cliente, com voz, rotas e decisões
visuais próprias.

## Regra de ouro

Um app de operador não inventa infraestrutura visual local. Ele compõe telas de
negócio usando o `operator-kit`.

```text
tela do app
    ↓
contrato Shopman no operator-kit
    ↓
Nuxt UI, Reka UI ou HTML semântico
```

Nuxt UI e Reka são infraestrutura. A aparência final continua sendo Shopman:
tokens, densidade, foco, copy, vocabulário, adaptação ao contexto operacional e
comportamento por dispositivo.

## Como criar um app novo

Use sempre o gerador:

```bash
make new-surface name=loyalty label="Fidelidade" subdomain=fidelidade \
  group=operator-office perm=backstage.view_loyalty \
  color="#5B6B2E" symbol=lucide:heart-handshake
```

O gerador registra o app nos lugares que costumam envelhecer em silêncio:

- `surfaces/registry.json`;
- `SURFACES` no `Makefile`;
- matrizes do `surfaces-gate.yml`;
- `operator-router/groups.json`;
- `Dockerfile.operator-group`;
- specs de deploy e hosts;
- `CSRF_TRUSTED_ORIGINS` de desenvolvimento;
- Central, permissões e tile;
- `operator-kit/app-identity.json`;
- PWA, health, BFF e contrato de shell.

Depois da geração, rode:

```bash
make test-surface-registry
make test-surface-versions
make test-operator-components
```

Se o app novo precisa de componente que ainda não existe no `operator-kit`, a
ordem é: criar o contrato canônico no kit, testar ali, e só depois consumir no
app. Não copie um componente local de outro app.

## O que fica no app e o que fica no kit

Fica no app:

- regras de apresentação específicas do domínio;
- projection adapters e composição de blocos;
- labels e textos da tela, dentro do vocabulário canônico;
- dados mockados de teste daquele app;
- rotas, páginas e seleção de seções.

Fica no `operator-kit`:

- botões, campos, seleção, rádio, checkbox, switch e tabs;
- modais, dialogs, sheets, popovers, tooltips, scrims e focus traps;
- steppers, campos de data, hora e período;
- shell de operador, rail, barra inferior, lock, PIN, health e PWA;
- BFF canônico, SSE, retry, erros, conectividade e telemetria;
- tokens, CSS base e contratos compartilhados.

Uma exceção só é aceitável quando melhora um caso operacional real. A exceção
precisa estar documentada e coberta por teste.

## Nuxt UI, Reka UI e aparência Shopman

Cada componente toma duas decisões separadas:

| Decisão | Opções válidas |
|---|---|
| estrutura e comportamento | Nuxt UI, Reka UI ou HTML semântico |
| aparência | Shopman refinado, anatomia Nuxt UI adaptada ou aparência Nuxt UI adaptada |

Use Nuxt UI quando ele reduz estado local, SSR/hidratação continuam corretos e
a customização por slots não vira uma briga contra o componente.

Use Reka diretamente quando a interação precisa de controle operacional fino:
scanner, estação, teclado, toque, focus trap, sheet adaptativo ou navegação por
setas.

Use HTML semântico quando o controle é simples e não tem estado composto.

O app não importa `@nuxt/ui` nem `reka-ui` diretamente. O import direto fica no
`operator-kit`, salvo exceção temporária registrada no ledger.

## Anatomia canônica não é opcional

Customizar tokens não autoriza trocar a anatomia do componente por outro padrão.

O `UiStepper` é o exemplo canônico: círculos, indicadores, títulos e separadores
continuam existindo. A aparência Shopman é aplicada sobre a sequência clássica,
não sobre um card de botões.

Checklist para qualquer wrapper:

- preserva trigger, conteúdo, viewport, item, indicador e separador quando eles
  fazem parte da anatomia;
- preserva papéis ARIA, `aria-current`, `aria-expanded`, `aria-controls` e
  estados desabilitados;
- mantém foco visível por outline real, não só mudança de cor;
- não esconde slot estrutural sem justificar qual problema operacional resolveu;
- usa tokens Shopman para cor, densidade, raio, tipografia e espaçamento.

## Primitivas atuais

Use estes contratos antes de criar qualquer peça nova:

| Necessidade | Contrato |
|---|---|
| ação | `UiButton` |
| texto curto | `UiInput` |
| texto longo | `UiTextarea` |
| escolha curta do sistema | `UiNativeSelect` |
| escolha longa com busca local | `UiSelect` |
| múltipla escolha | `UiCheckbox` |
| escolha exclusiva | `UiRadioGroup` e `UiRadio` |
| liga/desliga | `UiSwitch` |
| abas | `UiTabs`, `UiTabsList`, `UiTabsTrigger`, `UiTabsContent` |
| modal | `UiModal` ou família `Ui/Dialog` |
| folha adaptativa | `UiSheet` |
| menu ancorado | `UiPopover` |
| anteparo | `UiScrim` |
| etapa | `UiStepper` |
| data | `UiDateField` |
| hora | `UiTimeField` |
| data e hora | `UiDateTimeField` |
| período | `UiDateRangeField` |

`UiSelect` é uma exceção operacional controlada. Ele existe porque listas longas
no celular e no chão de operação precisam de busca sem acento, busca por
keywords invisíveis, lista curta sem campo de busca, foco previsível e
fechamento seguro dentro de modal. Se `USelectMenu` passar a entregar a mesma
ergonomia com menos código, a migração deve ser avaliada no `operator-kit`, não
em cada app.

## Dispositivo muda a solução, não só o breakpoint

Responsividade superficial não basta. Cada tela precisa favorecer fortemente o
uso no contexto em que o operador está.

### Desktop com teclado

- ordem de foco estável;
- atalhos visíveis quando existirem;
- hover como melhoria, nunca como única forma de descobrir ação;
- densidade eficiente sem reduzir alvo abaixo de 44 px para controles;
- tabelas e listas com ações previsíveis por teclado.

### Tablet com toque e giro

- alvo confortável para dedo;
- rail quando há largura e barra inferior quando o tablet está em pé;
- sheets e dialogs que sobrevivem ao giro;
- ausência de dependência de hover;
- scroll interno sem prender o operador em camadas.

### Celular

- operação com polegar;
- área segura e `100dvh` quando houver tela cheia;
- teclado virtual sem cobrir ação primária;
- câmera, localização e captura tratados como capacidades do dispositivo;
- ações extensas em sheet inferior;
- nenhuma sobreposição entre botão, rodapé, sticky bar ou texto de apoio.

### Estação ou kiosk

- foco previsível;
- Escape fecha só a camada atual;
- tela cheia recuperável;
- lock e troca de operador sempre alcançáveis;
- estado offline ou stale explícito.

## Omotenashi-first

Omotenashi no operador significa o sistema entender a situação antes de pedir
esforço:

- em Produção e Compras, priorize toque, câmera, giro e trabalho com uma mão;
- no PDV, priorize teclado, velocidade, correção e clareza no balcão;
- na Cozinha, priorize legibilidade à distância, som, foco e estado em tempo real;
- no Gestor, priorize leitura, filtros, ações reversíveis e explicação de risco;
- no B.I., priorize comparação, período, contexto e não só gráfico bonito.

Uma tela nova precisa declarar qual é o gesto principal em desktop, tablet e
celular. Se o gesto muda por dispositivo, a UI também muda.

## Campos de data, hora e período

Não use `input[type=date]`, `input[type=time]` ou `input[type=datetime-local]`
visíveis diretamente em apps de operador. Use:

- `UiDateField` para data;
- `UiTimeField` para hora;
- `UiDateTimeField` para instante local;
- `UiDateRangeField` para período.

Dois campos soltos de data só são aceitáveis quando o caso de uso exige
semânticas diferentes. Para filtro ou vigência, prefira período.

## Busca, filtros e ações

Busca e filtro precisam ser previsíveis entre apps:

- busca textual fica na região de ferramentas ou no topo da lista;
- filtros persistentes precisam mostrar resumo legível;
- ação primária fica clara e não compete com ações destrutivas;
- ação destrutiva exige confirmação quando afeta dado ou operação viva;
- menus contextuais usam `UiPopover`;
- ações longas ou móveis usam `UiSheet`;
- estados vazios explicam o próximo gesto, não só “nenhum item”.

## Validação mínima de uma PR de superfície

Para qualquer app novo ou tela relevante:

```bash
make test-surface-registry
make test-surface-versions
make test-operator-components
cd surfaces/operator-kit && npm test -- --run
cd surfaces/<app>-nuxt && npm run lint
cd surfaces/<app>-nuxt && npm run test -- --run
```

Quando houver comportamento de navegador, rode também o gate e2e do app. Para
Produção, por exemplo:

```bash
cd surfaces/production-nuxt
npm run test:e2e
```

A PR precisa dizer quais perfis foram validados:

- desktop com teclado;
- tablet com toque e giro;
- celular com toque e teclado virtual;
- estação/kiosk quando aplicável.

Print bonito não substitui prova funcional. Teste verde sem cobrir o gesto real
também não prova a UX.

## O que reprova uma revisão

- componente local duplicando peça do `operator-kit`;
- import direto de `@nuxt/ui` ou `reka-ui` no app;
- stepper, dialog, sheet, popover ou select reimplementado numa tela;
- controles nativos de data/hora visíveis ao operador;
- ação que só existe no hover;
- botão ou texto sobreposto em viewport pequeno;
- foco invisível;
- alvo menor que 44 px em toque;
- mobile que só empilha colunas sem repensar o gesto;
- cópia que exige o operador completar contexto;
- mudança visual sem problema operacional nomeado.

## Evidência que deve acompanhar o WP

Ao lançar ou revisar uma superfície, anexe no relatório:

- tela ou rota;
- perfis de dispositivo cobertos;
- famílias de componentes usadas;
- exceções e motivo;
- comandos executados;
- evidência visual quando layout foi alterado;
- riscos que ficaram fora do WP.

Se uma exceção estrutural for mantida, registre no ledger. Dívida conhecida é
melhor que customização invisível.
