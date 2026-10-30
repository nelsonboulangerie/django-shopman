# Gera a página-índice das prévias (servida por túnel). Uso: python3 build.py <saída> <links.json>
import json, sys, shutil, pathlib, html
out = pathlib.Path(sys.argv[1]); links = json.load(open(sys.argv[2]))
here = pathlib.Path(__file__).parent.parent
out.mkdir(parents=True, exist_ok=True)
for app in links['apps']:
    src = here / app['dir'] / app.get('capdir', 'captures')
    if src.exists():
        shutil.copytree(src, out / app['dir'], dirs_exist_ok=True, ignore=shutil.ignore_patterns('*.mjs', '*.md', '*.sh', '*.vue', '*.css'))
def sec(app):
    rows = ''.join(f'<li><a href="{html.escape(u)}">{html.escape(t)}</a></li>' for t, u in app['links'])
    caps = ''.join(f'<figure><a href="{app["dir"]}/{c}"><img loading="lazy" src="{app["dir"]}/{c}" alt="{html.escape(l)}"></a><figcaption>{html.escape(l)}</figcaption></figure>' for c, l in app.get('captures', []))
    notes = ''.join(f'<li>{html.escape(n)}</li>' for n in app.get('notes', []))
    return f'<section><h2>{html.escape(app["title"])}</h2><p class=muted>{html.escape(app["summary"])}</p><ul class=links>{rows}</ul>{"<ul class=notes>"+notes+"</ul>" if notes else ""}<div class=caps>{caps}</div></section>'
page = f'''<!doctype html><html lang=pt-BR><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Prévias do modo compacto</title>
<style>:root{{--bg:#faf7f2;--fg:#231d17;--muted:#6b6157;--line:#e3dbd0;--card:#fff;--link:#8a5a12}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1d1814;--fg:#f1e9df;--muted:#b3a697;--line:#3a322b;--card:#26201b;--link:#e4b465}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:16px}}
h1{{font-size:1.4rem;margin:.2em 0}}h2{{font-size:1.15rem;margin:0 0 .3em}}section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0}}
.muted{{color:var(--muted)}}a{{color:var(--link)}}.links{{padding-left:1.1em}}.links li{{margin:.35em 0}}.notes{{font-size:.95rem}}
.caps{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:10px}}figure{{margin:0}}img{{width:100%;border:1px solid var(--line);border-radius:8px}}figcaption{{font-size:.8rem;color:var(--muted)}}</style>
<main><h1>Prévias: modo compacto e modo padrão</h1><p class=muted>{html.escape(links["intro"])}</p>
{links.get("rules","")}{"".join(sec(a) for a in links["apps"])}</main></html>'''
(out / 'index.html').write_text(page)
