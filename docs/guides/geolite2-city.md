# A cidade aproximada do aparelho (GeoLite2-City)

A tela **"Segurança e dados"** da loja (`/conta/seguranca`) escreve, ao lado de cada
aparelho confiável:

```
Chrome no Android                      [Este aparelho]
Próximo a Londrina, PR · Brasil
Último uso em 22/09/2026 às 14:30 · Registrado em 20/09/2026
```

A linha do meio é o assunto deste guia. Ela existe para a pessoa reconhecer o acesso
("fui eu que entrei?") quando o nome do navegador não basta.

## A regra, em uma frase

**O IP do titular não sai da casa.** A cidade é lida de um arquivo dentro da imagem, em
tempo de exibição, e **não é gravada** em lugar nenhum.

## Como chegamos aqui

Até 23/09/2026 esse rótulo vinha do `ip-api.com`: o servidor mandava o IP do titular para
um terceiro, **em HTTP puro**, uma requisição de até 2 s **por aparelho**, bloqueando o
render — e esse terceiro não constava da lista de operadores da política de privacidade,
que se declara "a lista inteira". A **PR #991** removeu a chamada e a linha ficou só com
navegador e data.

No mesmo dia o dono decidiu trazer a cidade de volta **sem terceiro**, com base local, e
**só quando a leitura for confiável**.

## Por que GeoLite2 e não DB-IP Lite

A primeira escolha foi a **DB-IP Lite**, que não exige conta nem chave. Ela foi baixada e
**medida**, e reprovou em dois pontos independentes — 3.000.000 de registros da edição
`dbip-city-lite` de 2026-09:

| campo que a frente precisa | DB-IP Lite | GeoLite2-City |
|---|---|---|
| `location.accuracy_radius` (decide se mostra) | **0 ocorrências** | presente em 242/242 |
| `subdivisions[].iso_code` (a sigla "PR") | **0 ocorrências** — só "Paraná" por extenso | presente |
| `country.names["pt-BR"]` ("Brasil") | ausente | presente |

Sem raio de precisão não há como saber se a leitura serve, e mostrar sempre é justamente o
que a decisão do dono proíbe. Sem a sigla do estado não dá para escrever a frase escolhida.
Cada uma das duas reprovações bastaria sozinha.

A coluna da GeoLite2 foi conferida na **fixture oficial** publicada pela MaxMind
(`GeoLite2-City-Test.mmdb`, do repositório `maxmind/MaxMind-DB`), não em documentação.

**O preço da troca**: a GeoLite2 exige conta gratuita e chave de licença na MaxMind, e essa
chave passa a ser parte do deploy. É o que as seções abaixo descrevem.

## O limiar de confiança: 50 km

`GEOIP_CITY_MAX_ACCURACY_RADIUS_KM = 50` (em `config/settings.py`).

A base devolve, junto com a cidade, um **raio de precisão** em km: a pessoa está em algum
lugar dentro desse círculo. Acima do limiar a linha **não aparece** — nem com ressalva, nem
com "Local aproximado", nem com asterisco.

**O número saiu de medição, não de preferência.** Agrupando por ligação simples as 300
cidades brasileiras com mais blocos de IP (base DB-IP Lite 2026-09; 14.345.887 redes lidas,
9.901 cidades distintas):

| raio | o grupo de Londrina contém |
|---|---|
| 20 km | só Londrina |
| 30 km | só Londrina |
| **50 km** | **só Londrina** |
| 80 km | Londrina, **Maringá** (80 km), **Sarandi** (74 km) |
| 100 km | + Figueira |
| 150 km | 187 âncoras num grupo só, 1.580 km de diâmetro |

Londrina é a cidade da própria frase escolhida pelo dono, e 50 km é o último limiar em que
o nome ainda identifica uma região só. A 80 km "Próximo a Londrina" já pode estar nomeando
Maringá.

Escolher pela cidade vizinha mais próxima seria errado e foi descartado: a mediana da
distância até a vizinha é **2,6 km**, porque a base conta distritos e municípios conurbados
(38 "cidades" a menos de 10 km de Londrina). "Próximo a Londrina" continua verdadeiro em
Cambé — o que não pode é alcançar outra **âncora regional**.

**Efeito colateral, desejado:** IP de saída de operadora de celular costuma vir com raio de
100 km para cima e é descartado automaticamente. Em celular a linha fica só com navegador
e data, que é exatamente o comportamento pedido.

