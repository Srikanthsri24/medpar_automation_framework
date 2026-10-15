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
