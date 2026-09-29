# Player de menuboard — Raspberry Pi 4 + 2 Samsung The Frame

Um único Pi abre dois Chromiums independentes e controla uma TV por HDMI. A
política continua no Shopman: o player só pergunta se deve manter cada saída
acordada. Fora do expediente, o marquee aparece primeiro; após o atraso local
(30 minutos por padrão), o Pi manda a TV para standby. Ele volta a acordá-la
15 minutos antes da abertura.

O Pi **não desliga**. Assim não há boot diário, seleção manual de fonte nem risco
de abrir a imagem errada. Se a rede cair enquanto as TVs dormem, o último
horário de retorno fica em memória e o player acorda a tela quando ele chegar.

## Limite específico da The Frame

Samsung chama HDMI-CEC de **Anynet+**. Ligue em *Configurações → Geral →
Gerenciador de Dispositivos Externos → Anynet+ (HDMI-CEC)*. Dependendo da geração
e das opções do Art Mode, o comando CEC de standby pode apagar o painel ou abrir
o Art Mode. Isso precisa de um teste nas duas TVs; se quiser painel realmente
apagado, desative o Art Mode automático/sensor nessa janela. O comando de ligar
e assumir a entrada HDMI continua sendo enviado pelo Pi.

Controle por SmartThings não faz parte deste player: exigiria conta, nuvem e
tokens Samsung. HDMI-CEC é local e continua funcionando sem internet.

## 1. Preparar o Pi

Use Raspberry Pi OS 64-bit com desktop e sessão automática. No Pi 4, ligue a TV
do Café no HDMI 0 e a do Salão no HDMI 1. Para manter as duas saídas mesmo com
uma TV em standby, acrescente ao fim de `/boot/firmware/cmdline.txt` (na **mesma
linha**):

```text
video=HDMI-A-1:1920x1080M@60D video=HDMI-A-2:1920x1080M@60D
```

O posicionamento explícito de duas janelas é mais previsível em X11. Em
`raspi-config`, selecione *Advanced Options → Wayland → X11* e reinicie.
Depois, em *Preferences → Screen Configuration*, desative o espelhamento e
organize HDMI-1 à esquerda de HDMI-2, ambas em 1920×1080. Confira com `xrandr`:
o desktop combinado deve medir 3840×1080.

```bash
sudo apt update
sudo apt install chromium libcec6 cec-utils
cec-client -l
ls -l /dev/cec0 /dev/cec1
```

`cec-client -l` deve enxergar dois adaptadores. Confirme qual conector corresponde
a `/dev/cec0` e `/dev/cec1`; se vierem invertidos, troque apenas esses valores no
JSON. Um teste seguro, com a TV correta à vista:

```bash
printf 'on 0\nas\n' | cec-client -s -d 1 /dev/cec0
printf 'standby 0\n' | cec-client -s -d 1 /dev/cec0
```

## 2. Emitir a configuração no servidor

Na release do Shopman, use as refs reais dos dois quadros e a origem pública:

```bash
python manage.py issue_menuboard_player_credential tv-cafe tv-salao \
  --server-url https://gestor.example \
  --label 'Raspberry Pi 4 · Menuboards'
```

O comando imprime um JSON uma vez. Copie-o para o Pi em
`~/.config/nelson-menuboard-player/player.json` e proteja o arquivo:

```bash
install -d -m 700 ~/.config/nelson-menuboard-player
chmod 600 ~/.config/nelson-menuboard-player/player.json
```

Cada Bearer é exclusivo de um quadro, expira em um ano e só abre o endpoint de
controle. Ele **não** abre o cardápio, produtos, preços ou eventos.

## 3. Autorizar os dois perfis do Chromium

Cada tela tem um perfil próprio. Faça uma única entrada de operador em cada um;
ao abrir o menuboard logado, o Shopman grava o cookie durável daquela TV:

```bash
chromium --user-data-dir="$HOME/.local/share/nelson-menuboard-player/profiles/tv-cafe" \
  'https://gestor.example/admin/login/?next=/menuboard/tv-cafe/'

chromium --user-data-dir="$HOME/.local/share/nelson-menuboard-player/profiles/tv-salao" \
  'https://gestor.example/admin/login/?next=/menuboard/tv-salao/'
```

Feche cada Chromium depois de confirmar a tela. Autorizar um quadro não abre o
outro. Se a autorização expirar, repita somente este passo.

## 4. Instalar e conferir

Copie `player.py` para `~/.local/share/nelson-menuboard-player/player.py`. Antes
de instalar o serviço, rode o diagnóstico:

```bash
python3 ~/.local/share/nelson-menuboard-player/player.py \
  --config ~/.config/nelson-menuboard-player/player.json --doctor
```

Para inspecionar comandos sem abrir janelas nem tocar nas TVs:

```bash
python3 ~/.local/share/nelson-menuboard-player/player.py \
  --config ~/.config/nelson-menuboard-player/player.json --dry-run --once
```

Instale a unit como serviço do usuário da sessão gráfica:

```bash
install -d ~/.config/systemd/user
cp nelson-menuboard-player.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now nelson-menuboard-player.service
journalctl --user -u nelson-menuboard-player.service -f
```

O Gestor passa a mostrar separadamente a TV que buscou o quadro e o player do
Raspberry Pi que controla energia. Se o player ficar mais de cinco minutos sem
contato, aparece uma pendência no card do canal.

## Configuração

```json
{
  "server_url": "https://gestor.example",
  "poll_seconds": 30,
  "standby_delay_minutes": 30,
  "chromium": "chromium",
  "screens": [
    {
      "ref": "tv-cafe",
      "cec_adapter": "/dev/cec0",
      "token": "…",
      "window_position": "0,0",
      "window_size": "1920,1080"
    },
    {
      "ref": "tv-salao",
      "cec_adapter": "/dev/cec1",
      "token": "…",
      "window_position": "1920,0",
      "window_size": "1920,1080"
    }
  ]
}
```

Se quiser manter o marquee por mais ou menos tempo antes do standby, altere
somente `standby_delay_minutes`. O horário de abrir/fechar e as frases continuam
sendo configurados no Gestor.
