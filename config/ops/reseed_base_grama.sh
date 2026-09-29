#!/usr/bin/env bash
# Uso, no console do componente `web` da DigitalOcean (App → Console):
#     bash config/ops/reseed_base_grama.sh
#
# Ensaio de 24/09/2026 contra a cópia do banco do alpha: exit 0 (PR #1089).
# Pré-requisito: #1089 no ar (sem ele o flush quebra no terminal do PDV).
set -euo pipefail
# Base em grama no alpha (WP-UNIDADE-BASE-GRAMA). Roda no console do componente
# `web`: as variáveis de ambiente são as dele, e nada aqui toca no spec.

# 0) Trava: sem o #1089 no ar, o flush quebra no terminal com meio banco apagado.
#    Lê o FONTE (grep): importar o seed sem o Django carregado estoura
#    AppRegistryNotReady — foi o que a primeira tentativa no alpha fez, em 24/09.
grep -q 'PrintAgentCredential' config/management/commands/seed.py \
  && grep -q 'if material.unit != "g":' config/management/commands/seed.py \
  || { echo "imagem sem o #1089: espere o deploy"; exit 1; }

# 1) Curadoria dos nomes dos insumos (28 renomeações, o café vira dois).
python manage.py apply_material_skus --apply | tail -3

# 2) Custo lançado POR QUILO, sem embalagem: pendura na embalagem "quilos"
#    antes de converter, para o centavo não virar fração de grama.
python manage.py shell -c "
from decimal import Decimal
from shopman.buyman.models import MaterialConversion, SupplierMaterialCost
from shopman.offerman.models import Product
vendidos = set(Product.objects.values_list('sku', flat=True))
for c in SupplierMaterialCost.objects.filter(conversion__isnull=True, material__unit='kg').select_related('material'):
    if c.material.sku in vendidos:
        continue
    conv, _ = MaterialConversion.objects.get_or_create(material=c.material, supplier=None, label='quilos', defaults={'to_base_factor': Decimal('1'), 'kind': MaterialConversion.Kind.CONVENTIONAL})
    c.conversion = conv
    c.save(update_fields=['conversion'])
    print('custo por quilo preso a embalagem:', c.material.sku)
"

# 3) Insumo pesado passa a contar em grama (o que também se VENDE por peso fica em kg).
SKUS=$(python manage.py shell -c "
from shopman.buyman.models import Material
from shopman.offerman.models import Product
vendidos = set(Product.objects.values_list('sku', flat=True))
# AGUA: o órfão que o dono mandou apagar (22/09); sem densidade, não converte.
print(' '.join(sorted(m.sku for m in Material.objects.filter(unit__in=['kg', 'l']) if m.sku not in vendidos and m.sku != 'AGUA')))
" | tail -1)
echo "convertendo: $SKUS"
python manage.py convert_material_base_unit $SKUS --to g --apply | tail -15

# 4) O reseed. A senha é só a trava do seed fora de DEBUG: o admin que existe não muda.
ADMIN_PASSWORD=$(python -c 'import secrets; print(secrets.token_urlsafe(24))') python manage.py seed --flush | tail -25
echo RESEED_GRAMA_OK