## O arquivo na imagem

- Baixado no **build**, por `scripts/fetch-geolite2.sh`, chamado pelo `Dockerfile`.
- Destino: `/app/data/GeoLite2-City.mmdb` (o default de `GEOIP_CITY_DATABASE_PATH`).
- O download é **verificado por sha256** publicado pela própria MaxMind. Binário de ~60 MB
  que entra na imagem e é lido por código de produção não entra sem conferência.
- **Falha suave**: sem chave, o script sai com 0, a imagem sobe sem a base, e a tela degrada
  para "navegador e data". Build vermelho por causa de um rótulo de cidade seria troca
  péssima.

### Ligar em produção (ação pendente do dono)

1. Criar conta gratuita em maxmind.com e gerar uma **license key** para GeoLite2.
2. No **GitHub**, criar o segredo de repositório `MAXMIND_LICENSE_KEY` (Settings → Secrets
   and variables → Actions). O runbook passo a passo é
   [`docs/plans/WP-MAXMIND-CHAVE-DO-DONO.md`](../plans/WP-MAXMIND-CHAVE-DO-DONO.md).
3. Reconstruir a imagem `web`: rodar o workflow **Deploy images** com
   `components=web`. O log do job `web` diz
   `geolite2: ✓ base em /app/data/… , sha256 conferido.`

⚠️ **Não é no painel da DigitalOcean.** O app vivo (`shopman-nelson`,
`.do/app.alpha-subdomains.yaml`) roda imagem pronta do DOCR, construída no GitHub Actions
(`.github/workflows/deploy-images.yml`); o App Platform não constrói nada. Env
`BUILD_TIME` no painel nunca chega a esse build: a chave ficaria lá, cifrada e sem efeito,
sem erro nenhum. Só o spec `.do/app.subdomains.yaml`, que o App Platform constrói a partir
do `Dockerfile`, lê a chave do painel, e é por isso que só ele a declara.

⚠️ A chave entra por `ARG` do Docker e **não** por segredo de BuildKit. O motivo está
escrito no `Dockerfile`: o mesmo arquivo serve ao spec que o App Platform constrói, não foi
possível provar que aquele builder aceita `--mount=type=secret`, e derrubar o deploy por
causa deste rótulo seria desproporcional. A
consequência é que a chave fica legível no histórico da imagem — é uma chave de licença de
base pública, revogável no painel da MaxMind, sem acesso a dado de cliente, mas **rotacione
se a imagem for publicada em registry de terceiro**.

## A base envelhece — e agora ela avisa

A MaxMind republica a GeoLite2-City **toda terça-feira**. Esta imagem não rebaixa sozinha:
a camada do Docker só refaz quando é invalidada, e com o cache do builder isso pode não
acontecer por meses. Para forçar, bump em `ARG GEOLITE2_SNAPSHOT` no `Dockerfile` (a data
da edição). O valor não é lido pelo script — ele invalida a camada e serve de registro.

Até 23/09/2026 isso era tudo, e o parágrafo acima era a única proteção que existia.
Documentação não é mecanismo: quem lê o guia é quem já foi olhar.

### Por que base velha é pior do que parece

Não é que ela erre muito. É **como** ela erra: em silêncio, e com a cara de quem acertou.

Todo o resto desta frente falha alto — base ausente não abre, base corrompida levanta
exceção, raio de precisão ruim é descartado. A base velha **abre, lê e responde**: um
bloco de IP que mudou de operadora continua nomeando a cidade antiga, com raio bom,
passando por todos os filtros que existem. A tela escreve "Próximo a Londrina, PR ·
Brasil" com a autoridade de sempre e ninguém tem como desconfiar.

E o alvo é grande. Medindo as **234.511 redes IPv4 brasileiras** da DB-IP Lite 2026-09
(14.345.887 redes lidas, 88.123.296 endereços brasileiros cobertos):

| tamanho do bloco | % das redes brasileiras | % dos endereços |
|---|---|---|
| `/24` | **49,71%** | 33,87% |
| `/23` | 10,34% | 14,09% |
| `/22` | 3,79% | 10,32% |
| **`/22` ou menor** | **97,87%** | 62,04% |
| `/16` ou maior | 0,09% | 23,72% |

