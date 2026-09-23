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
2. No painel do DigitalOcean, definir `MAXMIND_LICENSE_KEY` como env **BUILD_TIME**
   (o `key` já está declarado nos dois specs de `.do/`, valuless, como todo SECRET da casa).
3. Rebuild. O log do build diz `geolite2: ✓ base em /app/data/… , sha256 conferido.`

⚠️ A chave entra por `ARG` do Docker e **não** por segredo de BuildKit. O motivo está
escrito no `Dockerfile`: não foi possível provar que o builder do App Platform aceita
`--mount=type=secret`, e derrubar o deploy por causa deste rótulo seria desproporcional. A
consequência é que a chave fica legível no histórico da imagem — é uma chave de licença de
base pública, revogável no painel da MaxMind, sem acesso a dado de cliente, mas **rotacione
se a imagem for publicada em registry de terceiro**.

## ⚠️ Atualização: NÃO é automática

Isto é dito com todas as letras porque o contrário se supõe.

A MaxMind republica a GeoLite2-City **toda terça-feira**. Esta imagem **não** rebaixa
sozinha: a camada do Docker só refaz quando é invalidada, e com o cache do builder isso
pode não acontecer por meses. **Não existe job agendado, nem Dependabot, nem alerta de base
velha.**

Para forçar a atualização, bump em `ARG GEOLITE2_SNAPSHOT` no `Dockerfile` (use a data da
edição). O valor não é lido pelo script — ele existe para invalidar a camada, e serve de
registro de quando a base da imagem foi trocada pela última vez.

**O que uma base velha causa:** não é rótulo errado em massa — o filtro por raio continua
valendo. É o caso pontual de uma faixa de IP realocada entre operadoras, que passa a nomear
a cidade antiga. Para uma linha de reconhecimento de acesso, o risco é baixo; para não ser
esquecido, é este parágrafo.

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

## Testes que prendem isto

- `shopman/shop/tests/test_ip_location.py` — limiar e sua borda, frase incompleta, IP
  privado que **não consulta a base**, base ausente/corrompida que falha fechado, a base
  que **abre uma vez** para oito aparelhos, e a cidade que **nunca vira coluna** no banco.
- `shopman/storefront/tests/web/test_passkey.py` — as duas metades da decisão: nenhuma
  chamada de rede (com `urlopen` **e soquete** vigiados) e, mesmo assim, a frase chegando
  à tela.
- `shopman/shop/tests/test_no_plaintext_third_party_calls.py` (da PR #991) — segue verde.
  O download do build é `https` e mora em shell, fora da varredura de `.py`: a trava não
  precisou de ajuste nenhum.
