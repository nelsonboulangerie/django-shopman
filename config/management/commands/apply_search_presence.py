"""Leva a presença de busca da Nelson a um banco que já existe — sem reseed.

Usage::

    python manage.py apply_search_presence            # relatório (não escreve)
    python manage.py apply_search_presence --apply    # grava o que está faltando

**Por que este comando existe.** Os textos de busca, os perfis da marca e a FAQ
inicial moram no BANCO (Admin → Busca e compartilhamento, Perguntas frequentes),
porque o gestor edita sem deploy. O ``seed`` os grava num banco novo; o alpha já
está semeado e reseed pede a palavra do dono. Este comando é o recorte oposto:
grava só o que falta no banco que já está lá.

O que ele respeita, de propósito:

- **campo de busca preenchido não é tocado** — se o gestor escreveu, é dele;
- **pergunta existente não é tocada** (casa pela ``ref``), publicada ou não;
- **perfil já cadastrado fica**; só entra o perfil real que falta e sai o link
  de exemplo (``example``), que declarava ao Google um perfil que não é da casa.

O que ele NÃO faz: não mexe em horário, endereço, coordenadas, preço, catálogo.
Esses fatos têm tela própria e dono próprio.

A MESMA fonte alimenta o ``seed`` (``apply_search_presence(shop, overwrite=True)``):
o que o alpha recebe por este comando é o que um banco novo nasce tendo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

#: Os textos da Nelson para busca e cartão de link. Os dois códigos de
#: verificação são os que a landing antiga (www.) publicava: moram na loja para a
#: verificação sobreviver quando aquele domínio passar a apontar para cá.
SEARCH_FIELDS: dict[str, object] = {
    "seo_home_title": "Nelson Boulangerie · Padaria artesanal em Londrina",
    "seo_home_description": (
        "Padaria artesanal em Londrina desde 1997. Pães de fermentação natural, "
        "croissants e brioches feitos todo dia. Peça online para retirar ou receber."
    ),
    "seo_menu_description": (
        "Pães de fermentação natural, croissants, brioches e doces da Nelson "
        "Boulangerie, com a disponibilidade do dia. Peça online em Londrina."
    ),
    "seo_faq_description": (
        "Pedidos, retirada, entrega, encomendas, pagamento e alérgenos na Nelson "
        "Boulangerie, padaria artesanal em Londrina."
    ),
    "business_type": "Bakery",
    "price_range": "$$",
    "founding_year": 1997,
    "facebook_domain_verification": "oo7p4q0ge38t6uld8oteigl0bk1xbt",
    "pinterest_domain_verification": "90531536e1551847c482077d10bc9c4d",
}

#: Os perfis que a landing antiga já declarava como canais oficiais.
BRAND_PROFILES: tuple[str, ...] = (
    "https://www.instagram.com/nelsonboulangerie",
    "https://www.facebook.com/nelsonboulangerie",
)

#: A FAQ inicial. Cada resposta saiu de um fato que o sistema já afirma (seed,
#: configuração de canal, copy da loja), mas a copy pública ainda não passou pela
#: revisão do dono (17/09/2026: "essas copies estão erradas, precisam de revisão").
#: Por isso TODAS nascem como RASCUNHO: o gestor revisa e publica no Admin. A
#: revisão é bloqueio de go-live (``config/public_copy_review.py``). As que
#: dependem de decisão de negócio além do texto: cancelamento (os termos ainda
#: aguardam aval), CPF na nota do pedido online (sem campo no checkout), iFood
#: (integração em homologação) e fidelidade (sem decisão registrada).
#: As quatro perguntas operacionais (entrega, horário, endereço, contato) NÃO
#: estão aqui: a loja as responde da configuração viva (``FAQEntry`` as recusa).
PUBLIC_FAQ: tuple[dict, ...] = (
    {
        "ref": "o-que-e-fermentacao-natural",
        "position": 10,
        "published": False,
        "question": "O que é fermentação natural (levain)?",
        "answer": (
            "Levain é o fermento natural feito só de farinha e água, que alimentamos todos os "
            "dias. Nossos pães rústicos, como baguetes, ciabattas e campagnes, levam fermentação "
            "100% natural e tempo longo de descanso. Os pães macios e as massas amanteigadas, "
            "como croissant e brioche, levam fermento biológico. A lista de ingredientes de cada "
            "item está na página do produto."
        ),
        "search_terms": "levain, fermentação natural, fermento natural, massa madre, sourdough, fermento biológico, pão rústico",
    },
    {
        "ref": "voces-tem-opcoes-sem-gluten",
        "position": 20,
        "published": False,
        "question": "Vocês têm opções sem glúten? E quanto a alérgenos?",
        "answer": (
            "Não temos. Somos uma padaria e trabalhamos com farinha de trigo todos os dias, então "
            "todos os nossos produtos contêm ou podem conter glúten. A produção é feita em cozinha "
            "compartilhada, e os produtos podem conter traços de leite, ovos, castanha-do-brasil, "
            "castanha de caju, gergelim e pimenta-do-reino. Na página de cada produto, em "
            "Ingredientes e restrições, listamos os ingredientes e os alérgenos declarados."
        ),
        "search_terms": "glúten, sem glúten, celíaco, alergia, alérgenos, intolerância, lactose, leite, ovos, castanhas, gergelim, traços, trigo",
    },
    {
        "ref": "como-faco-um-pedido-pelo-site",
        "position": 30,
        "published": False,
        "question": "Como faço um pedido pelo site?",
        "answer": (
            "Navegue pelo cardápio e adicione os itens à sacola; a disponibilidade aparece em tempo "
            "real. Na finalização, você escolhe se vai retirar na loja ou receber em casa, a data e "
            "a forma de pagamento. Depois de enviado, conferimos o pedido e mostramos cada passo na "
            "página de acompanhamento."
        ),
        "search_terms": "como pedir, fazer pedido, comprar online, pedido pelo site, sacola, carrinho, finalizar, retirada",
    },
    {
        "ref": "preciso-criar-uma-conta",
        "position": 40,
        "published": False,
        "question": "Preciso criar uma conta? Como faço para entrar?",
        "answer": (
            "Você vê o cardápio à vontade; para finalizar um pedido, pedimos que entre com seu "
            "telefone. Não usamos senha: você entra pelo WhatsApp, enviando uma mensagem pronta e "
            "recebendo um link, ou com um código por SMS. Se quiser, o aparelho fica salvo e você "
            "entra sem código nas próximas vezes."
        ),
        "search_terms": "conta, cadastro, login, entrar, senha, código, WhatsApp, SMS, telefone, criar conta, acesso",
    },
    {
        "ref": "quais-formas-de-pagamento-voces-aceitam",
        "position": 50,
        "published": False,
        "question": "Quais formas de pagamento vocês aceitam?",
        "answer": (
            "No site, aceitamos Pix e cartão. O cartão é processado por um provedor seguro, e nós "
            "não recebemos os dados dele. O Pix é confirmado automaticamente dentro do prazo que "
            "aparece na tela do pedido; se o prazo passar sem pagamento, o pedido é cancelado e nada "
            "é cobrado. Na loja, aceitamos dinheiro, Pix e cartão de crédito ou débito."
        ),
        "search_terms": "pagamento, formas de pagamento, Pix, cartão, crédito, débito, dinheiro, pagar, QR code, copia e cola",
    },
    {
        "ref": "posso-encomendar-para-outro-dia",
        "position": 60,
        "published": False,
        "question": "Posso encomendar para outro dia? Preciso pagar antes?",
        "answer": (
            "Sim. Na finalização do pedido, escolha outra data; o calendário mostra só os dias "
            "disponíveis. A encomenda é paga antecipadamente, por Pix ou cartão, e fica garantida "
            "com a confirmação do pagamento. Como produzimos para você na data combinada, "
            "preparamos tudo fresco no dia."
        ),
        "search_terms": "encomenda, encomendar, agendar, outro dia, amanhã, reservar, pagamento antecipado, pagar antes, antecedência",
    },
    {
        "ref": "por-que-um-produto-aparece-como-indisponivel",
        "position": 70,
        "published": False,
        "question": "Por que um produto aparece como indisponível?",
        "answer": (
            "Nossa produção é artesanal, feita em fornadas ao longo do dia e em quantidade "
            "limitada. O cardápio mostra a situação de cada item em tempo real: disponível, últimas "
            "unidades, lista de espera ou indisponível. Se um item acabar entre a sacola e a nossa "
            "conferência, avisamos você antes de seguir."
        ),
        "search_terms": "indisponível, esgotado, acabou, sem estoque, últimas unidades, disponibilidade, produção do dia, fornada",
    },
    {
        "ref": "como-funciona-a-lista-de-espera",
        "position": 80,
        "published": False,
        "question": "Como funciona a lista de espera de uma fornada?",
        "answer": (
            "Quando um item aparece em lista de espera, a próxima fornada dele já está planejada. "
            "Você envia o pedido para garantir sua vez, e nada é cobrado nesse momento. Quando a "
            "fornada sai, avisamos você para confirmar e pagar dentro do prazo mostrado; sem "
            "confirmação, a vaga passa para a próxima pessoa."
        ),
        "search_terms": "lista de espera, fila, fornada, reservar, próxima fornada, sair do forno, aguardar",
    },
    {
        "ref": "como-funciona-o-me-avise",
        "position": 90,
        "published": False,
        "question": "Como funciona o botão Me avise?",
        "answer": (
            "Quando um produto está indisponível, toque em Me avise. Avisamos pelo WhatsApp "
            "confirmado na sua conta sempre que ele voltar, até você pausar ou cancelar o aviso. "
            "Você gerencia seus avisos nas preferências da sua conta ou pelo link que vem na "
            "mensagem."
        ),
        "search_terms": "me avise, avise-me, aviso, alerta, notificação, voltou, quando voltar, reposição, cancelar aviso",
    },
    {
        "ref": "como-acompanho-meu-pedido",
        "position": 100,
        "published": False,
        "question": "Como acompanho meu pedido?",
        "answer": (
            "Depois de enviar o pedido, você acompanha cada etapa na página do pedido: pagamento, "
            "confirmação, preparo, retirada ou entrega. Enviamos as atualizações pelo WhatsApp, "
            "como o aviso de pedido pronto. Seus pedidos também ficam na sua conta."
        ),
        "search_terms": "acompanhar pedido, status, rastrear, onde está meu pedido, pedido pronto, andamento, meus pedidos",
    },
    {
        "ref": "posso-cancelar-meu-pedido",
        "position": 110,
        "published": False,
        "question": "Posso cancelar meu pedido?",
        "answer": (
            "Sim, enquanto o pedido ainda não foi pago e não entrou em preparo, o botão Cancelar "
            "pedido aparece na página de acompanhamento. Depois disso, fale conosco: alimento em "
            "preparo não volta para a prateleira, mas buscamos a melhor solução com você."
        ),
        "search_terms": "cancelar, cancelamento, desistir, estorno, reembolso, mudar pedido, alterar pedido",
    },
    {
        "ref": "posso-pedir-cpf-na-nota",
        "position": 120,
        "published": False,
        "question": "Posso pedir CPF na nota fiscal?",
        "answer": (
            "Sim. Na loja, é só informar seu CPF no caixa na hora da compra, e emitimos a NFC-e com "
            "ele. Também podemos enviar a nota por e-mail, se você preferir."
        ),
        "search_terms": "CPF na nota, nota fiscal, NFC-e, cupom fiscal, CNPJ, comprovante",
    },
    {
        "ref": "voces-estao-no-ifood",
        "position": 130,
        "published": False,
        "question": "Vocês estão no iFood?",
        "answer": (
            "Sim, também recebemos pedidos pelo iFood. Lá, o preço e o pagamento seguem as regras do "
            "aplicativo. Pelo nosso site, você fala direto conosco e pode encomendar para outras datas."
        ),
        "search_terms": "iFood, aplicativo, app de delivery, marketplace",
    },
    {
        "ref": "voces-tem-programa-de-fidelidade",
        "position": 140,
        "published": False,
        "question": "Vocês têm programa de fidelidade?",
        "answer": (
            "Sim. Os pedidos concluídos com a sua conta acumulam pontos e selos. Você acompanha o "
            "saldo na sua conta e pode usar os pontos ao finalizar um pedido pelo site."
        ),
        "search_terms": "fidelidade, pontos, selos, cartela, cashback, recompensa, programa de pontos",
    },
)


def _is_placeholder_profile(url: str) -> bool:
    return "example" in (url or "").lower()


def _profile_key(url: str) -> str:
    """O mesmo perfil escrito de outro jeito (http, sem www, barra final) é o mesmo perfil."""
    value = (url or "").strip().lower().rstrip("/")
    for prefix in ("https://", "http://", "www."):
        value = value.removeprefix(prefix)
    return value


def apply_search_presence(shop, *, overwrite: bool = False, write: bool = True) -> list[str]:
    """Aplica campos de busca, perfis e FAQ. Devolve o que mudou (ou mudaria).

    ``overwrite=True`` é o modo do ``seed``: banco novo, a fonte manda em tudo.
    """
    from shopman.shop.models import FAQEntry

    changes: list[str] = []

    for field, value in SEARCH_FIELDS.items():
        current = getattr(shop, field)
        if current == value:
            continue
        # `business_type` nasce "Bakery" pelo default do campo: o default não é escolha de ninguém.
        if overwrite or current in ("", None) or field == "business_type":
            changes.append(f"loja.{field}: {current!r} → {value!r}")
            setattr(shop, field, value)

    links = list(shop.social_links or [])
    kept = [link for link in links if not _is_placeholder_profile(link)]
    for dropped in (link for link in links if _is_placeholder_profile(link)):
        changes.append(f"loja.social_links: remove {dropped}")
    known = {_profile_key(link) for link in kept}
    for profile in BRAND_PROFILES:
        if _profile_key(profile) not in known:
            kept.append(profile)
            changes.append(f"loja.social_links: adiciona {profile}")
    shop.social_links = kept

    faq_changes = []
    for entry in PUBLIC_FAQ:
        existing = FAQEntry.objects.filter(ref=entry["ref"]).first()
        if existing is not None and not overwrite:
            continue
        state = "publicada" if entry["published"] else "rascunho"
        faq_changes.append((entry, existing))
        changes.append(f"faq: {'atualiza' if existing else 'cria'} ({state}) {entry['question']}")

    if write and changes:
        with transaction.atomic():
            shop.save()
            for entry, existing in faq_changes:
                target = existing or FAQEntry(ref=entry["ref"])
                target.question = entry["question"]
                target.answer = entry["answer"]
                target.search_terms = entry["search_terms"]
                target.position = entry["position"]
                target.is_published = entry["published"]
                target.save()
    return changes


class Command(BaseCommand):
    help = "Grava os textos de busca, os perfis da marca e a FAQ inicial que faltam no banco."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Grava. Sem esta opção o comando só relata o que mudaria.",
        )

    def handle(self, *args, **options):
        from shopman.shop.models import Shop

        shop = Shop.objects.first()
        if shop is None:
            self.stderr.write("Nenhuma loja no banco. Rode o seed primeiro.")
            return

        write = options["apply"]
        changes = apply_search_presence(shop, write=write)
        if not changes:
            self.stdout.write("Nada a fazer: a presença de busca já está completa.")
            return
        for change in changes:
            self.stdout.write(f"  {change}")
        verb = "Gravado" if write else "Mudaria (rode com --apply para gravar)"
        self.stdout.write(f"{verb}: {len(changes)} alteração(ões).")
