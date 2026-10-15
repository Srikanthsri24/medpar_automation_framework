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
