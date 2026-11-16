# EXCELÊNCIA: base comum das revisões por app

Este arquivo não se executa sozinho. Cada app tem o seu brief (`EXCELENCIA-<app>.md`), que
aponta para cá e diz o perímetro, as fronteiras e o foco daquele app.

Compromisso: DEV-2026-026. Modelo: Fable 5.2, esforço `high`. Nenhum código de produção.

## O objetivo

Levar o app a um patamar acima dos melhores do mercado. O concorrente que olhar deve pensar
"como não pensei nisso antes?". A régua tem três partes:

- **Zero quebra de contrato**: o que a tela, a API e a projection dizem é verdade e continua
  verdade até o fim do fluxo.
- **Zero quebra de expectativa**: nada que o usuário precise lembrar, adivinhar ou refazer.
- **Zero beco sem saída**: todo estado tem a próxima ação ao lado.

**O ponto mais sensível é a promessa sobre produção dinâmica.** Pão e produto de fornada têm
reposição longa e validade curtíssima, e o produto efêmero existe só numa janela. Tudo o que a
tela promete (disponível, quantidade, dia, horário, "fica pronto às…") precisa bater com a
verdade da produção e do estoque: fornada, saldo, reserva e validade. Isso vale no momento em
que a promessa é feita e até a entrega.

## As lentes

Todo achado se classifica em uma delas:

- UX/UI;
- copy: `docs/reference/omotenashi-copy.md` e `docs/reference/suite-vocabulary.md`;
- contrato: `docs/reference/projection-contracts.md` e o contrato de superfície do app;
- segurança e permissão;
- omotenashi-first: antecipar, não perguntar o óbvio;
- mobile-first, de 375 px para cima;
- continuidade do fluxo;
- a promessa de produção.

Os princípios da casa estão no CLAUDE.md e não se repetem aqui.

## Método

1. **Meça antes de opinar.** Monte uma pilha isolada, com as portas e o banco que o brief do
   app dá, e rode o seed. Percorra as jornadas do brief **pela UI**, em 375 px e em 1366 px,
   cruzando as horas que mudam a regra: abertura, corte, fechamento e virada do dia. Cada
   achado tem prova: uma captura, ou `caminho:linha`.
2. **Leia o histórico do app** (laudos, PRs e decisões que o brief cita). Não reaudite o que já
   foi corrigido. Confira cada item contra o `main` de hoje antes de listá-lo.
3. **Pesquise os benchmarks** citados no brief: o que eles fazem melhor e o que nenhum deles
   faz. Neste ponto, a fonte é a referência, nunca a cópia.
4. **Ataque o desenho, não só a tela.** Quando um defeito volta em várias telas, a causa está
   no contrato ou no eixo do conceito. Proponha a correção ali.

## Entregue

`docs/plans/EXCELENCIA-<APP>-PLANO.md`, num PR, com:

1. **Laudo**: os achados P0, P1 e P2, cada um com a lente, a prova e a causa no código.
2. **O salto**: até cinco ideias que tiram o app do "correto" para o "uau", cada uma com o
   ganho para o usuário e o custo.
3. **WPs**, cada um cabendo numa sessão Opus 5.5, um branch e um PR, com:
   - objetivo em uma frase;
   - achados que fecha;
   - dependências;
   - arquivos que toca;
   - fora do escopo;
   - pronto quando: o teste ou o roteiro pela UI que prova;
   - se muda tela (se sim, o WP inclui prévia local ao dono antes de enfileirar);
   - tamanho;
   - um brief para a sessão Opus, que aponta o que ler e não copia o CLAUDE.md.
4. **Ondas**: o que corre em paralelo. Dois WPs da mesma onda nunca tocam o mesmo arquivo.
5. **Decisões do dono**: no máximo seis, só as que bloqueiam um WP e que nenhum documento já
   respondeu. Cada uma respondível com sim/1/2, com a recomendação primeiro. Antes de
   perguntar, procure em `docs/coordination/DECISIONS.md` e em `docs/reference/`.

## Perímetro

O trabalho é **só do app do brief**. O que pertence a outro app, ao `operator-kit`, aos
services do `shop` ou ao Core (`packages/`) não vira WP deste plano. Vira uma seção
**Fronteiras**: o que é, por que afeta este app, de quem é e quais outros apps sente a mudança.
Três revisões irmãs rodam em paralelo (PDV, Gestor de pedidos, Storefront), cada uma no seu
perímetro.

## Limites

- Nenhuma chamada paga a modelo, nenhum SMS, e-mail ou WhatsApp real, nenhum pagamento real.
- Banco do alpha: só leitura, pela conexão direta 25060. Nada de reseed.
- Use só as portas e o banco do seu brief: as revisões irmãs estão rodando ao mesmo tempo.

## No chat, ao terminar

Em um parágrafo: quantos achados P0 e P1, a ideia do salto que mais impressiona, quantos WPs
e ondas, e o primeiro a delegar. Depois, as decisões do dono.