O espaço brasileiro é dominado por alocações **pequenas** — metade das redes é um `/24`
sozinho —, e são elas que trocam de mão entre operadoras. "Bloco de IP muda de dono" não é
hipótese remota aqui: é a forma do espaço.

⚠️ **O que isso não mede.** Isto é a *exposição*, não a *taxa* de realocação. Medir a taxa
exigiria comparar duas edições da base, e a segunda edição é um download que não foi
feito. A medição justifica **existir** um limiar; a largura dele é julgamento, declarado
abaixo.

### Os dois limiares

Todo `.mmdb` carrega a data em que foi construído (`metadata().build_epoch` — conferido no
arquivo real, não na documentação). É dela que saem os dois gestos:

| idade da base | a tela | o operador | lembrete |
|---|---|---|---|
| < 21 dias | mostra a cidade | nada | — |
| 21 a 89 dias | **mostra** a cidade | `OperatorAlert` `warning` | 7 dias |
| 90 dias ou mais | **não mostra** | `OperatorAlert` `error` | 24 horas |

**21 dias = três publicações perdidas.** Sete dias é o chão físico (abaixo disso não
existe base mais nova) e avisar em sete seria gritar sobre uma semana corrida. Três
publicações seguidas sem bump não é semana corrida — é ninguém cuidando.

**90 dias = o ponto em que o aviso comprovadamente não funcionou.** Entre 21 e 90 cabem
~10 avisos semanais. Se nenhum virou bump, o deployment esqueceu que isto existe. É largo
de propósito: como o bump é manual, um limiar curto deixaria a tela permanentemente muda e
mataria o rótulo na prática. Mas depois de um trimestre, "Próximo a X" errado é pior que
ausência — a cidade errada faz o titular responder "não fui eu" sobre o **próprio** acesso,
que é o oposto exato da função da linha. É a mesma régua que já faz a cidade calar onde o
raio de precisão é ruim.

Os dois vivem em `config/settings.py` (`GEOIP_CITY_STALE_ALERT_DAYS` e
`GEOIP_CITY_MAX_AGE_DAYS`) e aceitam env. Zero desliga a trava.

⚠️ **Data ilegível conta como velha.** Base presente cujo `build_epoch` não se lê não vira
"provavelmente nova": a cidade some e o alerta sai dizendo que a idade é *desconhecida*, em
vez de inventar um número. É a mesma regra do raio ausente — mostrar uma cidade cuja
confiabilidade não se pôde conferir *é* um palpite.

### O que o operador vê, e como resolve

Um alerta em **Alertas operacionais** (Admin), tipo *"Base de cidade dos dispositivos
desatualizada"*, dizendo há quantos dias a base está, o que isso causa na tela, e o gesto:

> A base de cidade dos dispositivos está com 34 dias (construída em 20/08/2026). A cidade
> continua aparecendo, mas a base já perdeu publicações: a MaxMind republica toda terça.
> […] Para atualizar: bump do `ARG GEOLITE2_SNAPSHOT` no Dockerfile (a data da edição
> nova, ex. 2026-10) e novo deploy — é o bump que invalida a camada e rebaixa a base.

Quem grita é `shopman/backstage/management/commands/check_geoip_freshness.py`, no ciclo do
`maintenance_worker` (irmão do `check_integration_drift`). O dedupe é
`(data de construção, faixa)`: bumpar a base recomeça a história, e passar de 21 → 90 dias
é fato novo que sai na hora.

⚠️ **Base AUSENTE não gera alerta**, de propósito. Ausência não é atraso: não há idade e
não há o que bumpar, e é o estado previsto em dev, na CI e em qualquer imagem construída
sem `MAXMIND_LICENSE_KEY`. Alertar ali seria ruído diário sobre um estado conhecido, até o
operador aprender a ignorar o tipo inteiro. A ausência aparece no diagnóstico
(`scripts/diagnose_operational.py`, linha `geoip city database`), que é onde se pergunta.

⚠️ **Isto não entra no `/ready/`.** Prontidão que reprova por causa de um rótulo de cidade
transforma um enfeite em bloqueio de deploy — a mesma troca que o `fetch-geolite2.sh`
recusa quando sai com 0 sem a chave.

### A atualização automática: um PR agendado, e nenhuma peça nova

