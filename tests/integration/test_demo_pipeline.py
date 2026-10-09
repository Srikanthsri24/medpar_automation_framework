"""Real cross-stage execution tests using output of each preceding stage."""
import json
from pathlib import Path

import pytest

from medpar_qa.demo_pipeline import run_pipeline, load_claims, split_claims, stay_claims, final_medpar

ROOT = Path(__file__).resolve().parents[2]


def test_demo_end_to_end(tmp_path):
    report = run_pipeline(ROOT / 'data/demo_v3/demo_claims.json', tmp_path, 2024, ROOT / 'config/field_aliases.yaml')
    stages = report['stages']
    assert stages['final_action']['input'] == 5
    assert stages['final_action']['kept'] == 5
    assert stages['split']['output'] == 4
    assert stages['stay']['input_bills'] == 4
    assert stages['stay']['output_stays'] == 3
    assert stages['intermediate']['output'] == 3
    assert stages['final_medpar']['output'] == 3
    for name in ('final_action','split','stay','intermediate','final_medpar'):
        assert (tmp_path / name / 'output.json').is_file()
        assert (tmp_path / name / 'audit.json').is_file()
    stays = json.loads((tmp_path / 'stay/output.json').read_text())
    h2 = next(x for x in stays if x['hicn'] == 'H2')
    assert h2['bill_count'] == 2
    assert h2['diagnosis_codes'] == ['D2']
    assert h2['total_charges'] == '201.00'
    assert (tmp_path / 'audit_summary.json').is_file()


def test_reject_invalid_transaction(tmp_path):
    records = load_claims(ROOT / 'data/demo_v3/demo_claims.json')
    records[0]['transaction_code'] = '9'
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps(records))
    with pytest.raises(ValueError, match='transaction code'):
        load_claims(path)


def test_split_inpatient_last_thru_and_snf_admit():
    base = {'hicn':'H','provider_id':'P','admission_date':'2023-12-30','claim_can':'999595','processing_date':'2024-02-01','accrete_date':'2024-02-01'}
    inpatient = [dict(base, claim_id='1', transaction_code='3', stay_thru_date='2023-12-31'), dict(base, claim_id='2', transaction_code='3', stay_thru_date='2024-01-02', processing_date='2024-02-02')]
    snf = [dict(base, claim_id='3', transaction_code='4', stay_thru_date='2024-01-02')]
    output, audit = split_claims(inpatient+snf, 2024)
    assert [r['split_bucket'] for r in output if r['split_type']=='INP'] == ['Y0Q0109']*2
    assert [r['split_bucket'] for r in output if r['split_type']=='SNF'] == ['Y1Q1012']
    assert all(r['sample_1pct'] for r in output)


def test_inpatient_without_discharge_excluded_snf_allowed():
    inp={'claim_id':'A','split_type':'INP'}
    snf={'claim_id':'B','split_type':'SNF'}
    output, audit=final_medpar([inp,snf])
    assert output == [snf]
    assert audit['excluded_undischarged_inpatient'] == ['A']


def test_split_excess_bills_quarantined():
    records = [{'claim_id':str(i),'hicn':'H','provider_id':'P','admission_date':'2024-01-01','processing_date':'2024-02-01','stay_thru_date':'2024-01-02','transaction_code':'3'} for i in range(76)]
    output,audit=split_claims(records,2024)
    assert output == []
    assert len(audit['exceptions']) == 1
