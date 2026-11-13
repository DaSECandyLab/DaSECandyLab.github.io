"""Regression checks for publication identity, versions, and failed-source retention."""
import argparse
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sync', ROOT / 'scripts/sync-publications.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class PublicationsTest(unittest.TestCase):
    def setUp(self):
        self.papers = json.loads((ROOT / 'data/publications.json').read_text())
        self.members = json.loads((ROOT / 'data/members.json').read_text())
        self.paper = next(p for p in self.papers if p['id'] == 'aqetuner')

    def test_preprint_merges_with_published_and_preserves_members(self):
        preprint = copy.deepcopy(self.paper)
        preprint.update(id='preprint-aqe', status='preprint', url='https://arxiv.org/abs/2504.11756')
        preprint.pop('doi')
        preprint['memberIds'] = ['lixiang-chen']
        merged = sync.builder.deduplicate([preprint, self.paper])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['id'], 'aqetuner')
        self.assertEqual(merged[0]['status'], 'published')
        self.assertIn('yu-chen', merged[0]['memberIds'])

    def test_doi_case_and_title_variants(self):
        duplicate = copy.deepcopy(self.paper)
        duplicate.update(id='duplicate', doi=self.paper['doi'].upper(), url=self.paper['url'].upper())
        duplicate['title'] = duplicate['title'].replace('-', ' ')
        self.assertEqual(len(sync.builder.deduplicate([duplicate, self.paper])), 1)

    def test_distinct_journal_extension_is_preserved(self):
        extension = copy.deepcopy(self.paper)
        extension.update(id='extension', doi='10.1234/extension', url='https://doi.org/10.1234/extension',
                         title='Query-Level Configuration: A New Journal Extension', alternateUrls=[])
        self.assertEqual(len(sync.builder.deduplicate([self.paper, extension])), 2)

    def test_bound_member_must_be_an_author(self):
        member = next(m for m in self.members if m['id'] == 'haoyu-wang')
        with self.assertRaises(ValueError):
            sync.from_crossref({'author': [{'given': 'Different', 'family': 'Person'}]}, member, self.members, 'https://example.com')

    def test_author_ambiguity_and_student_scope(self):
        sync.validate(self.papers, self.members)
        pisco = next(p for p in self.papers if p['id'] == 'pisco')
        self.assertNotIn('yu-chen', pisco['memberIds'])  # Yuxing Chen is not Yu Chen.
        self.assertTrue(all(any(mid != 'chengcheng-yang' for mid in p['memberIds']) for p in self.papers))
        self.assertTrue(all(not m.get('publicationSources') for m in self.members if m['role'] == 'advisor'))

    def test_homepage_only_records_do_not_reappear_during_sync(self):
        unsupported = copy.deepcopy(self.paper)
        unsupported.update(id='homepage-announcement', title='Homepage-only announcement',
                           status='accepted', url='https://example.org/#publications', alternateUrls=[])
        unsupported.pop('doi')
        self.assertFalse(sync.builder.has_publication_record(unsupported))
        self.assertTrue(sync.builder.has_publication_record(self.paper))
        arxiv = dict(unsupported, url='https://arxiv.org/abs/2607.27056', status='preprint')
        self.assertTrue(sync.builder.has_publication_record(arxiv))
        for url in ['https://arxiv.org/', 'https://arxiv.org.evil.example/abs/2607.27056']:
            self.assertFalse(sync.builder.has_publication_record(dict(arxiv, url=url)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/members.json').write_text(json.dumps(self.members))
            (root / 'data/publications.json').write_text(json.dumps(self.papers + [unsupported]))
            args = argparse.Namespace(cache=root / 'cache', offline=False,
                                      publish=root / 'public/data.js', allow_source_errors=True)
            with patch.object(sync, 'ROOT', root), patch.object(sync.Fetcher, 'get', side_effect=OSError('outage')):
                sync.run(args)
            output = json.loads(args.publish.read_text()[len('const LAB = '):].rstrip(';\n'))
            self.assertNotIn(unsupported['id'], [p['id'] for p in output['papers']])
            self.assertIn('setoka', [p['id'] for p in output['papers']])
            report = json.loads((root / 'data/publication-sync-report.json').read_text())
            self.assertEqual(report['excludedWithoutPublicationRecord'], [unsupported['id']])
            self.assertNotIn(unsupported['id'], report['excludedByEnrollment'])

    def test_source_outages_preserve_existing_papers_and_live_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/members.json').write_text(json.dumps(self.members))
            (root / 'data/publications.json').write_text(json.dumps(self.papers))
            args = argparse.Namespace(cache=root / 'cache', offline=False, publish=root / 'public/data.js')
            with patch.object(sync, 'ROOT', root), patch.object(sync.Fetcher, 'get', side_effect=OSError('source unavailable')):
                with self.assertRaises(SystemExit):
                    sync.run(args)
            kept = json.loads((root / 'data/publications.json').read_text())
            self.assertEqual(kept, self.papers)
            self.assertIn('const LAB = ', args.publish.read_text())
            report = json.loads((root / 'data/publication-sync-report.json').read_text())
            visible = sync.publications_since_enrollment(self.papers, self.members)
            self.assertEqual(report['after'], len(visible))
            output = json.loads(args.publish.read_text()[len('const LAB = '):].rstrip(';\n'))
            self.assertEqual([p['id'] for p in output['papers']], [p['id'] for p in visible])
            self.assertTrue(report['issues'])
            # Pages can publish a validated snapshot despite a discovery outage.
            args.allow_source_errors = True
            with patch.object(sync, 'ROOT', root), patch.object(sync.Fetcher, 'get', side_effect=OSError('source unavailable')):
                sync.run(args)
            self.assertEqual(json.loads((root / 'data/publications.json').read_text()), self.papers)
            # The opt-in must not bypass registry validation or replace live data.
            before = args.publish.read_text()
            invalid = [dict(self.members[1], graduationYear=1900)]
            (root / 'data/members.json').write_text(json.dumps(invalid))
            with patch.object(sync, 'ROOT', root), self.assertRaises(ValueError):
                sync.run(args)
            self.assertEqual(args.publish.read_text(), before)


if __name__ == '__main__':
    unittest.main()
