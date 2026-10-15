import json
from medpar_qa.reporting.row_dashboard import row_browser,render_overview,unmapped_leaves
from medpar_qa.normalization.fields import FieldResolver


def test_row_browser_preserves_all_evidence_without_rendering_all_cards():
    rows=[dict(row=i,decision='KEEP',validation_status='PASS',comparison_status='PASS') for i in range(1,24)]
    markup=row_browser(1,rows,['<details>proof '+str(i)+'</details>' for i in range(23)])
    payload=json.loads(markup.split('class="row-data">')[1].split('</script>')[0])
    assert len(payload)==23 and payload[-1]['row']==23
    assert '<details>proof' not in markup
    assert 'View next 10' in markup and 'All comparisons' in markup


def test_embedded_evidence_cannot_close_json_script():
    row=dict(row=1,decision='KEEP',validation_status='PASS',comparison_status='PASS')
    markup=row_browser(1,[row],['</script><script>alert(1)</script>'])
    assert markup.count('</script>')==1


def test_unmapped_nested_values_remain_in_data_comparison():
    resolver=FieldResolver({'provider_id':['provider.id']})
    assert unmapped_leaves({'provider':{'id':'1'},'other':{'amount':5},'lines':[1,2]},resolver)==[('other.amount',5),('lines',[1,2])]


def test_chart_scope_distinguishes_sample_from_whole_output():
    body=render_overview(dict(decision_counts={'KEEP':2},scoped_output_rows={'keep':2,'drop':0},comparison_rows={'keep':100,'drop':3},comparison_outcomes={'PASS':2}))
    assert 'All supplied output rows' in body and 'Sample results apply only' in body
    assert '<td>2</td><td>2</td><td>100</td>' in body
