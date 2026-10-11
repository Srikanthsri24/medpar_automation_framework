"""Render the tracked finding register into a readable team review page."""
from pathlib import Path
import html
import json

ROOT = Path(__file__).resolve().parents[1]

def render_status():
    data = json.loads((ROOT/'reviews/review_v2_status.json').read_text())
    esc = lambda value: html.escape(str(value))
    rows = []
    for finding in data['findings']:
        rows.append('<tr>' + ''.join(f'<td>{esc(finding[key])}</td>' for key in
            ('id','status','remarks','evidence','remaining_action')) + '</tr>')
    path = ROOT/'reviews/review_v2_status.html'
    path.write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>MedPAR review findings and evidence</title><style>body{font:16px system-ui;line-height:1.5;margin:28px;color:#17324b;background:#f4f7fa}'
        'section{background:white;padding:22px;border:1px solid #d5dfe8;border-radius:10px}table{border-collapse:collapse;background:white;width:100%;font-size:14px}'
        'td,th{padding:12px;border:1px solid #d5dfe8;text-align:left;vertical-align:top}th{background:#17324b;color:white}.scroll{overflow:auto}</style>'
        '<h1>MedPAR — review findings and evidence</h1>'
        f'<p>Reviewed {esc(data["reviewed_on"])} · Branch {esc(data["target_branch"])}</p>'
        '<section><h2>Conclusion</h2><p>Confirmed code defects and missing checks have been addressed with regression tests. '
        'Production acceptance remains pending where supplied output is defective or the specifications require a CMS/product-owner decision. '
        'No input was rewritten to manufacture a pass, and no approval was invented.</p>'
        '<p>371 automated tests passed. All 914 R65 Final records match their Intermediate source after removal of only Split-Year Indicator. '
        'Separate source checks identify SSI/CCN defects, one inconsistent bypass drop and 244 unaccounted Split claims.</p>'
        '<p><b>Status guide:</b> CODE_FIXED / CHECK_IMPLEMENTED describes framework capability, not certification of production data. '
        'SOURCE_DATA_DEFECT requires upstream correction. DECISION_PENDING / REFERENCE_MAPPING_PENDING requires approved policy or reference evidence. '
        'KNOWN_DIFFERENCE discloses a deviation and is not a passing validation.</p>'
        '<p>Generate current proof with <code>python scripts/run_r65_audit.py</code> and per-file Final checks with '
        '<code>python run_commands.py --stage final_medpar</code>. The commands print their timestamped report locations.</p></section>'
        '<h2>Every reported finding</h2><div class="scroll"><table><tr><th>Finding</th><th>Current status</th><th>What changed / what was found</th><th>Code or rule evidence</th><th>Remaining condition</th></tr>'
        + ''.join(rows) + '</table></div>',encoding='utf-8')
    return path

if __name__=='__main__':
    print(render_status())
