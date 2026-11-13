"""Update both website paper views from identity-bound student sources.

No LLM, name-only author search, API key, or advisor bibliography is used.
Uncertain metadata stays in the report; existing papers survive source outages.
"""
import argparse
import contextlib
import fcntl
import hashlib
import html
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from member_registry import (associate_papers, load_members, match_member_ids,
                             member_is_author, publications_since_enrollment, validate_members)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('builder', ROOT / 'scripts/build-preview-data.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def clean(text):
    return ' '.join(html.unescape(re.sub('<[^>]*>', '', text)).split())


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(content)
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class Fetcher:
    def __init__(self, cache, offline=False):
        self.cache, self.offline, self.last = cache, offline, 0
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, url, ttl=0):
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.txt')
        if path.exists() and (self.offline or time.time() - path.stat().st_mtime < ttl):
            return path.read_text()
        if self.offline:
            raise ValueError('Uncached URL: ' + url)
        for attempt in range(4):
            time.sleep(max(0, 2 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={'Accept': 'application/json',
                    'User-Agent': 'CandyLabPublicationSync/1.0 (https://docs.eggtart.icu)'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    text = response.read().decode('utf-8')
                if url.startswith(('https://api.crossref.org/', 'https://pub.orcid.org/')):
                    json.loads(text)
                atomic_write(path, text)
                return text
            except urllib.error.HTTPError as error:
                if error.code not in (429, 503) or attempt == 3:
                    raise
                retry = error.headers.get('Retry-After', '')
                time.sleep(min(int(retry), 60) if retry.isdigit() else 10 * (attempt + 1))

    def json(self, url, ttl=0):
        return json.loads(self.get(url, ttl))


def authors(item):
    return [clean(a.get('given', '') + ' ' + a.get('family', '')) for a in item.get('author', [])]


def title(item):
    return clean(': '.join(item.get('title', []) + item.get('subtitle', [])))


def homepage_titles(page):
    section = re.split('Selected Publications', page, flags=re.I)[1]
    section = re.split(r'<h[12]\b|</section>', section)[0]
    result = []
    for item in re.findall(r'<li\b[^>]*>(.*?)</li>', section, re.S):
        citation = clean(item).replace('C.S. Jensen', 'CS Jensen').replace('C S. Jensen', 'CS Jensen')
        parts = citation.split('. ')
        if len(parts) >= 2:
            result.append(parts[1])
    if not result:
        raise ValueError('Homepage publication markup changed')
    return result


def classify(text):
    text = text.lower()
    rules = [
        ('Storage', 'storage', r'storage|ssd|pcm|lsm|buffer|succinctkv'),
        ('Operations', 'operations', r'autoscal|parallelism|tuning|configuration|q-doctor|forecasting'),
        ('Query optimization', 'optimizer', r'cardinality|query planning|physical design|join|graph queries'),
        ('Similarity search', 'vector', r'similarity|trajectory|trajectories|high-dimensional|geo-textual|spatial keyword'),
        ('Database testing', None, r'isolation|bug|dbstorm|leopard'),
        ('Benchmarking', None, r'benchmark|(?:database|workload) (?:generation|generator)|vodka'),
        ('LLM', None, r'llm|language model|retrieval-augmented|personalized agents'),
        ('Reinforcement learning', None, r'reinforcement'),
        ('Data warehouse', None, r'data warehouse'),
        ('Multimodal analytics', None, r'multimodal'),
    ]
    matches = [(label, key) for label, key, pattern in rules if re.search(pattern, text)]
    return [label for label, _ in matches], [key for _, key in matches if key]


def venue(item):
    names = item.get('container-title', [])
    full = ' '.join(names)
    for pattern, short in [(r'VLDB Endowment', 'PVLDB'), (r'International Conference on Data Engineering', 'ICDE'),
        (r'Companion.*Management of Data', 'SIGMOD Companion'), (r'Management of Data', 'SIGMOD'),
        (r'Knowledge and Data Engineering', 'TKDE'), (r'Database Systems for Advanced Applications', 'DASFAA'),
        (r'Machine Learning and Knowledge Discovery', 'ECML PKDD'), (r'Information.*Knowledge Management', 'CIKM'),
        (r'Web Information Systems Engineering', 'WISE'), (r'Service-Oriented Computing', 'ICSOC'),
        (r'Knowledge and Information Systems', 'KAIS')]:
        if re.search(pattern, full, re.I):
            return short
    return clean(names[-1]) if names else ('Preprint' if item.get('type') == 'posted-content' else 'Publication')


def from_crossref(item, member, members, source):
    names = authors(item)
    if not member_is_author(member, names):
        raise ValueError('Bound member is absent from the author list')
    doi = item['DOI'].lower()
    name = title(item)
    year = item.get('published-print', item.get('published', {}))['date-parts'][0][0]
    topics, keys = classify(name)
    label = name.split(':')[0]
    if len(label) > 42:
        label = ' '.join(label.split()[:6]) + '…'
    return {'id': 'paper-' + hashlib.sha256(doi.encode()).hexdigest()[:12], 'label': label,
        'title': name, 'shortTitle': name, 'authors': names, 'year': year, 'venue': venue(item),
        'status': 'preprint' if item.get('type') == 'posted-content' else 'published',
        'doi': doi, 'url': 'https://doi.org/' + doi,
        'memberIds': match_member_ids(names, members),
        'sources': [source, 'https://api.crossref.org/works/' + doi],
        'checkedAt': datetime.now(timezone.utc).date().isoformat(), 'topics': topics, 'topicKeys': keys}


def validate(papers, members):
    lookup = {m['id']: m for m in members}
    assert len({p['id'] for p in papers}) == len(papers), 'Duplicate IDs'
    for p in papers:
        assert re.fullmatch('[a-z0-9-]+', p['id']), p['id']
        assert any(lookup[mid].get('role') != 'advisor' for mid in p['memberIds']), p['title']
        assert all(member_is_author(lookup[mid], p['authors']) for mid in p['memberIds']), p['title']
        assert p['url'].startswith('https://') and p['sources'], p['title']
        assert isinstance(p['year'], int) and 1900 < p['year'] < 2200, p['title']


def run(args):
    fetch = Fetcher(args.cache, args.offline)
    members_url = getattr(args, 'members_url', None)
    members_repo = getattr(args, 'members_repo', None)
    if members_repo:
        snapshot = subprocess.check_output([
            'git', '-C', str(members_repo), 'show', 'FETCH_HEAD:data/members.json'])
        members = validate_members(json.loads(snapshot.decode('utf-8')))
    elif members_url:
        if not members_url.startswith('https://'):
            raise ValueError('--members-url requires HTTPS')
        # Validate a complete fetched roster before replacing any local/live data.
        members = validate_members(fetch.json(members_url))
    else:
        members = load_members(ROOT / 'data/members.json')
    students = [m for m in members if m.get('role') != 'advisor']
    original = json.loads((ROOT / 'data/publications.json').read_text())
    records = associate_papers(original, members)
    report = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'issues': [], 'unmatchedTitles': [],
              'sourcesChecked': [], 'unboundMembers': [],
              'before': len(publications_since_enrollment(builder.deduplicate(records), members)),
              'memberRegistry': (str(members_repo) + '#FETCH_HEAD:data/members.json'
                                 if members_repo else members_url or 'data/members.json')}
    known_dois = {p.get('doi'): p for p in records if p.get('doi')}
    known_titles = {builder.title_key(p['title']): p for p in records}

    def accept(item, member, source):
        candidate = from_crossref(item, member, members, source)
        if candidate['doi'] in known_dois:
            existing = known_dois[candidate['doi']]
            # Preserve reviewed spelling/venue corrections and stable deep links.
            for field in ['memberIds', 'sources']:
                existing[field] = list(dict.fromkeys(existing[field] + candidate[field]))
            return
        records.append(candidate)
        known_dois[candidate['doi']] = candidate
        known_titles[builder.title_key(candidate['title'])] = candidate

    def get_doi(doi, member, source):
        if doi in known_dois:
            existing = known_dois[doi]
            if not member_is_author(member, existing['authors']):
                raise ValueError('ORCID work author mismatch: ' + doi)
            existing['sources'] = list(dict.fromkeys(existing['sources'] + [source]))
            if member['id'] not in existing['memberIds']:
                existing['memberIds'].append(member['id'])
            return
        item = fetch.json('https://api.crossref.org/works/' + doi, ttl=7 * 86400)['message']
        accept(item, member, source)

    def source_task(url, action):
        try:
            action()
            report['sourcesChecked'].append(url)
        except Exception as error:
            report['issues'].append({'source': url, 'error': str(error)})

    for member in students:
        config = member.get('publicationSources', {})
        if not config:
            report['unboundMembers'].append(member['id'])
        if config.get('orcid'):
            oid = config['orcid']
            assert re.fullmatch(r'\d{4}-\d{4}-\d{4}-[\dX]{4}', oid), oid
            orcid_url = 'https://pub.orcid.org/v3.0/' + oid + '/works'
            def orcid_work(member=member, orcid_url=orcid_url):
                for group in fetch.json(orcid_url)['group']:
                    for summary in group['work-summary']:
                        for ext in (summary.get('external-ids') or {}).get('external-id', []):
                            if ext['external-id-type'].lower() == 'doi' and ext.get('external-id-relationship') == 'self':
                                doi = re.sub(r'^https?://(?:dx\.)?doi.org/', '', ext['external-id-value'], flags=re.I).lower()
                                source_task('https://doi.org/' + doi, lambda doi=doi: get_doi(doi, member, orcid_url))
            source_task(orcid_url, orcid_work)
            crossref_url = 'https://api.crossref.org/works?' + urllib.parse.urlencode({'filter': 'orcid:' + oid, 'rows': 1000})
            def crossref_work(member=member, oid=oid, crossref_url=crossref_url):
                offset = 0
                while True:
                    batch = fetch.json(crossref_url + '&offset=' + str(offset))['message']
                    for item in batch['items']:
                        if any(a.get('ORCID', '').rstrip('/').endswith('/' + oid) and
                               member_is_author(member, [clean(a.get('given', '') + ' ' + a.get('family', ''))])
                               for a in item.get('author', [])):
                            accept(item, member, crossref_url)
                    offset += len(batch['items'])
                    if not batch['items'] or offset >= batch['total-results']:
                        break
            source_task(crossref_url, crossref_work)
        if config.get('homepage'):
            homepage = config['homepage']
            def homepage_work(member=member, homepage=homepage):
                page = fetch.get(homepage)
                for paper_title in homepage_titles(page):
                    key = builder.title_key(paper_title)
                    existing = known_titles.get(key)
                    if existing and existing['status'] == 'published':
                        continue
                    url = 'https://api.crossref.org/works?' + urllib.parse.urlencode({'query.title': paper_title, 'rows': 5})
                    matches = [p for p in fetch.json(url, ttl=86400)['message']['items']
                        if builder.title_key(title(p)) == key and member_is_author(member, authors(p))]
                    matches.sort(key=lambda p: p.get('type') == 'posted-content')
                    if matches:
                        accept(matches[0], member, homepage)
                    else:
                        report['unmatchedTitles'].append({'memberId': member['id'], 'title': paper_title, 'source': homepage})
            source_task(homepage, homepage_work)
    records = builder.deduplicate(associate_papers(records, members))
    # Retain existing IDs when accepted/preprint entries acquire a published DOI.
    for paper in records:
        old = next((p for p in original if builder.title_key(p['title']) == builder.title_key(paper['title'])), None)
        if old:
            paper['id'] = old['id']
    validate(records, members)
    papers = publications_since_enrollment(records, members)
    validate(papers, members)
    visible_ids = {p['id'] for p in papers}
    report['excludedByEnrollment'] = [p['id'] for p in records if p['id'] not in visible_ids]
    report['after'] = len(papers)
    report['added'] = [p['title'] for p in papers if not any(
        builder.title_key(p['title']) == builder.title_key(old['title']) for old in original)]
    coverage = {'checkedAt': report['checkedAt'], 'scope': 'Works from student enrollment year onward; unknown enrollment excluded, no graduation cutoff; advisor is a coauthor only.',
        'members': [{'memberId': m['id'], 'name': m['name'],
            'enrollmentYear': m['enrollmentYear'], 'graduationYear': m['graduationYear'],
            'automaticSource': bool(m.get('publicationSources')),
            'publicationIds': [p['id'] for p in papers if m['id'] in p['memberIds']]} for m in students]}
    output = {'members': members, 'papers': [dict(p, authors=', '.join(p['authors'])) for p in papers]}
    javascript = 'const LAB = ' + json.dumps(output, ensure_ascii=False, indent=2) + ';\n'
    # Every file is built and validated before replacing any live file.
    write_json(ROOT / 'data/members.json', members)
    # Preserve excluded works so correcting enrollment years can restore them,
    # even when discovery sources are temporarily unavailable.
    write_json(ROOT / 'data/publications.json', records)
    write_json(ROOT / 'data/publication-coverage.json', coverage)
    write_json(ROOT / 'data/publication-sync-report.json', report)
    atomic_write(ROOT / 'lab-preview/data.js', javascript)
    if args.publish:
        atomic_write(args.publish, javascript)
    print(json.dumps({'publications': len(papers), 'added': report['added'], 'sourceErrors': len(report['issues']),
        'unboundMembers': report['unboundMembers']}, ensure_ascii=False))
    if report['issues'] and not getattr(args, 'allow_source_errors', False):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / '.publication-cache')
    parser.add_argument('--allow-source-errors', action='store_true', help='Publish validated data while reporting individual discovery failures; member validation still blocks publishing')
    parser.add_argument('--offline', action='store_true', help='Replay cached responses for testing')
    registry = parser.add_mutually_exclusive_group()
    registry.add_argument('--members-url', help='Fetch and validate the member JSON from this HTTPS URL before syncing')
    registry.add_argument('--members-repo', type=Path,
                          help='Read data/members.json from FETCH_HEAD of a previously fetched Git repository')
    parser.add_argument('--publish', type=Path, help='Atomically update this website data.js')
    args = parser.parse_args()
    with (ROOT / 'data/.publication-sync.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run(args)


if __name__ == '__main__':
    main()
