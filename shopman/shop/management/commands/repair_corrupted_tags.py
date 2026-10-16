"""
Management command: repair_corrupted_tags

Conserta as etiquetas que o Admin gravou como repr de objeto.

Até a correção do widget (o ``UnfoldTagWidget`` dos admins de offerman e guestman),
o campo de etiquetas mostrava "[<Tag: pao>, <Tag: hamburger>]" e cada save sem mexer
gravava esse texto de volta, quebrado na vírgula: "[<Tag: pao>", "<Tag: hamburger>]".
Um segundo save aninhava ("[<Tag: [<Tag: pao>>"), e um campo vazio virava a etiqueta
"[]".

Para cada etiqueta corrompida, o comando tira as camadas de repr até sobrar o nome
limpo, liga o objeto à etiqueta limpa (reusando a que já existe) e solta a corrompida.
Etiqueta corrompida que fica sem uso é apagada. Nome que limpa para vazio ("[]") só
perde a ligação.

Cobre as duas famílias de etiqueta do projeto: ``taggit.Tag`` (palavras-chave do
Produto) e ``guestman.CustomerTag`` (etiquetas do Cliente).

Sem ``--apply`` só relata (dry-run). Idempotente: a segunda rodada não acha nada.

Usage:
    python manage.py repair_corrupted_tags
    python manage.py repair_corrupted_tags --apply
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db import transaction

#: "<Tag: ", "<CustomerTag: " e o "[" de lista que vem antes.
_REPR_PREFIX = re.compile(r"^\[?<\w*Tag: ")
_REPR_SUFFIX = re.compile(r">\]?$")
_EMPTY_LIST = "[]"


def is_corrupted(name: str) -> bool:
    return bool(re.search(r"<\w*Tag: ", name)) or name.strip() == _EMPTY_LIST


def clean_name(name: str) -> str:
    """Tira as camadas de repr até o nome parar de mudar. "" quando não sobra nome."""
    current = name.strip()
    while True:
        stripped = _REPR_SUFFIX.sub("", _REPR_PREFIX.sub("", current)).strip()
        if stripped == current:
            break
        current = stripped
    return "" if current in ("", _EMPTY_LIST, "[", "]") else current


def _tag_families():
    from shopman.guestman.models.tag import CustomerTag, TaggedCustomer
    from taggit.models import Tag, TaggedItem

    return [("taggit.Tag", Tag, TaggedItem), ("guestman.CustomerTag", CustomerTag, TaggedCustomer)]


def _clean_tag(tag_model, name: str):
    tag = tag_model.objects.filter(name__iexact=name).first()
    if tag is None:
        tag = tag_model.objects.filter(slug=tag_model().slugify(name)).first()
    if tag is None:
        tag = tag_model.objects.create(name=name)
    return tag


class Command(BaseCommand):
    help = "Conserta etiquetas gravadas como repr de objeto (\"[<Tag: pao>\"). Dry-run sem --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Grava a correção. Sem isto, só relata.")

    def handle(self, *args, **options):
        apply = options["apply"]
        totals = {"corrupted": 0, "relinked": 0, "unlinked": 0, "deleted": 0, "objects": set()}

        with transaction.atomic():
            for label, tag_model, through in _tag_families():
                corrupted = [t for t in tag_model.objects.all() if is_corrupted(t.name)]
                for tag in corrupted:
                    totals["corrupted"] += 1
                    target_name = clean_name(tag.name)
                    if target_name and is_corrupted(target_name):
                        self.stderr.write(f'{label} #{tag.pk} "{tag.name}": não sei limpar, ficou como está')
                        continue
                    items = list(through.objects.filter(tag=tag))
                    shown = f'"{target_name}"' if target_name else "(nenhuma: só solta)"
                    self.stdout.write(f'{label} #{tag.pk} "{tag.name}" -> {shown}, {len(items)} ligação(ões)')
                    target = _clean_tag(tag_model, target_name) if (apply and target_name and items) else None
                    for item in items:
                        totals["objects"].add((item.content_type_id, item.object_id))
                        if target_name:
                            totals["relinked"] += 1
                        else:
                            totals["unlinked"] += 1
                        if not apply:
                            continue
                        if target is not None:
                            through.objects.get_or_create(
                                tag=target, content_type_id=item.content_type_id, object_id=item.object_id
                            )
                        item.delete()
                    totals["deleted"] += 1
                    if apply:
                        tag.delete()

            if not apply:
                transaction.set_rollback(True)

        verb = "Corrigido" if apply else "Dry-run (nada gravado; use --apply)"
        self.stdout.write(
            f"{verb}: {totals['corrupted']} etiqueta(s) corrompida(s), {len(totals['objects'])} objeto(s) afetado(s), "
            f"{totals['relinked']} religada(s) ao nome limpo, {totals['unlinked']} solta(s), "
            f"{totals['deleted']} etiqueta(s) corrompida(s) apagada(s)."
        )
