"""Build the static preview from the reviewed member/publication JSON files."""
import copy
import json
import re
import unicodedata
from pathlib import Path
from member_registry import load_members, member_is_author, publications_since_enrollment

ROOT = Path(__file__).resolve().parents[1]


def title_key(title):
    return ''.join(c for c in unicodedata.normalize('NFKC', title).casefold() if c.isalnum())


def identity_urls(paper):
    urls = [paper['url'], *paper.get('alternateUrls', [])]
    if paper.get('doi'):
        urls.append('https://doi.org/' + paper['doi'])
    return {re.sub(r'^https?://(?:dx\.)?', '', url.strip()).rstrip('/').casefold() for url in urls}


def deduplicate(records):
    """Merge DOI/version identities or identical titles with overlapping authors.

    Different conference/demo/journal titles remain distinct unless explicitly
    linked as alternate versions. Metadata from published work takes priority.
    """
    merged = []
    rank = {'published': 0, 'accepted': 1, 'preprint': 2}
    for record in sorted(records, key=lambda p: rank[p['status']]):
        paper = copy.deepcopy(record)
        matches = [p for p in merged if identity_urls(p) & identity_urls(paper) or (
            title_key(p['title']) == title_key(paper['title']) and
            set(p['authors']) & set(paper['authors']))]
        if not matches:
            merged.append(paper)
            continue
        # Also collapse groups bridged by an explicit alternate-version URL.
        kept = matches[0]
        for other in [*matches[1:], paper]:
            for field in ['memberIds', 'sources', 'topics', 'topicKeys']:
                kept[field] = list(dict.fromkeys(kept.get(field, []) + other.get(field, [])))
            kept['alternateUrls'] = list(dict.fromkeys([
                *kept.get('alternateUrls', []), *other.get('alternateUrls', []), other['url']]))
            kept['alternateUrls'] = [u for u in kept['alternateUrls'] if u != kept['url']]
        for other in matches[1:]:
            merged.remove(other)
    return sorted(merged, key=lambda p: (-p['year'], p['title'].casefold()))


def main():
    members = load_members(ROOT / 'data/members.json')
    records = json.loads((ROOT / 'data/publications.json').read_text())
    papers = publications_since_enrollment(deduplicate(records), members)
    member_names = {m['id']: m for m in members}
    assert len(member_names) == len(members), 'Duplicate member IDs'
    assert len({p['id'] for p in papers}) == len(papers), 'Duplicate paper IDs'
    for p in papers:
        assert re.fullmatch(r'[a-z0-9-]+', p['id']), p['id']
        assert p['memberIds'] and p['sources'], p['title']
        assert all(member_is_author(member_names[mid], p['authors']) for mid in p['memberIds']), p['title']
        assert p['url'].startswith('https://'), p['url']
        p['authors'] = ', '.join(p['authors'])
    output = ROOT / 'lab-preview/data.js'
    output.write_text('const LAB = ' + json.dumps({'members': members, 'papers': papers},
                      ensure_ascii=False, indent=2) + ';\n')
    print(f'Built {len(papers)} publications for {len(members)} members.')


if __name__ == '__main__':
    main()
