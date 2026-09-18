# Revisão adversarial de UX/UI — app de Marketing (18/09/2026)

- **Escopo:** `surfaces/marketing-nuxt/app/` — `pages/`, `components/`, `presentation/`,
  `utils/`. Lido no `origin/main` em `e0fee913f`.
- **Fora do escopo por pedido:** `components/CampaignForm.vue` (em edição noutra frente).
- **Natureza:** leitura e relatório. Nenhuma linha de produto foi alterada.
- **Régua:** as cinco regras que o dono enunciou esta semana, mais uma sexta que nomeio
  abaixo porque aparece 11 vezes e não cabia em nenhuma das cinco.

## A régua

| # | Defeito | Enunciado do dono |
|---|---|---|
| 1 | **rótulo mente** | "Se 'Disparar agora' não dispara, então é mentira!" |
| 2 | **prolixo** | "Tem que ser breve e diretasso. Elevator pitch elevado ao cubo!" |
| 3 | **grandezas confundidas** | "É óbvio que 50 não serve para contar plataformas para postagens." |
| 4 | **frase incompleta** | "O que significa 'em cada' em '1 postagem em cada'?" |
| 5 | **verbo errado** | "Definir público é um pouco melhor que escolher, né?" |
| 6 | **nota de rodapé do engenheiro** | *(meu)* a frase explica a decisão de arquitetura em vez de dizer o que aconteceu e o que fazer. |

O defeito 6 é o irmão do 2 e merece nome próprio porque tem uma assinatura: a frase
começa afirmando o que o sistema **não** faz — "não inferimos sucesso", "o app não
transforma essa falha em lista vazia", "o sistema nunca troca Stories por Feed sozinho",
"nunca será apresentado como desfeito". É orgulho de engenharia lido pelo padeiro. Ele
não sabia que havia esse risco; agora precisa ler a defesa contra ele.

## Placar

| Defeito | Achados |
|---|---:|
| rótulo mente | 6 |
| grandezas confundidas | 5 |
| verbo errado | 4 |
| nota de rodapé do engenheiro | 11 |
| prolixo | 9 |
| frase incompleta | 3 |
| **Total** | **38** (25 fichas abaixo; as de vocabulário agrupam ocorrências) |

Ordenado por dano: o que faz o gestor concluir errado vem primeiro; o que só é feio vem
por último. **A seção final diz o que examinei e considerei bom** — é metade do
resultado, não cortesia.

---

# Parte A — faz o gestor concluir errado

## A1. Os cinco números do Painel somam pessoas com murais

- **Onde:** `pages/index.vue`, os rótulos dos cartões do topo: `"Entregas confirmadas
  hoje"`, `"Aceitas, ainda sem confirmação"`, `"Falhas finais hoje"`, `"Resultados
  incertos"`.
