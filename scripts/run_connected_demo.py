"""Run the synthetic five-stage example through unmodified real processors.

Candidate JSON outputs are supplied fixtures, not generated production outputs or
approved CMS golden files. Missing optional/reference/physical-layout checks remain
visible as N/A. The input identifiers and drug number are fictitious.
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from medpar_qa.orchestration.connected import STAGES, run_configured
from medpar_qa.reporting.run_layout import ReportSession


def demo_config():
    """Configure one synthetic source and independently supplied downstream candidates."""
    config = {stage.value: {'run_date': '2026-04-20'} for stage in STAGES}
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
    from medpar_qa.reporting.connected_review import write_connected_review
    write_connected_review(journeys, index, synthetic=True)
    return journeys, index


if __name__ == '__main__':
    journeys, index = run_demo()
    print(f'Synthetic five-stage demonstration: {index}')
    raise SystemExit(0 if all(journey['completed'] for journey, _ in journeys) else 1)
