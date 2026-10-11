"""Stay field checks for non-conflicting MM-Stay-10..21 requirements."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import SourceRecord, RuleResult
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.decimal_values import quantize_decimal, to_decimal
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.intermediate.business_rules import codes


FIRST_FIELDS = (
    "state_code", "county_code", "fiscal_intermediary", "beneficiary_zip_code",
    "beneficiary_gender", "beneficiary_race", "beneficiary_date_of_birth", "medicare_status",
    "patient_surname", "patient_first_initial", "patientMiddleInitial", "claim_can", "hicn", "bic",
    "action_code", "provider_id", "providerStateCode", "medicaidProvider", "medicaidInformation",
    "medical_record", "proMedicalNumber", "admission_date", "patientControl", "nchNearLineRIC",
    "rictypeCode", "pro_approval", "daysPrPsychology", "kronIndicator", "host_site",
    "primaryPaymentCode", "internal_control_number_origin", "cancel_only_adjustment_code",
    "nchStateSegment", "transaction_code", "hmoPaidIndicator", "treatmentAuth",
    "patchTrailerData", "demonstrationLine",
)
LAST_FIELDS = ("bundled_m1_percent", "vbp_adjustment_percent", "hrr_adjustment_percent",
               "diagnosisLines", "diagnosisELines", "procedureLines", "diagnosis_codes", "procedure_codes")
FIRST_FOUND_FIELDS = (
    "query_code", "internalControlNumber", "dischargeDestination", "admissionType",
    "admissionSource", "keptOutCode", "nchNearLineRIC.version", "admissionDiagnosisCode.code",
    "diagnosisRelatedGroup.id", "patientRelationship", "careImprovementModel1", "careImprovementModel2",
    "careImprovementModel3", "careImprovementModel4", "vbpParticipantIndicator",
    "hrrParticipantIndicator", "hacReductionIndicatorSwitch", "ehrReductionIndicatorSwitch",
    "priorAuthorizationIndicator", "uniqueTrackingNumber", "ngAcoIndicatorCodes",
    "residualPaymentIndicatorCode", "rpIndicator", "initialMedicareSeverityDrgCode", "acoId",
    "mbiId", "beneIdTypeCode",
)
HIGH_DATES = ("stay_thru_date", "processing_date", "accrete_date", "forwarded_date", "hcfa_received",
              "mqaDate", "approvedDate", "proProcessDate", "qualifiedStayThruDate", "nonCoverageThruDate",
              "outPatientPhysicalTherapyDate", "activeCareEndsDate", "benefits_exhausted_date")
LOW_DATES = ("stay_from_date", "qualifiedStayFromDate", "nonCoverageFromDate")
SUM_FIELDS = (
    "baseOperatingDrgAmount", "operatingHspAmount", "uncompensatedCarePayment",
    "bundledAdjustmentPayment", "vbpAdjustmentPayment", "hrrAdjustmentPayment", "ehrAdjustmentPayment",
    "ppsStandardValuePayment", "finalStandardAmount", "ppsHacPayment", "ppsFlexiblePayment7",
    "modelReimbursmentAmount", "ltchDischargePercentAmount", "siteNtrlCostAmount", "siteNtrlIppsAmount",
    "fullStandardAmount", "ssoStandardAmount", "reimbursement_amount", "primary_payment_amount",
    "totalCharges", "inPatientDeduction", "coinsuranceAmount", "bloodDeductable", "capitalTotal",
    "utilization_days", "daysCoinsurance", "daysLRTotal", "pintsFurnished", "outlierAmount",
    # lowVolumePaymentAmount also appears in first-bill rules: excluded pending resolution.
)


def _validate_merge_rules(records: list[SourceRecord], actual: SourceRecord | None,
                         resolver: FieldResolver, scale: Decimal) -> list[RuleResult]:
    """Order bills and independently derive supported first/last/nonblank/date/sum/revenue/warning
    expectations; retain per-field source lineage.
    """
    results = []
    def get(r: SourceRecord, field: str) -> Any:
        """Read the resolved field from the supplied record. Alias resolution and missing-value
        handling follow the code below.
        """
        return resolver.get(r.data, field)
    ordered = sorted(records, key=lambda r: (parse_date(get(r,"stay_from_date")), parse_date(get(r,"stay_thru_date")),
        -(parse_date(get(r,"processing_date"), allow_none=True).toordinal() if get(r,"processing_date") else 0),
        -(parse_date(get(r,"accrete_date"), allow_none=True).toordinal() if get(r,"accrete_date") else 0),
        -int(get(r,"query_code") or 0), str(get(r,"icn") or "")))
    first, last = ordered[0], ordered[-1]

    def check(field: str, expected: Any, rule: str, numeric: bool = False) -> None:
        """Compare the local independently calculated expectation with the target field and append
        a traced rule outcome. Missing operands/output and invalid values use the explicit
        status branches below.
        """
        observed = get(actual, field) if actual else None
        if observed is None:
            status = ValidationStatus.NOT_APPLICABLE
        else:
            try:
                if field == "beneficiary_date_of_birth" or field.endswith("_date") or field in HIGH_DATES or field in LOW_DATES:
                    left, right = parse_date(expected), parse_date(observed)
                else:
                    left, right = (quantize_decimal(expected, scale=scale), quantize_decimal(observed, scale=scale)) if numeric else (expected, observed)
                status = ValidationStatus.PASS if left == right else ValidationStatus.FAIL
            except (TypeError, ValueError):
                status = ValidationStatus.FAIL
        results.append(RuleResult(stage=Stage.STAY, rule_id=rule, status=status,
            message="Stay merge rule matches" if status == ValidationStatus.PASS else "Calculated Stay expectation; output absent" if observed is None else "Stay merge mismatch",
            field_name=field, expected=str(expected) if isinstance(expected, Decimal) else expected, actual=observed,
            record_ids=[r.record_id for r in records], source_files=sorted({r.source.file_path for r in records}),
            evidence={"first_bill": first.record_id, "last_bill": last.record_id, "specification": "MM-Stay-10..21", "comparison": "calendar_date" if field == "beneficiary_date_of_birth" or field.endswith("_date") or field in HIGH_DATES or field in LOW_DATES else "value"}))
    for fields, record, rule in ((FIRST_FIELDS, first, "ST-FIRST-BILL"), (LAST_FIELDS,last,"ST-LAST-BILL")):
        for field in fields:
            value = get(record,field)
            if value is not None:
                check(field,value,rule)
    for field in FIRST_FOUND_FIELDS:
        value = next((get(r, field) for r in ordered if get(r, field) is not None
                      and str(get(r, field)).strip()), None)
        if value is not None:
            check(field, value, "ST-FIRST-NONBLANK")
    for fields, choose, rule in ((HIGH_DATES,max,"ST-HIGH-DATE"), (LOW_DATES,min,"ST-LOW-DATE")):
        for field in fields:
            values = [parse_date(get(r,field)) for r in records if get(r,field) not in (None,"")]
            if values:
                expected = choose(values)
                observed = get(actual, field) if actual else None
                if observed is not None:
                    try:
                        observed = parse_date(observed)
                    except ValueError:
                        pass
                check(field, expected, rule)
                if results[-1].status != ValidationStatus.NOT_APPLICABLE:
                    results[-1].status = ValidationStatus.PASS if observed == expected else ValidationStatus.FAIL
                results[-1].expected = expected.isoformat()
    for field in SUM_FIELDS:
        values = [get(r,field) for r in records]
        if any(v is not None for v in values):
            if any(v is None for v in values):
                results.append(RuleResult(stage=Stage.STAY,rule_id="ST-SUM-MISSING-OPERAND",status=ValidationStatus.BLOCKED,
                    message=f"Cannot sum {field}: absent on one or more source bills",field_name=field,record_ids=[r.record_id for r in records]))
            else:
                check(field, sum(map(to_decimal,values),Decimal(0)),"ST-SUM-FIELD", True)
    revenue = [item for r in ordered for item in (get(r,"revenue_lines") or [])]
    if revenue:
        check("revenue_lines",revenue,"ST-ALL-REVENUE-LINES")
    qcs = {str(get(r,"query_code")) for r in records}
    check("warning_indicator_01",str((1 if "0" in qcs else 0)+(2 if "5" in qcs else 0)),"ST-WARNING-01", True)
    snf = str(get(first,"transaction_code")) in {"0","4"}
    discharge = get(last,"discharge_status") or get(last,"patientStatus")
    check("warning_indicator_05", "0" if len(records)==1 else "2" if snf and str(discharge)=="30" else "1", "ST-WARNING-05", True)
    from .warnings import warning06, warning08
    for number, calculation in ((6, warning06), (8, warning08)):
        field = f"warning_indicator_{number:02}"
        try:
            check(field, calculation(records, resolver), f"ST-WARNING-{number:02}", True)
        except LookupError as exc:
            observed = get(actual, field) if actual else None
            results.append(RuleResult(stage=Stage.STAY, rule_id=f"ST-WARNING-{number:02}",
                status=ValidationStatus.BLOCKED if observed is not None else ValidationStatus.NOT_APPLICABLE,
                message=str(exc), expected="Complete source operands for V3 p24", actual=observed,
                field_name=field, record_ids=[r.record_id for r in records]))
    return results


def validate_merge_rules(records, actual, resolver, scale):
    """Wrap merge derivation and convert invalid numeric/date operands into a reportable failure."""
    try:
        return _validate_merge_rules(records,actual,resolver,scale)
    except (ValueError,TypeError,ArithmeticError) as exc:
        return [RuleResult(stage=Stage.STAY,rule_id="ST-MERGE-OPERANDS",status=ValidationStatus.FAIL,
            message=str(exc),record_ids=[r.record_id for r in records])]
