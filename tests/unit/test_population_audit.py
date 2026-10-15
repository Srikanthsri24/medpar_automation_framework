import json
from medpar_qa.reporting.population_audit import audit_populations,render_population


def test_multiplicity_and_identical_file_proof(tmp_path):
    for name,rows in {'a':[{'id':1},{'id':2}],'b':[{'id':2},{'id':1}],'keep':[{'id':1}],'drop':[{'id':1},{'id':2},{'id':2},{'id':2}]}.items():
        (tmp_path/(name+'.json')).write_text(json.dumps(rows))
    data=audit_populations(tmp_path,'final_action',dict(original=['a.json','b.json'],keep=['keep.json'],drop=['drop.json']),lambda r:(r.data['id'],))
    assert data['datasets']['original']['rows']==4
    assert data['datasets']['original']['identical_file_groups'][0]['files']==['a.json','b.json']
    assert data['excess_output_occurrences']==1 and data['missing_output_occurrences']==0
    assert data['identities_in_both_outputs']==1
    assert data['examples'][0]['original_occurrences']==2
    assert 'Physical rows' in render_population(data)


def test_same_identity_with_different_data_is_not_identical_file(tmp_path):
    (tmp_path/'a.json').write_text('[{"id":1,"amount":10}]')
    (tmp_path/'b.json').write_text('[{"id":1,"amount":20}]')
    data=audit_populations(tmp_path,'final_action',dict(original=['a.json','b.json','a.json'],keep=[],drop=[]),lambda r:(r.data['id'],))
    original=data['datasets']['original']
    assert original['files']==2 and original['rows']==2
    assert original['repeated_identity_rows']==1
    assert original['identical_file_groups']==[]


def test_split_count_balance_excludes_exceptions_from_expected_keep_drop(tmp_path):
    (tmp_path/'original.json').write_text('[{"id":1,"tc":3},{"id":2,"tc":6}]')
    (tmp_path/'keep.json').write_text('[{"id":1,"tc":3}]')
    (tmp_path/'drop.json').write_text('[]')
    data=audit_populations(tmp_path,'split',dict(original=['original.json'],keep=['keep.json'],drop=['drop.json']),lambda r:(r.data['id'],),lambda r:r.data['tc'] not in range(5))
    assert data['source_exception_rows']==1 and data['expected_keep_drop_rows']==1
    assert data['missing_output_occurrences']==0 and data['excess_output_occurrences']==0


def test_merging_stages_do_not_require_equal_physical_row_counts(tmp_path):
    (tmp_path/'original.json').write_text('[{"id":1},{"id":1},{"id":1}]')
    (tmp_path/'keep.json').write_text('[{"id":1}]')
    data=audit_populations(tmp_path,'stay',dict(original=['original.json'],keep=['keep.json'],drop=[]),lambda r:(r.data['id'],),one_to_one=False)
    assert data['expected_keep_drop_rows'] is None
    assert data['missing_output_occurrences'] is None
    assert not data['count_comparison_applicable']
    assert 'merging' in data['conclusion']
