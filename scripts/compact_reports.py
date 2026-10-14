"""Retry report packaging without rerunning stage processing."""
from pathlib import Path
import argparse
import sys

PROJECT_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT_ROOT/'src'))
from medpar_qa.reporting.compact import compact_reports

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_folder',type=Path,help='Existing timestamped report folder')
    args=parser.parse_args()
    root=args.report_folder if args.report_folder.is_absolute() else PROJECT_ROOT/args.report_folder
    if not root.is_dir() or not any(root.rglob('*.html')):parser.error('Report folder must exist and contain HTML reports')
    print('Master report:',compact_reports(root))
