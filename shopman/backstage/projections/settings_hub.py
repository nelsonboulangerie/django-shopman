"""Projection da tela de Configuração — o mapa do que se ajusta nesta loja.

Config e dado disputavam o mesmo menu, e essa disputa era o que obrigava o gestor
a decidir "isso que eu procuro é um ajuste ou é um dado?" antes de conseguir
procurar. Para *Promoções* essa pergunta não tem resposta óbvia, e a dúvida
custava a busca inteira. Aqui a configuração vira destino próprio: sai do menu de
operação e ganha uma tela onde se lê o que existe em vez de lembrar onde estava.

Os grupos são por ESCOPO — o que a loja é, como ela vende, como ela entrega, o que
ela diz, o que ela fabrica, com que equipamento, quem entra. Não por app Python e
não por "ser config": todo mundo aqui é config, então isso não distingue nada.

Cada cartão carrega uma frase do que ele controla. Sem ela, uma grade de trinta
títulos é uma lista de menu deitada — o texto é o que deixa reconhecer a tela sem
abrir. Esta projection é também a fonte única de "o que é configuração": o teste
de navegação a consulta para garantir que nenhuma tela registrada fica fora do
menu E fora daqui.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class SettingsEntry:
    """Um cartão: para onde vai, o que controla, com que cara."""

    label: str
    url_name: str
    description: str
    icon: str
    is_custom_page: bool = False

    @property
    def url(self) -> str:
        return reverse(self.url_name)


@dataclass(frozen=True)
class SettingsGroup:
    title: str
    hint: str
    icon: str
    entries: tuple[SettingsEntry, ...] = field(default_factory=tuple)

    #: Pedaço da URL do escopo. Em INGLÊS por convenção do projeto ("URL é em
    #: inglês. Ponto." — CLAUDE.md): o TÍTULO da tela segue em português, o
    #: caminho não. Derivar do título geraria `/admin/settings/como-vendemos/`.
    slug: str = ""


def _model(label: str, app_model: str, description: str, icon: str) -> SettingsEntry:
    return SettingsEntry(
        label=label,
        url_name=f"admin:{app_model}_changelist",
        description=description,
        icon=icon,
    )


SETTINGS_MAP: tuple[SettingsGroup, ...] = (
    SettingsGroup(
        title="A loja",
        slug="store",
        hint="Quem somos, quando abrimos, o que servimos.",
        icon="storefront",
        entries=(
            _model("Loja e contato", "shop_shop", "Nome, telefone, endereço e documento da casa.", "store"),
            _model("Marca e aparência", "shop_shopappearance", "Logo, cores e a voz que a loja usa com o cliente.", "palette"),
            _model("Horários e operação", "shop_shopoperation", "Dias e horas de funcionamento, feriados e fechamentos.", "schedule"),
            _model("Cardápio", "shop_shopmenu", "Coleções que aparecem na loja e como o cardápio se monta.", "restaurant_menu"),
            _model("Integrações", "shop_shopintegrations", "Serviços externos: pagamento, mensagens, iFood.", "extension"),
        ),
    ),
    SettingsGroup(
        title="Como vendemos",
        slug="selling",
        hint="Preço, desconto e por onde o pedido entra.",
        icon="sell",
        entries=(
            _model("Canais", "shop_channel", "Onde a loja vende: web, PDV, iFood, WhatsApp.", "hub"),
            _model("Regras de preço", "shop_ruleconfig", "As regras que alteram preço automaticamente.", "price_change"),
            _model("Promoções", "shop_promotion", "Campanhas de desconto por período, produto ou público.", "campaign"),
            _model("Cupons", "shop_coupon", "Códigos que o cliente digita para ganhar desconto.", "confirmation_number"),
            _model("Faixas de preço", "guestman_pricetier", "Tabelas de preço por tipo de cliente.", "groups"),
            _model("Fidelidade", "shop_shoployalty", "Como o cliente acumula e troca pontos.", "loyalty"),
            _model("Papéis de consumo", "backstage_consumptionrole", "O que faz uma cesta indicar consumo no salão: bebida, lanche, prato quente.", "restaurant"),
            _model("Etiquetas de consumo", "backstage_productconsumptiontag", "Que papel cada produto cumpre na cesta. O nome engana: pão de hambúrguer é pão.", "label"),
        ),
    ),
    SettingsGroup(
        title="Como entregamos",
        slug="delivery",
        hint="Retirada, entrega e quanto custa cada uma.",
        icon="local_shipping",
        entries=(
            _model("Pedidos e entrega", "shop_shopordering", "Pedido mínimo, frete grátis, prazos e janelas de retirada.", "receipt_long"),
            _model("Zonas de entrega", "shop_deliveryzone", "Bairros e regiões atendidos, com a taxa de cada um.", "pin_drop"),
            _model("Faixas de distância", "shop_deliverydistanceband", "Taxa por quilômetro, quando a cobrança é por distância.", "straighten"),
        ),
    ),
    SettingsGroup(
        title="O que dizemos",
        slug="messages",
        hint="Cada frase que o cliente lê, na tela e nas mensagens.",
        icon="format_quote",
        entries=(
            SettingsEntry(
                label="Textos da interface",
                url_name="admin_console_copy_catalog",
                description="Toda frase da loja, organizada pela tela onde ela aparece.",
                icon="format_quote",
                is_custom_page=True,
            ),
            _model("Modelos de mensagem", "shop_notificationtemplate", "O texto de cada aviso enviado por WhatsApp, SMS e e-mail.", "mail"),
        ),
    ),
    SettingsGroup(
        title="Produção e estoque",
        slug="production",
        hint="Como a fornada é avaliada e onde o estoque mora.",
        icon="factory",
        entries=(
            _model("Produção", "shop_shopproduction", "Como o dia de produção é planejado e conferido.", "manufacturing"),
            _model("Compras", "shop_shoppurchase", "Como a reposição de insumos é calculada: consumo, prazos e segurança.", "shopping_cart"),
            _model("Defeitos de fornada", "shop_qualitydefect", "Os problemas que o padeiro pode apontar ao avaliar um lote.", "report"),
            _model("Graus de qualidade", "shop_qualitygrade", "As notas de qualidade e o desconto que cada uma aplica.", "grade"),
            _model("Motivos de episódio", "backstage_operationepisodekind", "As explicações que o operador pode dar quando algo sai do previsto.", "help_center"),
            _model("Posições", "stockman_position", "Os lugares onde o estoque fica: balcão, câmara, depósito.", "domain"),
            _model("Alertas de estoque", "stockman_stockalert", "A partir de que quantidade a loja avisa que vai faltar.", "notification_important"),
        ),
    ),
    SettingsGroup(
        title="Equipamentos",
        slug="equipment",
        hint="As máquinas e estações da casa.",
        icon="settings_input_component",
        entries=(
            _model("PDV e alertas", "shop_shoppos", "Comportamento do balcão e quais alertas o operador recebe.", "point_of_sale"),
            _model("Estações KDS", "backstage_kdsinstance", "As telas da cozinha e o que cada uma exibe.", "tv"),
            _model("Comandas do PDV", "backstage_postab", "As comandas fixas do balcão.", "receipt"),
            _model("Lugares do salão", "backstage_seatingspot", "Mesas, balcão e o que só é usado em dia cheio.", "table_restaurant"),
            _model("Terminais do PDV", "cashman_terminal", "Os caixas físicos e a gaveta de dinheiro de cada um.", "point_of_sale"),
            _model("Modelos de checklist", "backstage_operationchecklisttemplate", "As rotinas de abertura e fechamento da casa.", "fact_check"),
            _model("Modelos de tarefa", "backstage_operationtasktemplate", "As tarefas que compõem cada rotina.", "task_alt"),
        ),
    ),
    SettingsGroup(
        title="Quem entra",
        slug="access",
        hint="Pessoas, permissões e credenciais.",
        icon="admin_panel_settings",
        entries=(
            _model("Usuários", "auth_user", "Quem tem acesso ao sistema.", "person"),
            _model("Grupos", "auth_group", "Os papéis e o que cada um pode fazer.", "group"),
            _model("Operadores e PIN", "doorman_pincredential", "O PIN e o crachá de cada operador do balcão.", "badge"),
            _model("Dispositivos confiáveis", "doorman_trusteddevice", "Aparelhos que dispensam nova verificação.", "devices"),
            _model("Verificação em duas etapas", "otp_totp_totpdevice", "Autenticação extra para contas administrativas.", "security"),
            _model("Referências", "refs_ref", "O registro interno de códigos e a renomeação em massa.", "tag"),
        ),
    ),
)


def _normalize(text: str) -> str:
    """Sem acento e em minúsculas — quem busca "producao" quer achar "Produção"."""
    stripped = unicodedata.normalize("NFKD", text)
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower()


def _matches(entry: SettingsEntry, group: SettingsGroup, needle: str) -> bool:
    haystack = _normalize(f"{entry.label} {entry.description} {group.title}")
    return needle in haystack


def build_settings_hub(*, q: str = "", slug: str = "") -> dict:
    """Monta a tela de Configuração, opcionalmente filtrada por um termo.

    Uma entrada que não resolve é omitida com o motivo — o app pode não estar
    instalado neste deployment, e uma grade com link morto seria pior do que uma
    grade menor (foi assim que cinco telas ficaram inalcançáveis por meses).
    """
    needle = _normalize(q.strip())
    groups: list[dict] = []
    total = 0
    unavailable: list[str] = []

    for group in SETTINGS_MAP:
        if slug and group.slug != slug:
            continue
        cards = []
        for entry in group.entries:
            try:
                url = entry.url
            except NoReverseMatch:
                unavailable.append(entry.label)
                continue
            if needle and not _matches(entry, group, needle):
                continue
            cards.append(
                {
                    "label": entry.label,
                    "description": entry.description,
                    "icon": entry.icon,
                    "url": url,
                }
            )
        total += len(cards)
        if cards:
            groups.append(
                {
                    "title": group.title,
                    "slug": group.slug,
                    "hint": group.hint,
                    "icon": group.icon,
                    "cards": tuple(cards),
                }
            )

    current = next((g for g in SETTINGS_MAP if g.slug == slug), None)
    return {
        "groups": tuple(groups),
        "total": total,
        "query": q,
        "unavailable": tuple(unavailable),
        "scope": {"title": current.title, "hint": current.hint, "slug": current.slug}
        if current
        else None,
    }


def settings_screen_urls() -> set[str]:
    """Os caminhos que esta tela alcança — usado pelo contrato de navegação.

    O teste que proíbe tela órfã precisa saber que uma tela alcançada pela
    Configuração não está órfã. Perguntar aqui, em vez de manter uma segunda
    lista no teste, é o que impede as duas listas de divergirem.
    """
    urls = set()
    for group in SETTINGS_MAP:
        for entry in group.entries:
            try:
                urls.add(entry.url)
            except NoReverseMatch:
                continue
    return urls


def settings_nav_sections() -> tuple[dict, ...]:
    """Os escopos, para o menu lateral desenhar os mesmos sete que a tela mostra.

    Uma lista só, consultada pelos dois: se alguém criar um escopo novo aqui, ele
    nasce no menu junto. Duas listas divergiriam no primeiro escopo novo.
    """
    return tuple(
        {"title": g.title, "slug": g.slug, "icon": g.icon} for g in SETTINGS_MAP
    )


def settings_scope_urls(slug: str) -> set[str]:
    """As telas de UM escopo — o menu usa para saber que escopo destacar.

    Sem isto, editar "Zonas de entrega" não acende nada no menu: a tela é
    alcançada pela Configuração e não tem item próprio. Com isto, o escopo dela
    ("Como entregamos") fica destacado enquanto ela está aberta.
    """
    group = next((g for g in SETTINGS_MAP if g.slug == slug), None)
    if group is None:
        return set()
    urls = set()
    for entry in group.entries:
        try:
            urls.add(entry.url)
        except NoReverseMatch:
            continue
    return urls
