# Gera src/purchase-base3.html: cabeçalho v3 + corpo (tabela, rodapé, painel) da v2.
# Rode depois de gen-purchase.py para herdar as linhas atuais.
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
v2 = open('src/purchase-base.html').read()
a = v2.index('    <!-- Conteúdo: tabela')
b = v2.index('  </main>') + len('  </main>\n')
head = open('src-templates/purchase-base3.head.part').read()
tail = open('src-templates/purchase-base3.tail.part').read()
open('src/purchase-base3.html', 'w').write(head + v2[a:b] + tail)
print('ok')