`.github/workflows/geolite2-refresh.yml` roda às **quartas** (a MaxMind publica às terças),
confere a idade do `GEOLITE2_SNAPSHOT` e, passando de 21 dias, abre um PR bumpando aquela
linha. Branch fixa (`chore/geolite2-snapshot`), um PR por vez.

Não é componente de infraestrutura: é o que o Dependabot já faz para dependência. Um job
que baixasse a base para um volume compartilhado resolveria o mesmo problema criando uma
peça com estado — e a regra da casa é não criar peça sem provar necessidade.

⚠️ **Ele não precisa da `MAXMIND_LICENSE_KEY`.** Não foi "pular com aviso": a chave é
desnecessária aqui. O `GEOLITE2_SNAPSHOT` não é lido pelo `fetch-geolite2.sh` — ele só
invalida a camada. Quem baixa é o build, com a chave dele. Então o workflow nunca fala com
a MaxMind e não tem credencial para faltar; sem chave, o PR continua correto e o build que
sair dele sobe sem base, a degradação prevista de sempre. Um workflow que dependesse da
chave ficaria vermelho toda semana por falta de credencial, e vermelho previsível ensina a
ignorar vermelho.

⚠️ **O PR nasce sem checks.** Evento gerado pelo `GITHUB_TOKEN` não dispara workflow de
`pull_request` — regra do GitHub. Ausência de check se parece com "ainda não começou"
quando é "não vai começar". O corpo do PR diz o gesto na primeira linha: **feche e reabra
o PR**, ou empurre um commit.

## Atribuição e licença

- **GeoLite2** é da MaxMind, distribuída sob a
  [GeoLite2 End User License Agreement](https://www.maxmind.com/en/geolite2/eula). O uso
  aqui é interno (um rótulo na tela do próprio titular), sem redistribuição da base.
- A **DB-IP Lite**, avaliada e não adotada, é CC-BY 4.0 e exigiria atribuição visível. Como
  ela não foi adotada, **não há atribuição a cumprir** nesta frente. Se um dia alguém voltar
  a ela, a atribuição volta junto — e é requisito da licença, não cortesia.

## Onde o código mora

| arquivo | o quê |
|---|---|
| `shopman/shop/services/ip_location.py` | a leitura, a regra de confiança, o leitor aberto uma vez |
| `shopman/shop/services/devices.py` | chama por aparelho; documenta por que não se grava |
| `shopman/storefront/api/account.py` | `approximate_city` no contrato + copy `near_prefix` |
| `shopman/shop/omotenashi/copy.py` | `DEVICE_LIST_NEAR_PREFIX` ("Próximo a"), editável no Admin |
| `surfaces/storefront-nuxt/app/pages/conta/seguranca.vue` | a linha na tela |
| `scripts/fetch-geolite2.sh` · `Dockerfile` | o download no build |
| `shopman/backstage/management/commands/check_geoip_freshness.py` | a base velha vira alerta |
| `.github/workflows/geolite2-refresh.yml` | o PR agendado que bumpa o snapshot |

## Testes que prendem isto

- `shopman/shop/tests/test_ip_location.py` — limiar e sua borda, frase incompleta, IP
  privado que **não consulta a base**, base ausente/corrompida que falha fechado, a base
  que **abre uma vez** para oito aparelhos, e a cidade que **nunca vira coluna** no banco.
- `shopman/storefront/tests/web/test_passkey.py` — as duas metades da decisão: nenhuma
  chamada de rede (com `urlopen` **e soquete** vigiados) e, mesmo assim, a frase chegando
  à tela.
- `shopman/shop/tests/test_ip_location.py` (envelhecimento) — as duas faixas e suas bordas,
  data ilegível que conta como velha, base ausente que **não** é base velha, limiar zerado
  que desliga a trava, e a data lida de um `.mmdb` de verdade (montado byte a byte no
  teste, porque o `maxminddb` só lê e um binário de 60 MB não se versiona).
- `shopman/backstage/tests/test_geoip_freshness.py` — o tipo registrado em `TYPE_CHOICES`
  (sem ele o alerta grava e a coluna do Admin some), as duas severidades, o gesto presente
  em toda variação da mensagem, o dedupe por faixa e por data, e a ausência que cala.
- `shopman/shop/tests/test_no_plaintext_third_party_calls.py` (da PR #991) — segue verde.
  O download do build é `https` e mora em shell, fora da varredura de `.py`: a trava não
  precisou de ajuste nenhum.
