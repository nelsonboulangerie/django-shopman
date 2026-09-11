"""Read-only source inventory; AST occurrences are candidates, not runtime proof."""
import ast
import csv
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
urls = ROOT / 'shopman/backstage/api/urls.py'
tree = ast.parse(urls.read_text())
imports = {alias.asname or alias.name: node.module for node in tree.body
           if isinstance(node, ast.ImportFrom) for alias in node.names}
rows = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'path' or len(node.args) < 2:
        continue
    if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        continue
    route = node.args[0].value
    if not route.startswith(('orders/', 'catalog/', 'feeds/')):
        continue
    view = node.args[1]
    if not isinstance(view, ast.Call) or not isinstance(view.func, ast.Attribute) or not isinstance(view.func.value, ast.Name):
        raise ValueError(f'Unresolved view: {route}')
    name = view.func.value.id
    source = ROOT / 'shopman/backstage/api' / f'{imports[name]}.py'
    classes = {item.name: item for item in ast.parse(source.read_text()).body if isinstance(item, ast.ClassDef)}
    cls = classes[name]
    methods = {}
    def inherit(current, class_map=classes, method_map=methods):
        for base in current.bases:
            if isinstance(base, ast.Name) and base.id in class_map:
                inherit(class_map[base.id], class_map, method_map)
        for method in current.body:
            if isinstance(method, ast.FunctionDef):
                method_map[method.name] = method
    inherit(cls)
    verbs = sorted(set(methods) & {'get', 'post', 'put', 'patch', 'delete'})
    calls = sorted({ast.unparse(call.func) for method in methods.values() for call in ast.walk(method)
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and any(word in ast.unparse(call.func) for word in ('service.', 'service_', 'orders_service.', 'catalog_service.', 'feed_service.'))})
    rows.append({'route': route, 'view': name, 'methods': ','.join(verbs), 'source': str(source.relative_to(ROOT)),
                 'line': cls.lineno, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'facade_calls': ';'.join(calls)})
with (OUT / 'routes.csv').open('w') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(sorted(rows, key=lambda row: row['route']))
consumers = []
for folder in ('shopman', 'packages'):
    for source in sorted((ROOT / folder).rglob('*.py')):
        if any(part in {'tests', 'migrations', '__pycache__'} for part in source.parts) or source.name.startswith('test_'):
            continue
        content = source.read_text()
        if 'IdempotencyKey' not in content and 'merge_order_data' not in content:
            continue
        module = ast.parse(content)
        for node in ast.walk(module):
            if isinstance(node, ast.Name) and node.id in {'IdempotencyKey', 'merge_order_data'} and isinstance(node.ctx, ast.Load):
                consumers.append({'source': str(source.relative_to(ROOT)), 'line': node.lineno, 'symbol': node.id})
with (OUT / 'consumers.csv').open('w') as stream:
    writer = csv.DictWriter(stream, fieldnames=['source', 'line', 'symbol'])
    writer.writeheader()
    writer.writerows(consumers)
(OUT / 'provenance.txt').write_text('Source HEAD: ' + subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True)
    + f'Routes: {len(rows)}\nDirect symbol occurrences: {len(consumers)}\n'
    + 'Only read source. No Django initialization, database or remote call.\n')
print(f'{len(rows)} routes; {len(consumers)} direct symbol occurrences')
