"""Check R65 Intermediate/Final exact lineage, routing and reconciliation evidence."""
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
from medpar_qa.stages.final_medpar.archive_audit import audit_archive
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.reporting.run_layout import ReportSession
from medpar_qa.reporting.report_bundle import write_report_bundle
from medpar_qa.reporting.session_index import refresh_session_indexes


def run_audit(session=None):
    session = session or ReportSession.create(project_root=PROJECT_ROOT)
    resolver = FieldResolver.from_yaml(PROJECT_ROOT / 'config/field_aliases.yaml')
    result = audit_archive(PROJECT_ROOT / 'data/production/r65', current_year=2024, resolver=resolver)
    directory = session.command_directory('final_medpar', 'r65_lineage_routing_reconciliation')
    bundle = write_report_bundle(run_id='r65_archive_audit', results=[result], output_directory=directory,
        title='R65 Final MEDPAR — lineage, routing and reconciliation', parent_link='../../master/index.html',
        context={'current_year': 2024, 'dataset': 'R65 DEV Q2 2025', 'scope': 'Supplied JSON evidence; not CMS physical-byte certification'})
    index = refresh_session_indexes(session.root)
    print(f'R65 evidence report: {bundle.html}')
    print(f'Master report: {index}')
    print(f'Counts: {result.status_counts}')
    return result


if __name__ == '__main__':
    raise SystemExit(0 if run_audit().passed else 1)
