"""Registry editing, remote sync and existing-paper association regressions."""
import argparse
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from member_registry import (associate_papers, load_members,
                             publications_since_enrollment, validate_members)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sync', ROOT / 'scripts/sync-publications.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def new_member(**fields):
    member = dict(id='new-student', name='New Student', role='student', enrollmentYear=2024,
                  graduationYear=None, publicationSources={})
    member.update(fields)
    return member


class MembersTest(unittest.TestCase):
    def setUp(self):
        self.members = load_members(ROOT / 'data/members.json')
        self.papers = json.loads((ROOT / 'data/publications.json').read_text())

    def test_registry_inferred_years_have_traceable_evidence(self):
        for member in self.members:
            evidence = member.get('yearEvidence', {})
            if evidence.get('status') == 'inferred':
                self.assertTrue(evidence['note'])
                source = evidence['source']
                if not source.startswith('https://'):
                    self.assertTrue(source.startswith('content/'))
                    self.assertRegex(evidence['sourceCommit'], r'^[0-9a-f]{7,40}$')

    def test_invalid_years_and_duplicate_id_fail_before_render(self):
        for field, value in [('enrollmentYear', True), ('graduationYear', '2026'), ('graduationYear', 2000)]:
            roster = copy.deepcopy(self.members)
            roster[1][field] = value
            with self.assertRaises(ValueError):
                validate_members(roster)
        with self.assertRaises(ValueError):
            validate_members(self.members + [self.members[0]])

    def test_alias_collision_and_advisor_discovery_are_rejected(self):
        roster = copy.deepcopy(self.members)
        roster[1]['publicationNames'] = [roster[2]['name']]
        with self.assertRaises(ValueError):
            validate_members(roster)
        roster = copy.deepcopy(self.members)
        roster[0]['publicationSources'] = {'orcid': '0000-0001-5128-8882'}
        with self.assertRaises(ValueError):
            validate_members(roster)

    def test_new_member_relinks_existing_paper_without_fetch(self):
        roster = self.members + [new_member()]
        paper = copy.deepcopy(self.papers[0])
        paper['authors'].append('New Student')
        updated = associate_papers([paper], roster)
        self.assertIn('new-student', updated[0]['memberIds'])
        self.assertNotIn('new-student', paper['memberIds'])
        self.assertEqual(len(updated), 1)

    def test_aliases_match_full_names_and_no_stale_ids_remain(self):
        member = new_member(publicationNames=['New Full Name'])
        paper = copy.deepcopy(self.papers[0])
        paper['authors'] = ['new full name']
        paper['memberIds'] = ['removed-member']
        updated = associate_papers([paper], [member])
        self.assertEqual(updated[0]['memberIds'], ['new-student'])
        paper['authors'] = ['N. Full Name']
        self.assertEqual(associate_papers([paper], [member]), [])

    def test_alumni_papers_are_retained(self):
        roster = copy.deepcopy(self.members)
        for member in roster:
            if member['role'] == 'student':
                member['enrollmentYear'], member['graduationYear'] = 2000, 2003
        result = associate_papers(self.papers, roster)
        self.assertEqual(len(result), len(self.papers))

    def test_publications_start_in_enrollment_year_without_graduation_cutoff(self):
        member = new_member()
        member['graduationYear'] = 2026
        paper = copy.deepcopy(self.papers[0])
        paper['authors'] = ['New Student']
        for year, included in [(2023, False), (2024, True), (2026, True), (2030, True)]:
            paper['year'] = year
            self.assertEqual(bool(publications_since_enrollment([paper], [member])), included)
        member['enrollmentYear'] = None
        self.assertEqual(publications_since_enrollment([paper], [member]), [])

    def test_any_enrolled_student_qualifies_but_advisor_alone_does_not(self):
        early = new_member()
        later = dict(new_member(), id='later-student', name='Later Student', enrollmentYear=2027)
        advisor = next(m for m in self.members if m['role'] == 'advisor')
        paper = copy.deepcopy(self.papers[0])
        paper.update(year=2025, authors=['New Student', 'Later Student', advisor['name']])
        visible = publications_since_enrollment([paper], [early, later, advisor])
        self.assertEqual(visible[0]['memberIds'], ['new-student', advisor['id']])
        self.assertEqual(visible[0]['authors'], paper['authors'])
        self.assertEqual(publications_since_enrollment([paper], [later, advisor]), [])

    def test_filter_uses_published_version_year_and_recomputes_merged_associations(self):
        member = new_member()
        published = copy.deepcopy(self.papers[0])
        published.update(year=2024, authors=['New Student'], status='published')
        preprint = dict(published, year=2023, status='preprint', id='old-preprint')
        records = sync.builder.deduplicate([preprint, published])
        visible = publications_since_enrollment(records, [member])
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]['year'], 2024)
        self.assertEqual(visible[0]['memberIds'], ['new-student'])

    def test_sync_preserves_excluded_archive_for_year_correction_during_outage(self):
        member = new_member(publicationSources={'orcid': '0009-0006-3448-3831'})
        paper = copy.deepcopy(self.papers[0])
        paper.update(year=2023, authors=['New Student'], memberIds=['new-student'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            registry = root / 'data/members.json'
            archive = root / 'data/publications.json'
            archive.write_text(json.dumps([paper]))
            args = argparse.Namespace(cache=root / 'cache', offline=False, publish=root / 'public/data.js')
            for enrollment, expected in [(2024, 0), (2023, 1)]:
                member['enrollmentYear'] = enrollment
                registry.write_text(json.dumps([member]))
                with patch.object(sync, 'ROOT', root), patch.object(sync.Fetcher, 'get', side_effect=OSError('outage')):
                    with self.assertRaises(SystemExit):
                        sync.run(args)
                output = json.loads(args.publish.read_text()[len('const LAB = '):].rstrip(';\n'))
                self.assertEqual(len(output['papers']), expected)
                self.assertEqual(json.loads(archive.read_text()), [paper])

    def test_missing_photo_allowed_but_path_traversal_rejected(self):
        self.assertTrue(validate_members([new_member()]))
        with self.assertRaises(ValueError):
            validate_members([new_member(photo='assets/../../private.png')])

    def test_remote_registry_drives_output_and_new_member_association(self):
        roster = copy.deepcopy(self.members)
        for member in roster:
            member['publicationSources'] = {}
        roster.append(new_member())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/members.json').write_text(json.dumps(self.members))
            papers = copy.deepcopy(self.papers)
            papers[0]['authors'].append('New Student')
            (root / 'data/publications.json').write_text(json.dumps(papers))
            args = argparse.Namespace(cache=root / 'cache', offline=False, publish=root / 'public/data.js', members_url='https://example.org/members.json')
            with patch.object(sync, 'ROOT', root), patch.object(sync.Fetcher, 'json', return_value=roster):
                sync.run(args)
            output = json.loads(args.publish.read_text()[len('const LAB = '):].rstrip(';\n'))
            self.assertEqual(len(output['members']), len(roster))
            self.assertTrue(any('new-student' in p['memberIds'] for p in output['papers']))
            self.assertEqual(json.loads((root / 'data/members.json').read_text()), roster)

    def test_invalid_or_unavailable_remote_registry_preserves_live_file(self):
        for failure in [[], OSError('network unavailable')]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'data').mkdir()
                (root / 'data/members.json').write_text(json.dumps(self.members))
                (root / 'data/publications.json').write_text(json.dumps(self.papers))
                live = root / 'live.js'
                live.write_text('existing live data')
                args = argparse.Namespace(cache=root / 'cache', offline=False, publish=live, members_url='https://example.org/members.json')
                kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
                with patch.object(sync, 'ROOT', root), patch.object(sync.Fetcher, 'json', **kwargs):
                    with self.assertRaises((ValueError, OSError)):
                        sync.run(args)
                self.assertEqual(live.read_text(), 'existing live data')
                self.assertEqual(json.loads((root / 'data/members.json').read_text()), self.members)

    def test_git_snapshot_drives_registry_without_network_or_live_partial_writes(self):
        roster = copy.deepcopy(self.members)
        for member in roster:
            member['publicationSources'] = {}
        roster.append(new_member())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'registry'
            (repo / 'data').mkdir(parents=True)
            (repo / 'data/members.json').write_text(json.dumps(roster))
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.STDOUT)
            git('init')
            git('add', 'data/members.json')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.org',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'Registry fixture')
            git('fetch', '.', 'HEAD')
            (root / 'data').mkdir()
            registry = root / 'data/members.json'
            registry.write_text(json.dumps(self.members))
            (root / 'data/publications.json').write_text(json.dumps(self.papers))
            args = argparse.Namespace(cache=root / 'cache', offline=False,
                members_repo=repo, publish=root / 'public/data.js')
            with patch.object(sync, 'ROOT', root):
                sync.run(args)
            self.assertEqual(json.loads(registry.read_text()), roster)
            previous = args.publish.read_text()
            (repo / '.git/FETCH_HEAD').unlink()
            with patch.object(sync, 'ROOT', root):
                with self.assertRaises(subprocess.CalledProcessError):
                    sync.run(args)
            self.assertEqual(args.publish.read_text(), previous)


if __name__ == '__main__':
    unittest.main()