- **Defeito:** grandezas confundidas (#3).
- **Por que dói:** os quatro números vêm de `counters.*_targets_*` na projection
  (`shopman/backstage/projections/marketing_v2.py`), que conta linhas de `DeliveryTarget`.
  Um destino de WhatsApp é **uma pessoa**; um destino de Instagram, Facebook ou Google é
  **uma postagem**. "12 entregas confirmadas hoje" pode ser 12 pessoas, ou 9 pessoas e 3
  murais. É o primeiro número que o gestor lê de manhã, é o que ele usa para decidir se
  disparou demais, e é justamente o que o contrato da superfície proíbe misturar: "a
  consequência é medida em pessoas que recebem mensagem — nunca em plataformas, que é
  outra grandeza".
- **Substituição:** separar os cartões por grandeza, com o mesmo número já disponível na
  projection por plataforma:
  - `"Pessoas que receberam hoje"` (destinos de WhatsApp confirmados)
  - `"Postagens publicadas hoje"` (destinos de mural confirmados)
  - `"Sem confirmação ainda"` mantém um número só **se** o subtítulo disser de quê:
    `"3 pessoas · 1 postagem"`.
  - Enquanto a projection não separar, o rótulo honesto é
    `"Envios e postagens confirmados hoje"` — feio, mas não mente.

## A2. "Enviado" aparece quando nada foi enviado

- **Onde:** `presentation/marketingResult.ts`, `decisionOutcomeNotice()` — títulos
  `"Enviado"`, `"Publicado"`, `"Disparado"`, com os detalhes `"Mensagens na fila. Cada
  confirmação aparece abaixo."`, `"Postagem na fila. A confirmação aparece abaixo."` e
  `"Mensagens e postagem na fila. Cada confirmação aparece abaixo."`
- **Defeito:** rótulo mente (#1) — o título afirma o ato irreversível concluído e a linha
  de baixo desmente na mesma faixa.
- **Por que dói:** o contrato é explícito: *"'Enviar agora' significa 'na próxima passada'
  e pode levar alguns minutos"* — até ~7 minutos para os primeiros 20 destinos, e mais um
  ciclo a cada 20. O gestor aprova, lê **Enviado** em verde, fecha o app e vai atender o
  balcão. Se a fila travar, ele já concluiu que saiu. A faixa foi construída exatamente
  para não deixá-lo sem saber, e é o título dela que mente.
- **Substituição:** o título vira o gerúndio e o detalhe fica com a promessa:
  - `"Enviando"` · `"As mensagens entraram na fila. Cada confirmação aparece aqui embaixo."`
  - `"Publicando"` · `"A postagem entrou na fila. A confirmação aparece aqui embaixo."`
  - `"Disparando"` · `"Mensagens e postagem na fila. Cada confirmação aparece aqui embaixo."`
  - Quando `delivery.state` assentar, a mesma faixa troca para `"Enviado"` / `"Publicado"`
    — aí é verdade.

**Irmã na mesma tela:** `pages/announcements/[id].vue`, toast `"Entrega autorizada
agora."` A lista de três toasts é `"Anúncio recusado."` / `"Anúncio agendado."` /
`"Entrega autorizada agora."` — dois nomeiam o objeto (anúncio), o terceiro troca para
"entrega", que o vocabulário fechado não aceita como substantivo do objeto.
**Substituição:** `"Anúncio autorizado. Sai nos próximos minutos."`

## A3. "Disparar a campanha X agora" — o botão que não dispara

- **Onde:** `pages/campaigns.vue`, na linha de cada campanha: rótulo visível
  `"Disparar"`, e `aria-label` `"Disparar a campanha {nome} agora"`.
- **Defeito:** rótulo mente (#1). É literalmente a frase que o dono proibiu, viva no nome
  acessível.
- **Por que dói:** `fire` **não entrega** — o contrato diz "modo `none` — cria rascunho em
  revisão e não entrega". O botão abre um painel de público, e o painel cria um anúncio
  para revisão. Quem lê o rótulo visível ("Disparar") acha que está mandando; quem usa
  leitor de tela ouve "agora" e tem certeza. E a prova de que a casa já sabe disso está
  a dois centímetros: a razão do botão desabilitado, em `presentation/campaignFire.ts`,
  já diz a verdade — `"Ligue a campanha antes de preparar um disparo."` O texto vizinho
  fala em *preparar*; o botão fala em *disparar agora*.
- **Substituição:**
  - rótulo visível: `"Preparar disparo"`
  - `aria-label` habilitado: `"Preparar o disparo da campanha {nome}"`
  - o botão desabilitado não pode continuar dizendo `"Indisponível"` (ver D5).

## A4. O remédio das grandezas não chegou ao diálogo irmão

- **Onde:** `components/AnnouncementResultPanel.vue`, no diálogo de recuperação:
  `"Destinos elegíveis"` com o número e a palavra `"destino"` / `"destinos"`, ao lado de
  `"Plataformas afetadas"`.
- **Defeito:** grandezas confundidas (#3) — e o padrão que a casa já conhece: *"o remédio
  é aplicado no site reportado, não no irmão"*.
- **Por que dói:** o `MarketingCommandConfirmationDialog` foi consertado e hoje mostra
  uma linha por destino com a grandeza certa (`WhatsApp · 37 pessoas`, `Instagram · 1
  postagem`). O diálogo de **recuperação** — repetir falhas, consultar incertos, cancelar
  — continua no modelo antigo: um número único chamado "destinos". É o diálogo onde o
  gestor autoriza reenvio; ali a diferença entre "37 pessoas" e "37 postagens" é a
  diferença entre uma conta de WhatsApp e um mural repetido 37 vezes.
- **Substituição:** reusar `reachLines` do diálogo irmão — uma linha por destino:
  `"WhatsApp · 37 pessoas"` / `"Instagram · 1 postagem"`, e o `dt` vira `"O que isto
  alcança"`. Se reusar não couber no PR, o mínimo é trocar `"Destinos elegíveis"` por
  `"Mensagens e postagens afetadas"` — ainda somado, mas sem chamar postagem de destino.

## A5. "Não publica" é o carimbo do WhatsApp

- **Onde:** `pages/platforms.vue`, função `tone()`: `label: "Não publica"` para
  `state === "blocked"`; e `presentation/platformReadiness.ts`, `badge: "não publica"` com
  o texto `"{Plataforma}: {motivo} Não vai publicar por aqui até resolver."` e
  `"... Não vai publicar por aqui até a verificação passar."`
- **Defeito:** verbo errado (#5). Nenhuma das duas funções recebe o `kind` da plataforma,
  então o WhatsApp — que **envia mensagem**, não publica — recebe o mesmo carimbo do
  Instagram.
- **Por que dói:** o gestor vê "WhatsApp · Não publica" e conclui que o problema é de
  postagem, não que **as mensagens não vão sair**. É a plataforma cuja falha custa
  dinheiro e cuja mensagem não se apaga; é a que menos pode ser descrita com o verbo da
  outra. O contrato manda o oposto: "mensagem é uma mensagem direta e possui destinatário;
  publicação é uma postagem pública... esses termos não podem ser trocados na UI".
- **Substituição:** as duas funções passam a receber `kind` (`direct_message` | resto):
  - chip: `"Não envia"` (WhatsApp) · `"Não publica"` (mural)
  - frase: `"WhatsApp: {motivo} Nenhuma mensagem sai por aqui até resolver."` ·
    `"Instagram: {motivo} Nada é publicado por aqui até resolver."`

## A6. "1/1 destinos preparados" no cartão do Instagram

- **Onde:** `components/AnnouncementResultPanel.vue`, no cartão de cada plataforma:
  `"{materialized}/{expected} destinos preparados"`.
- **Defeito:** grandezas confundidas (#3) + jargão (`destino` é `DeliveryTarget`).
- **Por que dói:** no Instagram sempre lerá "1/1 destinos preparados", o que faz o gestor
  procurar o sentido de "destino" num lugar onde só há um mural; no WhatsApp lerá "37/40",
  e o "40" é gente. A mesma palavra, dois mundos, um ao lado do outro na mesma lista.
- **Substituição:** por tipo de plataforma —
  - WhatsApp: `"37 de 40 pessoas na lista"`
  - mural: `"postagem preparada"` (ou `"postagem ainda não preparada"`), sem fração.

## A7. O diálogo que exige duas pessoas e não diz qual é a segunda

- **Onde:** dois textos diferentes para o mesmo estado:
  - `components/MarketingCommandConfirmationDialog.vue`: `"Este volume exige duas
    pessoas."` + `"A confirmação independente continua obrigatória; esta sessão não
    substitui o segundo controle."` (12 palavras)
  - `components/AnnouncementResultPanel.vue`: `"Duas pessoas são obrigatórias para este
    volume."` + `"O comando não será executado nesta sessão sem a confirmação independente
    prevista pelo gate de segurança."` (16 palavras)
- **Defeito:** prolixo (#2) + nota de rodapé do engenheiro (#6) + beco sem saída.
- **Por que dói:** nos dois componentes, `dual_control` força `ready`/`confirmationReady`
  a `false` — o botão de confirmar fica **morto para sempre** nessa caixa. O gestor tem um
  botão apagado, duas frases que explicam o desenho do gate e nenhuma que diga o que
  fazer. A casa tem regra escrita para isso: *botão morto sem frase é defeito*. Aqui há
  frase, e ela não é a que resolve.
- **Substituição:** um texto só, nos dois lugares, que termine no gesto:
  > **"Este disparo precisa de duas pessoas."**
  > "Você já fez a sua parte. Peça a outra pessoa com acesso ao Marketing para abrir este
  > mesmo anúncio e confirmar. Nada sai até lá."

  E o botão morto some: no lugar dele, `"Entendi"`, que fecha a caixa.

## A8. "Atualize os fatos" — ordem sem controle correspondente

- **Onde:** `components/AnnouncementCard.vue`: `"O prazo terminou. Atualize os fatos antes
  de publicar."`
- **Defeito:** verbo errado (#5) — "atualizar os fatos" não é nenhum gesto disponível em
  lugar nenhum do app.
- **Por que dói:** o anúncio expirou porque preço, estoque e disponibilidade foram selados
  há horas. O gestor lê "atualize os fatos", procura o botão, não acha, e conclui que o
  app quebrou. O caminho real é outro: voltar à campanha e preparar um disparo novo.
- **Substituição:** `"O prazo deste anúncio venceu — preço e estoque já podem ter
  mudado. Prepare um disparo novo em Campanhas."` com o link para `/campaigns`.

## A9. O rodapé manda "Aprovar" num card que não tem botão "Aprovar"

- **Onde:** `components/AnnouncementCard.vue`, rodapé: `"Aprovar sela esta versão. Agora,
  ou na hora que você marcar."` Os botões ali são `"Agendar"`, `"Visualizar consequência"`
  e `"Recusar"`.
- **Defeito:** rótulo mente (#1), na direção inversa — a instrução nomeia um controle
  inexistente.
- **Por que dói:** o gestor procura "Aprovar" e encontra "Visualizar consequência", que
  não soa como aprovar nada. Ou ele hesita, ou toca achando que só vai olhar. Ainda:
  "selar" é do ADR, não da padaria.
- **Substituição:** `"O texto que você conferir na próxima tela é o que sai — agora ou na
  hora que você marcar."`

## A10. "Visualizar consequência" — honesto, e ainda assim a palavra errada

- **Onde:** `components/AnnouncementCard.vue`, constante `REVIEW_CONSEQUENCE_LABEL =
  "Visualizar consequência"`, usada nos dois botões do card (imediato e agendamento).
- **Defeito:** verbo errado (#5). Este é o achado que **refuta o padrão**: o rótulo foi
  trocado de propósito para parar de mentir, e a troca funcionou — ele não promete mais
  entrega. Mas trocou uma mentira por uma palavra de documento. "Consequência" é o
  vocabulário da ADR-031; nenhum padeiro abre uma tela para visualizar uma consequência.
- **Por que dói:** custo baixo e real — hesitação. E desperdiça a pergunta que o próprio
  dono fez: *"no último momento, não seria relevante VER o que se está disparando?"* A
  caixa passou a mostrar exatamente isso (texto, foto, hashtags). O botão que a abre
  devia dizer isso.
- **Substituição:** `"Ver o que vai sair"` — e, no agendamento,
  `aria-label="Ver o que vai sair no horário marcado"`.

---

# Parte B — jargão do sistema na tela do padeiro

## B1. "faixa" quer dizer duas coisas no mesmo app

- **Onde:** `presentation/marketingResult.ts`, cinco frases:
  `"Enquanto nenhuma faixa iniciar, o cancelamento ainda pode ser possível."` ·
  `"As faixas que ainda não tinham começado foram preservadas sem envio."` ·
  `"Cancela somente faixas que ainda não começaram. Uma entrega iniciada nunca é
  apresentada como desfeita."` · `"{n} faixas que não tinham começado foram canceladas."` ·
  `"As faixas ainda não iniciadas usam o instante guardado neste comprovante."`
- **Defeito:** grandezas confundidas (#3), na forma mais crua: colisão de termo. "faixa"
  aqui é `lane` traduzido — a fila de entrega de uma plataforma. No **mesmo app**,
  `FireCampaignPanel` tem um bloco chamado **"Faixa de preço"**, que é um conceito real do
  negócio.
- **Por que dói:** o gestor acabou de montar um público por "Faixa de preço" e, minutos
  depois, lê "3 faixas que não tinham começado foram canceladas". A leitura natural é que
  ele cancelou faixas de preço. Ninguém tem motivo para desconfiar de uma palavra que
  acabou de aprender no app.
- **Substituição:** `faixa` → `fila da plataforma`, e sempre nomeada:
  - `"Ainda dá para cancelar: nada começou a sair."`
  - `"As plataformas que ainda não tinham começado não enviaram nada."`
  - `"Cancela só o que ainda não começou a sair. O que já saiu não volta."`
  - `"O envio do Instagram e do WhatsApp foi cancelado antes de começar."`
  - `"As plataformas que ainda não começaram usam o horário deste comprovante."`

## B2. "Escala para SRE" na campainha da padaria

- **Onde:** `components/MarketingNotificationsBell.vue` + `presentation/notifications.ts`:
  a linha `"Escala para {SRE|Operações|Produto|Responsável não definido} em {hora}
  (America/Sao_Paulo)"`, e a linha de cabeçalho de cada alerta,
  `"{Novo|Visto|Assumido|Resolvido} · {Produto|Operações|SRE}"`.
- **Defeito:** nota de rodapé do engenheiro (#6) + verbo errado (#5).
- **Por que dói:** a padaria não tem SRE, não tem time de Produto e não tem escalonamento
  de plantão. O gestor lê que o alerta dele vai "escalar para SRE" às 14h e não tem a
  menor ideia de quem é, nem do que acontece. É vocabulário de página de status de SaaS
  colado num aplicativo de uma pessoa.
- **Substituição:** enquanto a operação for uma pessoa, a linha de dono **sai**; o estado
  fica sozinho (`"Novo"`). Se a escalada precisar aparecer, que apareça como prazo:
  `"Se ninguém decidir até 14:00, o anúncio expira."` — que é o que de fato importa para
  quem lê.
- **Junto:** `"Criado {data} · origem v2"` — a versão da fonte é depuração; sai da linha.
  E `"Assumir"` / `"Assumindo…"` / `"Assumido"` é *acknowledge* traduzido. Proposta:
  botão `"Já vi"`, estado `"Visto"`.

## B3. "aparelho" — quatro violações da regra da casa

- **Onde:** `pages/platforms.vue`: `"Envia uma mensagem a um aparelho verificado. Nunca
  usa público de campanha."` · `"Nenhum aparelho de teste verificado foi configurado."` ·
  o rótulo do campo `"Aparelho verificado"` · a opção `"Escolha o aparelho"`. E
  `composables/useWhatsAppTemplate.ts`: `"O ambiente de teste aceitou. Confira o aparelho;
  aceite ainda não é entrega."`
- **Defeito:** regra explícita do `CLAUDE.md` — **"dispositivo", nunca "aparelho"**, em
  toda superfície de operador, para STRING. Marketing é superfície de operador; a
  concessão de voz própria é só do Storefront.
- **Por que dói:** é a deriva que já custou 104 arquivos em 17/09. A trava que existe
  (`shopman/backstage/tests/test_vocabulario_de_tela.py`) varre **Python**; string de
  `.vue` passa por baixo dela. Não é opinião, é regra escrita, e o Marketing está fora.
- **Substituição:** as quatro trocas diretas — `"dispositivo verificado"`, `"Nenhum
  dispositivo de teste verificado foi configurado."`, `"Dispositivo verificado"`,
  `"Escolha o dispositivo"`, `"Confira o dispositivo"`.
- **Sugestão de seguimento (não deste PR):** estender a varredura de vocabulário aos
  `.vue` das superfícies de operador, senão a regra vale só em metade do sistema.

## B4. "O público está sendo transformado em entregas rastreáveis."

- **Onde:** `presentation/marketingResult.ts`, estado `fanout_pending`: rótulo
  `"Preparando os destinos"`, detalhe acima (8 palavras). O mesmo estado aparece no filtro
  do histórico como `"Preparando destinos"` (`pages/history.vue`).
- **Defeito:** nota de rodapé do engenheiro (#6).
- **Por que dói:** é o estado em que o gestor mais olha a tela — acabou de aprovar e quer
  saber se está andando. O que ele lê descreve a materialização do fan-out. Não há nada
  ali para ele.
- **Substituição:** rótulo `"Montando a lista de quem recebe"`; detalhe `"Leva alguns
  segundos. Depois começam a sair."` Filtro do histórico: `"Montando a lista"`.

## B5. "anterior ao ledger por destino"

- **Onde:** `presentation/marketingResult.ts`, estado `legacy_untracked`: rótulo
  `"Resultado antigo sem rastreamento completo"` + `"Este anúncio é anterior ao ledger por
  destino; não inferimos sucesso sem prova."`
- **Defeito:** nota de rodapé do engenheiro (#6). `ledger`, `destino` e `inferir sucesso`
  numa frase de 13 palavras.
- **Substituição:** rótulo `"Anúncio antigo"`; detalhe `"Não guardamos o resultado dele
  por plataforma. O que aconteceu na época não dá para conferir aqui."`

## B6. Códigos internos que vazaram para a tela

Agrupados porque a correção é a mesma — mandar para o `title` ou apagar:

| Onde | Texto | Substituição |
|---|---|---|
| `AnnouncementPreview.vue` | `"Versão {hash de 8 dígitos}"` | sai da linha; fica só em `title` |
| `AnnouncementResultPanel.vue` | `"Versão"` / `"Versão resultante:"` com o inteiro da projection | sai; o comprovante já identifica |
| `AnnouncementCard.vue` | `"Política {policy_version}"` na sugestão de IA | sai |
| `MarketingNotificationsBell.vue` | `"origem v{n}"` | sai |
| `app.vue` | `shop.view_marketing` em monoespaçado | `"Peça a um responsável o acesso ao Marketing."` |
| `presentation/campaign.ts` | `'{n} pessoas fora por "{chave_em_inglês}"'` | mantém como escape, mas prefixa: `"{n} pessoas fora por um motivo novo ({chave}) — avise quem cuida do sistema."` |

---

# Parte C — prolixo, medido

Contagem de palavras da frase atual → da substituição.

## C1. 48 palavras numa frase só — a campeã

- **Onde:** `presentation/marketingResult.ts`,
  `acceptedAwaitingConfirmationNote()`:
  > "Uma entrega foi aceita pelo provedor: ele recebeu e assumiu a entrega, e a
  > confirmação de que chegou à pessoa vem depois, dele mesmo — quando chegar, aparece
  > neste mesmo quadro, sem você fazer nada. Até lá não reenvie: o reenvio duplicaria a
  > mensagem em vez de apressá-la."
- **48 palavras**, dois dois-pontos, um travessão, três orações subordinadas. Aparece no
  topo do quadro de resultado, que é onde o gestor vai para ter uma resposta rápida.
- **Substituição (16 palavras):**
  > **"O WhatsApp recebeu e vai entregar. A confirmação aparece aqui sozinha. Não reenvie:
  > duplicaria a mensagem."**

## C2. As outras oito, com a conta

| Onde | Texto atual | Palavras | Substituição | Palavras |
|---|---|---:|---|---:|
| `[id].vue` (resultado não abriu) | "Não vamos inferir sucesso enquanto o registro de entrega não responder. O comprovante preservado continua abaixo quando existir." | 18 | "Ainda não sabemos o que saiu. O comprovante continua abaixo." | 10 |
| `[id].vue` (acompanhamento esgotou) | "O registro de entrega ainda não respondeu. Não vamos inferir sucesso sem ele: pode ser só demora da fila." | 19 | "Ainda não sabemos se saiu. Provavelmente é a fila." | 9 |
| `marketingResult.ts` (erro de carga) | "Pode ser uma interrupção de rede ou do serviço. O app não transforma essa falha em lista vazia." | 18 | "Pode ser a rede. Isto não quer dizer que não há nada." | 12 |
| `marketingResult.ts` (404) | "O endereço pode estar incorreto ou o registro pode ter sido removido conforme a política de retenção." | 17 | "O endereço pode estar errado, ou este anúncio já saiu do histórico." | 12 |
| `marketingResult.ts` (plataforma desligada) | "{Plataforma} está desligado neste ambiente: os destinos na fila só podem sair depois que a operação ligar a plataforma." | 19 | "{Plataforma} está desligado. O que está na fila fica parado até alguém religar." | 13 |
| `AnnouncementTemplateForm.vue` (Story) | "O Story usará a foto do produto, que precisa estar em JPEG. Se o produto estiver sem foto, a aprovação será bloqueada antes de qualquer publicação." | 26 | "Usa a foto do produto, em JPEG. Produto sem foto não dá para aprovar." | 14 |
| `AnnouncementTemplateForm.vue` (formatos) | "O sistema nunca troca Stories por Feed sozinho. Facebook usa publicação na página; Google usa atualização padrão do estabelecimento." | 19 | "Facebook publica na página; Google, uma atualização do estabelecimento." | 9 |
| `AnnouncementTemplateForm.vue` (prompt de IA) | "Não inclua preço, validade, estoque, link ou dados pessoais: esses fatos continuam sob controle do sistema." | 16 | "Não escreva preço, validade, estoque nem link — o sistema põe os atuais." | 13 |
| `AnnouncementResultPanel.vue` (motivo) | "Este motivo fica registrado para a equipe entender o que aconteceu." | 11 | "Fica registrado no histórico." | 4 |

## C3. A prévia explica coisas que não estão na tela

- **Onde:** `components/AnnouncementPreview.vue`:
  - `"Modelo aprovado: {nome}. Os campos técnicos exibidos pertencem à mesma versão do
    artefato."` — não há campo técnico algum exibido neste componente; os `provider_fields`
    são mostrados em `pages/platforms.vue`, outra tela. A frase defende algo que o leitor
    não está vendo.
  - `"Fluxo conferido: {nome} · configuração v{n}. Esta é a versão selada para aprovação e
    envio."`
  - `"Campos por destinatário serão resolvidos apenas na etapa protegida de envio."`
  - `"A IA ainda pode sugerir outro texto; qualquer sugestão precisa de nova prévia e
    revisão."`
- **Defeito:** nota de rodapé do engenheiro (#6) + prolixo (#2).
- **Substituição:**
  - `"Modelo aprovado: {nome}."` (apaga a segunda oração)
  - `"Fluxo do WhatsApp: {nome}."`
  - `"Aqui é um exemplo: cada pessoa recebe o nome dela."`
  - `"Se você usar uma sugestão da IA, a prévia refaz."`
- **Junto:** o título `"Prévia fiel"` — "fiel" é uma promessa, não informação. `"Prévia"`.
  E `"Esta plataforma sairá sem imagem nesta versão."` → `"Vai sair sem foto."`

## C4. O carregando que lista o checklist do servidor

- **Onde:** `AnnouncementResultPanel.vue`: `"Conferindo versão, autorização e
  consequência…"`; e `"Confira o escopo calculado pelo servidor antes de autorizar."`;
  e `"Tudo o que foi autorizado e o estado atual estão reunidos aqui."`; e
  `"O comprovante abaixo é a prova persistida desta operação."`
- **Substituição:** `"Conferindo…"` · `"Confira o que isto afeta antes de autorizar."` ·
  *(apaga a terceira: a tabela logo abaixo já é isso)* · `"Este comprovante fica
  guardado."`

## C5. Duas cópias diferentes para a mesma volta de sessão

- **Onde:** o mesmo estado (`pendingReauthentication`) tem dois textos:
  - `pages/index.vue`: `"Guardamos exatamente o anúncio e as edições. Retome para o
    servidor conferir tudo de novo antes de pedir sua confirmação."` (20 palavras)
  - `pages/announcements/[id].vue`: `"O rascunho e a intenção foram preservados. Retome
    para receber uma nova conferência do servidor."` (15 palavras) — "a intenção" é o nome
    interno do comando.
- **Substituição, nos dois:** `"Seu texto e sua escolha estão guardados. Retome para
  confirmar de novo."` (11 palavras)

---

# Parte D — feio, mas não perigoso

## D1. Nove maneiras de dizer "tenta de novo"

Levantamento por varredura, 20 ocorrências, **9 rótulos distintos** para o mesmo gesto:

`"Tentar de novo"` (5×) · `"Tentar novamente"` (7×) · `"Verificar novamente"` (2×) ·
`"Atualizar verificação"` · `"Contar novamente"` · `"Revalidar"` · `"Conferir de novo"` ·
`"Tentar atualizar"` · `"Tentar carregar o resultado"`.

- **Defeito:** #5, diluído. `"Revalidar"` (em `AnnouncementPreview.vue`) é o pior dos
  nove: não é palavra de padaria e não aparece em mais lugar nenhum.
- **Substituição:** dois rótulos, não nove — `"Tentar de novo"` para recarregar o que
  falhou e `"Atualizar"` para buscar o estado novo de algo que já carregou. `"Revalidar"`
  vira `"Tentar de novo"`.

## D2. O "em cada" sobreviveu

- **Onde:** `components/FireCampaignPanel.vue`, no bloco de campanha só-mural:
  `"{n} postagem(ns) pública(s)"` + `"Uma em cada plataforma. Não escolhe contatos."`
- **Defeito:** frase incompleta (#4) — a própria construção que o dono questionou. Com uma
  plataforma só, a tela lê "1 postagem pública / Uma em cada plataforma", e o "em cada"
  fica sem o que distribuir.
- **Substituição:** a frase nomeia as plataformas, e some quando é uma só:
  - uma: `"1 postagem no Instagram. Não escolhe contatos."`
  - várias: `"3 postagens: Instagram, Facebook e Google. Uma em cada. Não escolhe
    contatos."`

## D3. "Publicação" e "postagem" para a mesma coisa

- **Onde:** `AnnouncementCard.vue`: `"Publicação para o público geral da plataforma"` +
  `"Não usa lista de contatos nem envia mensagem direta."` (15 palavras no total).
  `FireCampaignPanel.vue` chama a mesma coisa de `"postagem pública"`; o
  `MarketingCommandConfirmationDialog` também. `AnnouncementTemplateForm.vue` escreve
  `"publicação na página"`; `platforms.vue` escreve `"preparar uma publicação"`.
- **Defeito:** vocabulário (#3/#5). O vocabulário fechado tem **postagem** como o nome do
  resultado público; `publicação` é o termo que sobrou do ciclo anterior — o dono já baniu
  "publicação pública" e a metade solta continua viva.
- **Substituição:** `"Postagem pública. Não escolhe contatos."` (5 palavras, contra 15) —
  exatamente a mesma frase que o painel de disparo já usa. E `"preparar uma publicação"` →
  `"preparar um anúncio"`.

## D4. "Modo de entrega: sim"

- **Onde:** `AnnouncementCard.vue`, `DRAFT_LABELS` → `scheduling: "Modo de entrega"`;
  `DraftRecoveryNotice.vue` renderiza booleano como `"sim"` / `"não"`.
- **Defeito:** frase incompleta (#4). No aviso de conflito de rascunho o gestor lê:
  *"Modo de entrega — Versão atual: não · Seu rascunho: sim"*. Não quer dizer nada.
- **Substituição:** rótulo `"Agendamento"` e uma entrada no `describe` do card mapeando
  `true → "agendado"` e `false → "sair agora"`. O componente já tem a porta certa
  (`describe`), usada hoje só para plataformas.

## D5. Botão cujo rótulo é o estado dele

- **Onde:** `pages/campaigns.vue`: `{{ fireAction(rule)?.enabled ? "Disparar" :
  "Indisponível" }}`.
- **Defeito:** rótulo mente (#1), versão fraca — "Indisponível" descreve o botão, não o
  que ele faria.
- **Por que dói:** o gestor procura na linha o que está indisponível. A razão existe e já
  é impressa por extenso logo abaixo (bom conserto, ver E6), mas o rótulo continua sendo
  um adjetivo.
- **Substituição:** o rótulo não muda com o estado — `"Preparar disparo"` sempre, apagado
  quando desabilitado. Quem explica é a frase de baixo.

## D6. "28 recompra"

- **Onde:** `presentation/campaign.ts`, `AUDIENCE_PARTS` → `["bought_count", "recompra"]`,
  usado em `"12 favoritos, 28 recompra, 3 alertas = 43 clientes"`.
- **Defeito:** concordância. "28 recompra" não é português.
- **Substituição:** `"28 recompraram"`.

## D7. O mesmo rótulo duas vezes, coladinho

- **Onde:** `AnnouncementResultPanel.vue`, seção "Próximo passo": cada item imprime
  `recoveryActionLabel(action)` no `<p>` e de novo no botão ao lado. A tela lê
  `"Consultar 2 resultados incertos"` duas vezes na mesma linha.
- **Substituição:** o `<p>` fica só com a explicação; o rótulo mora no botão.

## D8. Miudezas com endereço

- `pages/history.vue`: `"Não há contagem rastreável por plataforma neste registro."` →
  `"Este registro é antigo e não guarda contagem por plataforma."`
- `pages/history.vue`: filtro `"Origem da decisão"` com a opção `"Automação ou sem
  autoria"` → `"Automação"`; e `historyActorLabel` `"Automação ou origem sem autoria
  registrada"` → `"Disparo automático"`.
- `pages/platforms.vue`: `"Teste não disponível para este papel"` + `"Um Editor habilitado
  ou responsável pelas plataformas pode fazer o teste no ambiente seguro."` → `"Sua conta
  não pode fazer o teste."` + `"Peça a quem cuida das plataformas."`
- `pages/platforms.vue`: `"Nada impede a entrega."` → `"Nada impede o disparo."`
- `MarketingNotificationsBell.vue`: `"Registrando os alertas que ficaram visíveis…"` →
  apagar (é contabilidade interna).
- `AnnouncementCard.vue`: a legenda das plataformas é `"Entregar por"` e a do horário é
  `"Entregar em"`. O mesmo verbo em dois sentidos a três centímetros um do outro →
  `"Sai por"` e `"Sair em"`.
- `AnnouncementCard.vue`: `"Fatos canônicos usados"` (na sugestão de IA) → `"Dados usados"`.
- `AnnouncementCard.vue`: link `"Usar 08:00"` afirma um horário fixo enquanto o valor vem
  de `scheduleResolution.nextAllowedLocal` → `"Usar o próximo horário permitido"`.

---

# Parte E — o que examinei e considerei BOM

Isto não é cortesia: metade do valor de uma auditoria é saber onde **não** mexer, e três
dos consertos abaixo são o padrão que os achados da Parte A deviam copiar.

## E1. A caixa de confirmação hoje mostra o que vai sair — a pergunta do dono, respondida

`components/MarketingCommandConfirmationDialog.vue` é a melhor peça do app. Ela:

- mostra **o texto congelado do comando** (não o que está na tela, que pode ter sido
  editado depois), a foto e as hashtags com a cerquilha, do jeito que saem;
- avisa `"Sem foto"` quando o disparo tem mural e não tem imagem — um fato que, sem isso,
  só apareceria depois de publicado;
- conta a consequência **uma linha por destino, com a grandeza certa de cada um**
  (`WhatsApp · 37 pessoas`, `Instagram · 1 postagem`) e diz no próprio comentário por que
  não junta as plataformas de mural numa linha só: *"obriga o leitor a distribuir o '1'
  entre as duas"*. É a resposta direta à pergunta do "em cada";
- deriva título e botão do **ato real** (`deliveryActionLabel`): `"Enviar agora"` para
  mensagem, `"Publicar agora"` para mural, `"Disparar agora"` só quando faz os dois,
  `"Agendar"` vencendo os três;
- tem descrição de **uma linha** que diz o que acontece depois do botão —
  `"Depois de confirmar, não tem desfazer."` / `"Nada sai agora; vai para revisão."`

**Não mexer.** Os achados A4 e A6 são pedidos para que o resto do app copie esta peça.

## E2. "Definir público" — o verbo consertado, e consertado por inteiro

`pages/campaigns.vue` + `components/FireCampaignPanel.vue`: o painel se chama **"Definir
público"**, e o botão de submissão diz **"Revisar anúncio"** — não "Disparar agora". O
comentário no topo do arquivo registra a razão: *"o botão daqui NÃO dispara: ele cria o
anúncio e leva à revisão"*. É a correção certa, e completa: mudou o título, o verbo e o
destino. **Único resto:** o botão da lista que abre este painel (A3) ficou para trás.

## E3. O número do público aparece enquanto se escolhe

`FireCampaignPanel.vue` conta em tempo real, e — mais importante — **explica o zero**:

- `zeroExplanation()` distingue "ninguém se encaixa" de "as regras acharam 1 pessoa, mas
  ela não pode receber", que são dois problemas diferentes com dois donos diferentes;
- `"Ficam de fora"` lista o motivo por pessoa (`sem consentimento para receber no
  WhatsApp`, `com menos de 18 anos`, `com telefone que não serve para WhatsApp`);
- `exclusionHint()` diz **onde o cliente conserta**: *"o WhatsApp, ele liga em Conta ›
  Preferências"*;
- as parcelas aparecem quando há mais de uma regra, para ensinar que somar alarga e cruzar
  estreita — a única coisa na tela que conta isso.

Copy em português, sem jargão, sem nota de rodapé de engenheiro. É o padrão da casa.

## E4. A prontidão por plataforma é dita antes do clique

`presentation/platformReadiness.ts` + a pílula de `AnnouncementCard.vue`: a plataforma
chega com a cor e a palavra do estado (`desligada`, `ensaio`, `não verificada`) **antes**
de o gestor escolher, e a frase completa aparece sob a escolha, com link para
`/platforms`. A distinção entre "desligada de propósito" e "quebrada" é feita de
propósito, com a justificativa certa no comentário. Só o verbo está errado no caso do
WhatsApp (A5) — a arquitetura da informação está certa.

## E5. "aguardando a plataforma ligar" em vez de "na fila"

`deliveryCountItems()` troca o rótulo `"na fila"` por `"aguardando a plataforma ligar"`
quando a plataforma está desligada. É exatamente o tipo de precisão que falta no resto:
"na fila" sozinho promete que a vez chega; com a plataforma desligada, não chega. Bom.

## E6. A razão do botão morto vai por extenso

`pages/campaigns.vue` imprime `fireState(rule).reason` **abaixo da linha**, em texto, e o
comentário diz por quê: *"a razão morava só no `title` do botão desabilitado, e o Firefox
não mostra tooltip em botão desabilitado"*. É o conserto certo da regra da casa sobre
botão morto — e é justamente o que falta no diálogo de duplo controle (A7).

## E7. Navegação e telas limpas

- `components/CampaignTopBar.vue`: três abas, um substantivo cada — **Painel ·
  Campanhas · Plataformas**. Sem verbos, sem jargão, com a razão de cada nome registrada
  ("Campanhas, não Regras"; "Plataformas, não canais"). Nada a fazer.
- `pages/templates.vue`: a melhor tela simples do app. O estado vazio explica o bloqueio
  que ela existe para resolver (`"Sem pelo menos um, não há como criar campanha."`), e a
  confirmação de apagar mostra **as campanhas que usam o modelo** antes de deixar apagar,
  trocando o botão destrutivo por `"Ver campanhas"`. Um achado só, menor, no formulário
  dela (C2).
- `pages/index.vue`, estados vazios e de erro: `"Nada esperando por você"`,
  `"Não conseguimos carregar o painel."` — curtos, humanos, com o gesto ao lado. O
  problema do Painel são os números do topo (A1), não a copy.
- `components/DraftRecoveryNotice.vue`: nunca imprime JSON, transforma valor composto em
  frase pelo dono do campo, e oferece `"Manter minhas mudanças"` / `"Usar a versão atual
  nos conflitos"` — dois rótulos que dizem o resultado, não o mecanismo. Um rótulo errado
  (D4); o desenho está certo.
- `presentation/campaign.ts` como um todo: o vocabulário de público
  (`"quem está sumindo"`, `"aniversariantes de hoje"`, `"cruzando ..."`) é a linguagem da
  casa. É a camada mais bem escrita do app.

---

## Onde eu procuraria o resto

Duas trilhas que não cabiam nesta leitura e que provavelmente escondem mais do mesmo:

1. **`components/CampaignForm.vue`** ficou fora por pedido. É o maior arquivo do app
   (1.295 linhas) e o irmão direto de duas peças que tinham o defeito (`FireCampaignPanel`,
   `AnnouncementCard`). Vale reler com esta régua depois que a frente atual fechar.
2. **As mensagens de erro vindas do Django.** Boa parte do que a tela mostra em vermelho é
   `detail` do backend (`shopman/shop/api_errors.py` e os comandos do Marketing), não copy
   do Nuxt. Trocar a copy do Nuxt sem olhar o `detail` do servidor conserta metade da
   frase — como já acontece em `platformReadinessNote`, onde a nossa frase é colada no
   `item.reason` do servidor e o resultado é um parágrafo de dois autores.
