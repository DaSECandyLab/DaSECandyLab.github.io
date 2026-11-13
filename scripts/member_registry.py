"""Validation and author association for the shared member registry."""
import copy
import json
import re
import unicodedata
from pathlib import PurePosixPath
from urllib.parse import urlsplit


def author_key(name):
    return ' '.join(unicodedata.normalize('NFKC', name).casefold().split())


def author_names(member):
    return [member['name'], *member.get('publicationNames', [])]


def member_is_author(member, authors):
    return bool({author_key(n) for n in author_names(member)} & {author_key(n) for n in authors})


def match_member_ids(authors, members):
    return [m['id'] for m in members if member_is_author(m, authors)]


def validate_members(members):
    if not isinstance(members, list) or not members:
        raise ValueError('members.json must contain a nonempty array')
    ids, names = set(), {}
    for member in members:
        if not isinstance(member, dict):
            raise ValueError('Every member must be an object')
        mid = member.get('id')
        if not isinstance(mid, str) or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', mid) or mid in ids:
            raise ValueError('Invalid or duplicate member ID: ' + str(mid))
        ids.add(mid)
        if not isinstance(member.get('name'), str) or not member['name'].strip():
            raise ValueError(mid + ': name is required')
        if member.get('role') not in ('advisor', 'student'):
            raise ValueError(mid + ': role must be advisor or student; alumni status is derived from years')
        for key in ('enrollmentYear', 'graduationYear'):
            if key not in member or (member[key] is not None and
                    (type(member[key]) is not int or not 1900 <= member[key] <= 2200)):
                raise ValueError(mid + ': ' + key + ' must be an integer year or null')
        start, end = member['enrollmentYear'], member['graduationYear']
        if start is not None and end is not None and end < start:
            raise ValueError(mid + ': graduationYear precedes enrollmentYear')
        if member.get('degree') not in (None, 'masters', 'phd'):
            raise ValueError(mid + ': degree must be masters, phd or null')
        aliases = member.get('publicationNames', [])
        if not isinstance(aliases, list) or any(not isinstance(a, str) or not a.strip() for a in aliases):
            raise ValueError(mid + ': publicationNames must be full-name strings')
        for name in author_names(member):
            key = author_key(name)
            if key in names and names[key] != mid:
                raise ValueError(mid + ': author name is already assigned to ' + names[key])
            names[key] = mid
        photo = member.get('photo')
        if photo is not None:
            if not isinstance(photo, str):
                raise ValueError(mid + ': photo must be a local asset path or null')
            path = PurePosixPath(photo)
            if not photo.startswith('assets/') or '..' in path.parts or '\\' in photo or urlsplit(photo).query or urlsplit(photo).fragment:
                raise ValueError(mid + ': photo must stay under assets/')
        sources = member.get('publicationSources', {})
        if not isinstance(sources, dict) or set(sources) - {'orcid', 'homepage'}:
            raise ValueError(mid + ': unsupported publicationSources fields')
        if member['role'] == 'advisor' and sources:
            raise ValueError(mid + ': advisors are coauthors, not publication discovery sources')
        if 'orcid' in sources and (not isinstance(sources['orcid'], str) or
                not re.fullmatch(r'\d{4}-\d{4}-\d{4}-[\dX]{4}', sources['orcid'])):
            raise ValueError(mid + ': invalid ORCID')
        if 'homepage' in sources:
            if not isinstance(sources['homepage'], str):
                raise ValueError(mid + ': homepage must be a public HTTPS URL')
            url = urlsplit(sources['homepage'])
            if url.scheme != 'https' or not url.netloc or url.username or url.password:
                raise ValueError(mid + ': homepage must be a public HTTPS URL')
        evidence = member.get('yearEvidence', {})
        if not isinstance(evidence, dict) or evidence.get('status') not in (None, 'inferred', 'confirmed', 'unknown', 'not-applicable'):
            raise ValueError(mid + ': invalid yearEvidence status')
        if evidence.get('status') == 'inferred' and (not evidence.get('source') or not evidence.get('note')):
            raise ValueError(mid + ': inferred years need their source and inference note')
    return members


def load_members(path):
    return validate_members(json.loads(path.read_text()))


def associate_papers(records, members):
    """Recompute associations from full author names, including current alumni.

    Records have already been identity-verified by their discovery source. Never
    use these name matches alone to import a record from an author-name search.
    """
    student_ids = {m['id'] for m in members if m['role'] == 'student'}
    result = []
    for record in records:
        paper = copy.deepcopy(record)
        if not isinstance(paper.get('authors'), list):
            raise ValueError('Publication authors must be a list of full names')
        paper['memberIds'] = match_member_ids(paper['authors'], members)
        if student_ids.intersection(paper['memberIds']):
            result.append(paper)
    return result


def publications_since_enrollment(records, members):
    """Select deduplicated works with at least one student enrolled that year.

    Keep the full bibliographic author list, but link only eligible members.
    Unknown enrollment years cannot establish eligibility; graduation is not a
    cutoff. The caller retains the unfiltered archive for later year corrections.
    """
    lookup = {m['id']: m for m in members}
    result = []
    for paper in associate_papers(records, members):
        if type(paper.get('year')) is not int:
            raise ValueError('Publication year must be an integer')
        paper['memberIds'] = [mid for mid in paper['memberIds']
            if lookup[mid]['role'] == 'advisor' or (
                lookup[mid]['enrollmentYear'] is not None and
                paper['year'] >= lookup[mid]['enrollmentYear'])]
        if any(lookup[mid]['role'] == 'student' for mid in paper['memberIds']):
            result.append(paper)
    return result
