"""Run the synthetic five-stage example through unmodified real processors.

Candidate JSON outputs are supplied fixtures, not generated production outputs or
approved CMS golden files. Missing optional/reference/physical-layout checks remain
visible as N/A. The input identifiers and drug number are fictitious.
"""
from pathlib import Path
import html
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from medpar_qa.orchestration.connected import STAGES, run_configured
from medpar_qa.reporting.run_layout import ReportSession


def demo_config():
    """Configure one synthetic source and independently supplied downstream candidates."""
    config = {stage.value: {'run_date': '2026-03-20'} for stage in STAGES}
    config['final_action'].update(enabled=True, single_files=[{
        'source': ['data/demo_connected/claims.json'],
        'pipeline_outputs': {stage: [f'data/demo_connected/{stage}_candidate.json']
                             for stage in ('stay', 'intermediate', 'final_medpar')},
    }])
    return config


def run_demo(root=PROJECT_ROOT, session=None):
    """Generate auditable connected reports and add a prominent scope/coverage statement."""
    session = session or ReportSession.create(project_root=root)
    journeys, index = run_configured(root, session, demo_config())
    rows = []
    for journey, directory in journeys:
        for step in journey['steps']:
            report = json.loads((directory / step['stage'] / 'report.json').read_text())
            checks = report['stages'][0]['rule_results']
            counts = {status: sum(check['status'] == status for check in checks)
                      for status in ('PASS', 'FAIL', 'BLOCKED', 'NOT_APPLICABLE')}
            rows.append('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in
                (step['stage'], step['status'], *counts.values())) + '</tr>')
        notice = ('<section style="background:#fff4cf;padding:24px;border:2px solid #b88700">'
            '<h2>SYNTHETIC DEMONSTRATION — supported JSON validation workflow</h2>'
            '<p>This fictitious claim is designed to demonstrate Final Action → Split → Stay → Intermediate → Final MEDPAR. Review the actual outcomes below. '
            'All five real stage processors execute with their default business rules. '
            'Final Action and Split calculate retained outputs; later stages validate supplied candidate JSON outputs.</p>'
            '<p>Worked expectations: QC1 is retained; January 2026 maps to Y00109; a single interim bill has '
            'warning 01=0 and warning 05=0; empty condition lists give N/N switches and no sequestration value '
            'gives amount 0. Date of birth 1 January 1950 gives age 76 on admission. No surgeries or diagnoses '
            'give zero counts. The fictitious 11-digit NDC is copied from its revenue line. Final classification is S.</p>'
            '<p>N/A checks do not establish coverage. Approved golden outputs, external reference calculations '
            'and the complete 3000-byte physical layout are not certified by this example. '
            'This report does not change or certify production results.</p></section>')
        page = directory / 'index.html'
        page.write_text(page.read_text().replace('<h1>Input file journey</h1>', notice + '<h1>Input file journey</h1>'))
    coverage = '<h2>Executed validation coverage</h2><table><tr><th>Stage</th><th>Outcome</th><th>Pass</th><th>Fail</th><th>Blocked</th><th>N/A</th></tr>' + ''.join(rows) + '</table>'
    index.write_text(index.read_text().replace('<h1>', notice + coverage + '<h1>', 1))
    return journeys, index


if __name__ == '__main__':
    journeys, index = run_demo()
    print(f'Synthetic five-stage demonstration: {index}')
    raise SystemExit(0 if all(journey['completed'] for journey, _ in journeys) else 1)
