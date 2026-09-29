# WP — a chave da MaxMind (ação do dono, ~10 minutos)

**Status:** aberto, esperando o Pablo. Nada está quebrado enquanto isso.
**Escrito em 23/09/2026.** Este documento se explica sozinho: não é preciso ter
acompanhado a conversa em que a frente nasceu.

---

## 1. O que esta chave liga

Na loja, em **Minha conta → Segurança e dados** (`/conta/seguranca`), cada aparelho
confiável aparece assim:

```
Chrome no Android                          [Este aparelho]
Próximo a Londrina, PR · Brasil
Último uso em 22/09/2026 às 14:30 · Registrado em 20/09/2026
```

A **linha do meio** é o que a chave liga. Ela existe para a cliente responder *"esse
acesso fui eu?"* quando o nome do navegador não basta — duas pessoas da mesma casa usam
Chrome no Android.

### O que acontece hoje, sem a chave

A linha do meio simplesmente **não aparece**. Fica navegador, data do último uso e data
do registro. Nada quebra, nenhum build fica vermelho, nenhum erro é registrado.

Isso é de propósito, e está escrito no código: derrubar um deploy inteiro por falta de um
rótulo de cidade seria uma troca péssima, e ninguém quer descobrir isso às 3 da manhã.
Então o script sai limpo quando não há chave, e a tela degrada.

> **Você pode não fazer isso.** Se decidir que a cidade não vale a conta, feche este WP e
> a tela fica como está. A decisão é sua; o custo de não fazer é zero.

---

## 2. Por que precisa de conta, se a base é gratuita

A base chama-se **GeoLite2-City**, é da MaxMind e é gratuita. Desde 2019 a MaxMind exige
**conta e chave de licença** para baixá-la — não por dinheiro, por rastreabilidade de
quem baixa e aceite dos termos de uso.

A alternativa sem conta (DB-IP Lite) foi testada e **reprovada com medição**: ela não traz
o *raio de precisão*, que é o que faz a cidade **calar** quando a leitura é ruim, e não
traz a sigla do estado ("escreve Paraná, nunca PR"). Sem o raio, a tela mostraria
"Próximo a São Paulo" para alguém em Londrina sempre que o celular saísse pela operadora
— e cidade errada numa tela de segurança **assusta quem não devia ser assustado**. O
detalhe da medição está em [`docs/guides/geolite2-city.md`](../guides/geolite2-city.md).

### O que sai e o que não sai desta casa

**Nada do cliente sai.** A base é um arquivo que entra na imagem no build e é lido do
disco, dentro do nosso servidor, na hora de desenhar a tela. O IP do titular **não é
enviado a ninguém**, e a cidade calculada **não é gravada** em lugar nenhum.

A única coisa que fala com a MaxMind é o **build**, uma vez, para baixar o arquivo — e
nessa conversa não vai nenhum dado de cliente, só "me dá a base".

---

## 3. Os passos

### Passo 1 — conta na MaxMind

1. Vá em **maxmind.com** e crie uma conta gratuita (procure por *GeoLite2* / *Sign up for
   GeoLite2*). Ela pede e-mail, confirmação e o aceite dos termos da GeoLite2.
2. Use um e-mail **da casa**, não pessoal — quem administrar isso depois de você precisa
   conseguir entrar. O mesmo endereço que recebe os avisos do sistema serve.

### Passo 2 — gerar a chave

No portal da conta, procure a área de **chaves de licença** (costuma aparecer como
*Manage License Keys* / *My License Key*) e gere uma chave nova.

- Dê um nome que diga para que serve, por exemplo `shopman-geolite2-build`.
- **Copie a chave na hora.** Chave de licença normalmente só é mostrada uma vez; depois
  disso o caminho é gerar outra.

> ⚠️ Se a tela oferecer a opção "para uso com `geoipupdate`", **não é a que usamos** —
> o nosso build baixa direto. Uma chave comum serve. Se só houver uma opção, use-a: a
> chave é a mesma coisa; o que muda é o programa que a consome.

### Passo 3 — colar no GitHub (e **não** no painel da DigitalOcean)

⚠️ **Corrigido em 23/09/2026, antes de alguém seguir a versão anterior.** A primeira
redação deste passo mandava colar a chave no painel da DigitalOcean como *Build Time*.
Não funcionaria, e **sem erro nenhum**: o app vivo (`shopman-nelson`) não é construído
pela DigitalOcean. A imagem é construída no **GitHub Actions** e só depois vai para o
registry, de onde a DigitalOcean a puxa pronta. O que fica no painel da DO nunca chega ao
build. Conferido no spec vivo (`doctl apps spec get`): todos os componentes são
`image:` do DOCR, nenhum é `dockerfile_path`.

O nome do segredo é exatamente este:

```
MAXMIND_LICENSE_KEY
```

No GitHub, no repositório `nelsonboulangerie/django-shopman`:
**Settings → Secrets and variables → Actions → New repository secret**.

| campo | valor |
|---|---|
| Name | `MAXMIND_LICENSE_KEY` |
| Secret | a chave copiada no passo 2 |

É uma tela só, e não há escopo para escolher: todo segredo de Actions já é lido só
durante o build. O workflow de deploy já está preparado para ler este nome — só falta o
valor.

### Passo 4 — reconstruir a imagem do servidor

