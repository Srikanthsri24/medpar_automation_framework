from html.parser import HTMLParser
from medpar_qa.reporting.stage_drilldown import file_rows,comparisons


class Table(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=[];self.cell=False
    def handle_starttag(self,t,a):
        if t=='tr':self.row=[]
        if t=='td':self.cell=True;self.row.append('')
    def handle_endtag(self,t):
        if t=='td':self.cell=False
        if t=='tr' and self.row:self.rows.append(self.row)
    def handle_data(self,d):
        if self.cell:self.row[-1]+=d


def test_per_file_continuation_uses_verified_handoff_not_just_keep(tmp_path):
    report=str(tmp_path/'connected/g1/stay/report.json')
    rows=[dict(file='a.json',decision='KEEP',checks=[{'event_id':report+'#check-1'}]) for _ in range(2)]
    rows += [dict(file='b.json',decision='KEEP',checks=[{'event_id':report+'#check-1'}])]
    files=[dict(file=n,total_rows=num,selected_rows=num,context_rows=0,decisions={'KEEP':num}) for n,num in [('a.json',2),('b.json',1)]]
    audit=dict(rows=rows,files=files,input_kind='supplied_original')
    table=Table();table.feed(file_rows(tmp_path,[(audit,tmp_path/'stay/row_review.html')],{report}))
    assert [r[-1] for r in table.rows]==['2','1']
    table=Table();table.feed(file_rows(tmp_path,[(audit,tmp_path/'stay/row_review.html')],set()))
    assert [r[-1] for r in table.rows]==['0','0']
    assert 'not the number of generated output rows' in file_rows(tmp_path,[(audit,tmp_path/'stay/row_review.html')],set())


def test_keep_drop_comparisons_show_scope_references_and_distinct_results(tmp_path):
    audit=dict(input_kind='supplied_original',rows=[dict(decision='KEEP',comparison_status='PASS'),dict(decision='DROP',comparison_status='FAIL')],comparison_status='FAIL',comparison_rows={'keep':100,'drop':50},comparison_files={r:[dict(file=r+'.json',origin='s3://bucket/'+r+'.json')] for r in ('keep','drop')})
    html=comparisons(tmp_path,[(audit,tmp_path/'row_review.html')])
    assert 'Calculated KEEP versus supplied KEEP' in html and 'Calculated DROP versus supplied DROP' in html
    assert '100 rows in whole reference dataset' in html and '50 rows in whole reference dataset' in html
    assert 's3://bucket/keep.json' in html
    table=Table();table.feed(html)
    assert table.rows[0][4]=='PASS' and table.rows[1][4]=='FAIL'


def test_empty_sample_does_not_certify_supplied_output(tmp_path):
    audit=dict(input_kind='supplied_original',rows=[],comparison_rows={'keep':2},comparison_files={'keep':[dict(file='keep.json')]})
    html=comparisons(tmp_path,[(audit,tmp_path/'row_review.html')])
    assert 'NOT ASSESSED — no KEEP decisions in this sample' in html
    assert 'NOT PROVIDED' in html


def test_reference_counts_deduplicate_identity_and_keep_full_multiplicity(tmp_path):
    from medpar_qa.reporting.stage_drilldown import reference_cell
    row=dict(row=1,decision='KEEP',input_row={'icn':'A'},comparison_status='BLOCKED',checks=[dict(rule_id='ROW-OUTPUT-MEMBERSHIP',actual={'keep':7,'drop':2},evidence={'keep':[{'file':'kept.json','row':1}]})])
    audit=dict(identity_fields=['icn'],comparison_rows={'keep':100},comparison_files={'keep':[dict(file='kept.json',rows=100)]})
    html=reference_cell(tmp_path,audit,[row,row],tmp_path/'row_review.html',1,'keep')
    assert '2 / 2 found' in html and '2 unverified' in html
    evidence=next(tmp_path.glob('reference_*.html')).read_text()
    assert '7 matching reference rows' in evidence
    assert 'kept.json' in evidence and 'BLOCKED' in evidence
    assert 'Count equality alone does not prove a data match' in evidence
    assert reference_cell(tmp_path,audit,[row],tmp_path/'row_review.html',1,'drop')=='<td>Not supplied</td>'


def test_reference_comparison_uses_only_same_decision_rows(tmp_path):
    from medpar_qa.reporting.stage_drilldown import reference_cell
    records=[dict(row=i,decision=decision,input_row={'icn':str(i)},comparison_status=status,checks=[]) for i,decision,status in [(1,'KEEP','PASS'),(2,'KEEP','FAIL'),(3,'KEEP','BLOCKED'),(4,'DROP','PASS')]]
    audit=dict(identity_fields=['icn'],comparison_rows={'keep':1000},comparison_files={'keep':[dict(file='reference.json',rows=1000)]})
    html=reference_cell(tmp_path,audit,records,tmp_path/'row_review.html',1,'keep')
    assert '0 / 3 found' in html
    assert '1 verified · 1 mismatched · 1 unverified' in html
    assert '1000' not in html
    proof=next(tmp_path.glob('reference_*.html')).read_text()
    assert '1000 rows in 1 files' in proof
    assert '<td>DROP</td>' not in proof


def test_row_comparison_normalizes_lossless_numeric_text_only():
    from medpar_qa.reporting.row_report import compare_row_values
    from medpar_qa.enums import Stage
    def compare(expected,actual):return compare_row_values(stage=Stage.FINAL_ACTION,rule_id='TEST',field_name='value',expected=expected,actual=actual,record_ids=[],source_files=[])
    assert compare(1,'1').status=='PASS'
    assert compare({'nested':[0,1]},{'nested':['0','1']}).status=='PASS'
    assert compare('001',1).status=='FAIL'
    assert compare(1,'2').status=='FAIL'
    assert compare(True,'True').status=='FAIL'
    assert compare(1,'1').evidence['representation_normalization']['raw_actual']=='1'
