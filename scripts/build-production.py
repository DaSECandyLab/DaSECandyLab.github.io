"""Build the public site from an explicit allowlist; no articles are shipped."""
import argparse
import hashlib
import html
import re
import shutil
from pathlib import Path
from member_registry import load_members

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'lab-preview'
OUTPUT = ROOT / 'site-dist'
ORIGIN = 'https://dasecandylab.github.io'


def build(member_assets=None):
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    files = ['style.css', 'app.js', 'data.js', 'members.js', 'system-motion.js',
             'mascot-v6.css', 'mascot-v6.js', 'brand-logo.css', 'brand-logo.js', 'assets/fonts.css',
             'assets/candy-org-logo.svg',
             'assets/candy-org-icon-v1.png', 'assets/candy-mascot-body-v4.png']
    files += ['assets/font-%d.ttf' % i for i in range(6)]
    photos = {m['photo'] for m in load_members(ROOT / 'data/members.json') if m.get('photo')}
    for relative in sorted(set(files) | photos):
        source = SOURCE / relative
        if member_assets and relative in photos:
            candidate = member_assets / relative
            if candidate.is_file():
                if not candidate.resolve().is_relative_to(member_assets.resolve()):
                    raise ValueError('Member photo escapes asset directory')
                source = candidate
        target = OUTPUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    page = (SOURCE / 'index.html').read_text()
    page = re.sub(r'<meta name="robots"[^>]+>', '', page)
    page = re.sub(r'<link rel="canonical"[^>]+>', '', page)
    page = page.replace('<div class="preview-label">Design preview</div>', '')
    # Version every first-party script and stylesheet, including the shared data.
    def version(match):
        attr, relative = match.group(1), match.group(2)
        digest = hashlib.sha256((OUTPUT / relative).read_bytes()).hexdigest()[:12]
        return '%s="%s?v=%s"' % (attr, relative, digest)
    page = re.sub(r'(href|src)="([^"?]+\.(?:js|css))(?:\?[^" ]*)?"', version, page)
    page = page.replace('</head>', '<link rel="canonical" href="' + ORIGIN + '/"></head>')
    (OUTPUT / 'index.html').write_text(page)
    (OUTPUT / '.nojekyll').touch()
    (OUTPUT / 'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: ' + ORIGIN + '/sitemap.xml\n')
    (OUTPUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + ORIGIN + '/</loc></url></urlset>\n')
    for path, section in [('contact', 'contact'), ('people', 'members'), ('publication', 'publications')]:
        target = OUTPUT / path
        target.mkdir()
        url = '/#' + section
        (target / 'index.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=' + url + '"><title>Candy Lab</title></head><body><a href="' + url + '">Continue to ' + html.escape(section) + '</a></body></html>')
    (OUTPUT / '404.html').write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Page not found — Candy Lab</title><link rel="icon" type="image/svg+xml" href="/assets/candy-org-logo.svg"><link rel="stylesheet" href="/assets/fonts.css"><link rel="stylesheet" href="/style.css"></head><body><main class="page-heading"><h1>Page not found</h1><p><a href="/">Return to Candy Lab →</a></p></main></body></html>''')
    assert 'data-nav="docs"' not in page
    assert not (OUTPUT / 'docs').exists()
    assert not (OUTPUT / 'article.js').exists()
    print('Production site built at', OUTPUT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--member-assets', type=Path, help='Directory containing assets/ from the member repository')
    build(parser.parse_args().member_assets)
