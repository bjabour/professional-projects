"""Check generated pages, local links, inline JavaScript and the source bundle.

This is structural and syntax verification, not rendered browser UI testing.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_portfolio import ROOT, EXPORT_ROOT

EXPECTED_TICKET_COUNTS = (17, 17, 18)


class Page(HTMLParser):
    def __init__(self, content: str):
        super().__init__()
        self.ids: set[str] = set()
        self.references: list[str] = []
        self.scripts: list[str] = []
        self.inline_script = False
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if 'id' in attrs:
            assert attrs['id'] not in self.ids, f"Duplicate HTML id: {attrs['id']}"
            self.ids.add(attrs['id'])
        for name in ('href', 'src'):
            if attrs.get(name):
                self.references.append(attrs[name])
        if tag == 'script':
            self.inline_script = not attrs.get('src') and attrs.get('type', '') not in ('application/json', 'application/ld+json')

    def handle_data(self, content):
        if self.inline_script:
            self.scripts.append(content)

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inline_script = False


def validate():
    targets = [ROOT/'index.html', ROOT/'presentation/index.html',
               EXPORT_ROOT/'supportops-control-tower.html', EXPORT_ROOT/'supportops-control-tower-case-study.html']
    references = 0
    for path in targets:
        content = path.read_text(encoding='utf-8')
        assert not re.search(r'__[A-Z_]+__|/\* EMBED_', content), f"Unresolved build token: {path}"
        assert 'C:\\Users\\' not in content and 'C:/Users/' not in content, 'Local machine path in public page'
        page = Page(content)
        for reference in page.references:
            parts = urlsplit(reference)
            if parts.scheme or parts.netloc:
                continue
            destination = (path.parent/unquote(parts.path)).resolve() if parts.path else path
            assert destination.is_file(), f"Missing link/asset: {path.name} -> {reference}"
            if parts.fragment and destination.suffix == '.html':
                target_ids = page.ids if destination == path else Page(destination.read_text(encoding='utf-8')).ids
                assert unquote(parts.fragment) in target_ids, f"Missing anchor: {reference}"
            references += 1
        with tempfile.TemporaryDirectory(prefix='supportops-js-check-') as folder:
            for index, source in enumerate(page.scripts):
                script = Path(folder)/f'inline-{index}.js'
                script.write_text(source, encoding='utf-8')
                subprocess.run(['node','--check',str(script)], check=True, capture_output=True, text=True)
        if 'case-study' in path.name or path.parent.name == 'presentation':
            assert len(re.findall(r'<section class="slide(?: active)?"', content)) == 7, 'Expected seven slides'
    data = json.loads((ROOT/'results/dashboard-data.json').read_text(encoding='utf-8'))
    checks = json.loads((ROOT/'results/control-checks.json').read_text(encoding='utf-8'))
    assert checks['status'] == 'PASS' and checks['failed'] == 0
    assert len(data['dates']) == 3
    assert [run['status'] for run in data['dates']] == ['CLEAR','REVIEW','CRITICAL']
    for index, run in enumerate(data['dates']):
        assert run['provenance']['code_sha256'] == checks['code_sha256']
        assert run['metrics']['ticket_count'] == EXPECTED_TICKET_COUNTS[index]
        assert run['execution_status'] == 'COMPLETED' and run['provenance']['integrity'] == 'VERIFIED'
    with zipfile.ZipFile(ROOT/'source.zip') as bundle:
        names = bundle.namelist()
        for required in ['README.md','supportops/engine.py','scripts/supportops.py','scripts/build_portfolio.py',
                         'scripts/validate_portfolio.py','tests/browser.test.cjs','tests/test_controls.py',
                         'results/dashboard-data.json','results/control-checks.json','presentation/index.html']:
            assert required in names, f"Missing source bundle item: {required}"
        assert not any(name.startswith(('runs/','.locks/','.venv/')) or '__pycache__' in name or name.endswith(('.sqlite3','.pyc')) for name in names)
        assert '../../index.html' not in bundle.read('index.html').decode('utf-8'), 'Extracted home link must be portable'
    result = {'status':'PASS','pages':len(targets),'local_references':references,
              'recorded_dates':len(data['dates']),'engine_controls':checks['passed'],
              'source_bundle_files':len(names),'scope':'Static structure, links, evidence and JavaScript syntax; no rendered browser QA.'}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    validate()