A chave só entra na imagem no próximo build **da imagem `web`** (a do Django). Cuidado:
o deploy só reconstrói o que mudou, então o próximo merge no `main` **não basta** se ele
só mexer em telas Nuxt. O caminho certo:

- no GitHub, **Actions → Deploy images → Run workflow**, com `components` = `web`
  (deixe `per_app_images` em `auto`). Leva ~6 min até o ar.

Não precisa bump de data nenhum: o valor da chave faz parte da chave de cache da camada
que baixa a base, então ligar a chave já obriga o build a baixá-la.

---

## 4. Como saber que deu certo

**Duas conferências, do mais barato ao mais definitivo.**

### 4.1 No log do build

No run do **Deploy images** do passo 4, abra o job **`web`**, passo **Build e push**, e
procure por `geolite2`. Com a chave funcionando, aparece a linha de sucesso com o sha256
conferido:

```
geolite2: ✓ base em /app/data/GeoLite2-City.mmdb (… bytes), sha256 conferido.
```

Sem a chave, aparece a mensagem de degradação, e ela diz isso com todas as letras:

```
geolite2: sem MAXMIND_LICENSE_KEY — a imagem sobe SEM a base de cidade.
```

### 4.2 Na tela

Abra a loja, entre na conta, vá em **Segurança e dados**. A linha `Próximo a …` aparece
sob o nome do navegador.

⚠️ **Se não aparecer, não conclua que falhou.** A cidade é omitida de propósito quando a
leitura não é confiável — e isso é comum em celular, porque o IP costuma apontar a saída
da operadora e não a sua rua. Confira por um acesso feito pelo **computador**, em rede
fixa, que é onde a leitura costuma ser boa. Se o log do passo 4.1 disse ✓, a base está lá.

---

## 5. Depois de ligar: o que continua sendo seu

**A base envelhece — mas não em silêncio.** A MaxMind republica a GeoLite2 toda semana.
Base velha não erra sempre; o risco é uma faixa de IP que trocou de operadora nomear a
cidade antiga, com a mesma confiança de uma correta.

Isso deixou de depender de alguém lembrar (PR #1021):

- **aos 21 dias** sem troca, o sistema **avisa o operador** — são três publicações
  perdidas; avisar em 7 seria gritar sobre uma semana corrida;
- **aos 90 dias**, a cidade **some da tela** e volta a ser navegador e data. O sumiço não
  acontece aos 21 de propósito: como o bump é manual, avisar e apagar no mesmo limiar
  deixaria o rótulo permanentemente mudo;
- **toda quarta**, um workflow abre sozinho o PR que sobe a data em `GEOLITE2_SNAPSHOT`.
  Ele **não precisa da chave da MaxMind** — esse campo só invalida a camada da imagem;
  quem baixa é o build.

Na prática, depois de ligar a chave, a sua parte vira **aprovar o PR semanal**. Se ele
parar de aparecer, isso é o sinal.

> ⚙️ Os dois prazos são configuráveis. Se você preferir que a cidade **nunca** suma por
> idade, `GEOIP_CITY_MAX_AGE_DAYS=0` desliga só essa metade e o aviso continua.

**A chave é revogável.** Se por qualquer motivo você quiser cortá-la, o caminho é o portal
da MaxMind, e o efeito é a tela voltar ao estado de hoje — navegador e data.

⚠️ **Um aviso honesto sobre esta chave.** Ela entra na imagem por *build arg*, o que
significa que fica **legível no histórico da imagem**. A escolha está escrita no
`Dockerfile`: a forma tecnicamente melhor (segredo de BuildKit) não pôde ser provada no
builder do App Platform, e um Dockerfile que não constrói derruba o deploy inteiro por
causa de um rótulo de cidade.

O risco real é pequeno — é chave de licença de uma base **pública**, sem acesso a dado de
cliente, e revogável a qualquer momento. Mas por isso: **use uma chave dedicada a isto**,
nunca a mesma de outro serviço, para que revogá-la não derrube nada além disto.

---

## 6. Onde isto mora no código

| o quê | onde |
|---|---|
| o guia técnico completo | [`docs/guides/geolite2-city.md`](../guides/geolite2-city.md) |
| o download, no build | `scripts/fetch-geolite2.sh` |
| a declaração da chave e da data da base | `Dockerfile` (`ARG MAXMIND_LICENSE_KEY`, `ARG GEOLITE2_SNAPSHOT`) |
| a leitura da base e o limiar de 50 km | `shopman/shop/services/ip_location.py` |
| quem passa a chave ao build do app vivo | `.github/workflows/deploy-images.yml` (segredo `MAXMIND_LICENSE_KEY` do repositório) |
| o `key` BUILD_TIME, só no spec que a DO constrói sozinha | `.do/app.subdomains.yaml` (o do app vivo, `.do/app.alpha-subdomains.yaml`, não o declara, e diz por quê) |
| a frase da tela | chave `DEVICE_LIST_NEAR_PREFIX` no Omotenashi (editável no Admin) |

A história de por que a cidade saiu e voltou está no guia: até 23/09/2026 esse rótulo
vinha de um serviço externo que recebia o **IP do titular em HTTP puro**, e que não
constava da lista de operadores da política de privacidade — a lista que se declara "a
lista inteira". A PR #991 tirou o vazamento e trouxe a cidade de volta pelo lado de
dentro.
