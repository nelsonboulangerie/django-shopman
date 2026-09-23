⚠️ **Este PR nasceu sem checks, e isso não é "ainda não começou".** PR aberto pelo
`GITHUB_TOKEN` não dispara workflow de `pull_request` — é regra do GitHub, e ausência de
check se parece com "não começou" quando na verdade é "não vai começar". Para destravar:
**feche e reabra este PR**, ou empurre um commit. Aí os gates rodam.

## O que mudou

Uma linha: `ARG GEOLITE2_SNAPSHOT` no `Dockerfile`, de `@ATUAL@` para `@EDICAO@` — a base
estava com **@IDADE@ dias**. É o bump que invalida a camada do Docker e faz o build baixar
a edição nova; o valor em si não é lido pelo `scripts/fetch-geolite2.sh`.

## Por que isto importa

A base GeoLite2-City, que escreve "Próximo a Londrina, PR · Brasil" ao lado do dispositivo
confiável na tela "Segurança e dados", entra na imagem no build e **não se atualiza
sozinha**. E velha ela não falha — responde **errado em silêncio**.

Todo o resto desta frente falha alto: base ausente não abre, base corrompida levanta
exceção, raio de precisão ruim é descartado. A base velha abre, lê e responde: um bloco de
IP que mudou de operadora continua nomeando a cidade antiga, com raio bom, passando por
todos os filtros que existem. A tela escreve a frase com a autoridade de sempre.

O alvo é grande: **97,87%** das 234.511 redes IPv4 brasileiras estão em blocos `/22` ou
menores (medido na DB-IP Lite 2026-09), e são as alocações pequenas que trocam de mão.

## Sem a chave da MaxMind, este PR continua certo

Se a `MAXMIND_LICENSE_KEY` ainda não estiver configurada, o build sobe **sem base** — a
degradação prevista, com a tela mostrando só navegador e data. O bump não fica errado por
isso; ele passa a valer no dia em que a chave existir. Por isso este workflow não usa a
chave: ele nunca fala com a MaxMind.

## Quem mais vigia isto

`check_geoip_freshness`, no ciclo do `maintenance_worker`, avisa o operador por
`OperatorAlert` aos 21 dias (o mesmo número que dispara este PR) e, aos 90, a cidade deixa
de aparecer na tela. Contexto completo em `docs/guides/geolite2-city.md`.
