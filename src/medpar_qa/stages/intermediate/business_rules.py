"""Independent expected-value checks from V3 pp26–34 and byte-by-byte pp4–6.

Source and output are separate: output values never supply calculation operands.
Missing operands block a populated target instead of silently validating it.
Absent targets expose calculated expectations as NOT_APPLICABLE, never PASS.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.decimal_values import to_decimal
from medpar_qa.normalization.fields import FieldResolver, nested_get
from medpar_qa.stages.common import normalize_collection


def whole_dollars(value: Any) -> Decimal:
    """Whole dollars, ties away from zero (including negative credits)."""
    # LD-1410's supplied COBOL notes cap positive dollar outputs at nine digits.
    return min(Decimal("999999999"), to_decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def length_of_stay(admission: date, thru: date, discharge_status: Any) -> int:
    """Derive stay length from admission/thru and discharge status, including same-day behavior;
    reject inverted dates.
    """
    days = (thru - admission).days
    if days < 0:
        raise ValueError("Thru date precedes admission/from date")
    return max(1, days + (str(discharge_status).strip() in {"30", "C"}))


def death_after_admission(admission: date, death: date | None) -> int | None:
    """Return the signed death-day distance from admission, using one for same-day death.
    A missing death date returns None; this arithmetic helper does not reject negative days.
    """
    return None if death is None else (1 if death == admission else (death - admission).days)


def age_at_admission(birth: date, admission: date, medicare_status: Any) -> int:
    """Compute age using the birthday boundary and the documented Medicare-status adjustment; never
    replace a missing DOB with an invented date.
    """
    if birth > admission:
        raise ValueError("Birth date is after admission")
    age = admission.year - birth.year - ((admission.month, admission.day) < (birth.month, birth.day))
    return 65 if age == 64 and str(medicare_status).strip() in {"10", "11"} else age


def base_facility_ccn(provider: Any) -> str:
    """Derive base facility CCN using the documented provider-position mapping."""
    text = str(provider).strip().upper()
    if len(text) != 6:
        raise ValueError("Provider CCN must contain six characters")
    third, fourth = text[2:4]
    if fourth.isdigit():
        replace = {"M":"1","R":"1","Z":"1","S":"0","T":"0","U":"0","W":"2","Y":"3"}
        return text[:2]+replace.get(third,third)+text[3:]
    pairs = {"TA":"20","SA":"20","TB":"21","SB":"21","TC":"22","SC":"22",
             "SD":"30","TE":"33","SE":"33","TF":"40","TG":"41","TH":"42","TJ":"43","TK":"44"}
    return text[:2]+pairs[text[2:4]]+text[4:] if text[2:4] in pairs else ""


def accommodation_totals(lines: Any) -> tuple[list[int], list[Decimal]]:
    """V3 p34's five groups: private, semi-private, ward, ICU, CCU."""
    days = [0]*5
    charges = [Decimal(0) for _ in range(5)]
    for line in normalize_collection(lines):
        code = str(line_value(line,"code","revenueCode","revCntrCd","REV-CNTR-CD","revenueCenter.revenueCenterId")).zfill(4)
        if not code.isdigit():
            raise ValueError("Invalid accommodation revenue code")
        number=int(code)
        family=number//10
        group=0 if family in {11,14} or 9033<=number<=9044 else 1 if family in {10,12,13,16,17,18,19} or 9019<=number<=9032 else 2 if family==15 or 9000<=number<=9018 else 3 if family==20 else 4 if family==21 else None
        if group is None:
            continue
        units=line_value(line,"units","unitCount","revCntrUnitCnt","REV-CNTR-UNIT-CNT")
        charge=line_value(line,"charges","amount","totalCharge","charge","revCntrTotChrgAmt","REV-CNTR-TOT-CHRG-AMT","totalAmount")
        if units is None or charge is None:
            raise LookupError("Accommodation line requires units and total charge")
        unit_decimal=to_decimal(units)
        if unit_decimal < 0 or unit_decimal != unit_decimal.to_integral_value():
            raise ValueError("Accommodation days must be non-negative integers")
        days[group]+=int(unit_decimal)
        charges[group]+=to_decimal(charge).quantize(Decimal("0.001"),rounding=ROUND_HALF_UP)
    return days,[whole_dollars(amount) for amount in charges]


def line_value(line: Any, *keys: str) -> Any:
    """Resolve alternate nested revenue/value/span keys and identifier wrappers from one line
    object.
    """
    if not isinstance(line, dict):
        return line if "code" in keys else None
    for key in keys:
        value = nested_get(line, key)
        if value is not None:
            if isinstance(value, dict):
                for identifier in ("revenueCenterId", "conditionCodeId", "occurrenceSpanCodeId", "valueCodeId"):
                    code = nested_get(value, identifier)
                    if code is not None:
                        return code
                continue
            return value
    # Production extract code groups wrap the code in an identifier object.
    if "code" in keys:
        for path in ("revenueCenter.revenueCenterId", "conditionCodeId",
                     "occurrenceSpanCode.occurrenceSpanCodeId", "occurrenceSpanCodeId"):
            value = nested_get(line, path)
            if value is not None:
                return value
    return None


def codes(lines: Any, *keys: str) -> list[str]:
    """Extract trimmed uppercase nonblank codes from the normalized repeated source collection."""
    return [str(value).strip().upper() for line in normalize_collection(lines)
            if (value := line_value(line, "code", *keys)) is not None and str(value).strip()]


def care_unit_indicator(lines: Any, family: str) -> str:
    """CMS CR14 pp54–55,137,139 and supplied LD-1514 charge selection.

    A tied maximum needs the current MPRPARL tie rule; never choose arbitrarily.
    """
    allowed = {"020": "012346789", "021": "01234"}[family]
    totals: dict[str, Decimal] = {}
    for line in normalize_collection(lines):
        raw = line_value(line, "code", "revenueCode", "revCntrCd", "REV-CNTR-CD")
        code = str(raw).strip().zfill(4)
        if not code.startswith(family):
            continue
        if len(code) != 4 or code[-1] not in allowed:
            raise LookupError(f"Unmapped {family} care-unit revenue code")
        amount = line_value(line, "charges", "amount", "totalCharge", "charge",
                            "revCntrTotChrgAmt", "REV-CNTR-TOT-CHRG-AMT", "totalAmount")
        if amount is None:
            raise LookupError("Care-unit derivation requires revenue total charge")
        totals[code] = totals.get(code, Decimal(0)) + to_decimal(amount)
    if not totals:
        return ""
    maximum = max(totals.values())
    winners = [code for code, amount in totals.items() if amount == maximum]
    if len(winners) != 1:
        raise LookupError("Care-unit charge tie requires approved MPRPARL tie policy")
    return winners[0][-1]


def outpatient_services_indicator(revenue_codes: list[str]) -> str:
    # CMS CR14 p139: outpatient=1, ambulatory surgery=2, both=3, neither=0.
    """Return 0=neither, 1=050X outpatient, 2=049X ambulatory surgery or 3=both."""
    outpatient = any("0500" <= code <= "0509" for code in revenue_codes)
    ambulatory = any("0490" <= code <= "0499" for code in revenue_codes)
    return str(int(outpatient) + 2 * int(ambulatory))


def ndc_values_from_revenue(lines: Any) -> list[str]:
    """CMS CR18 p125: first ten 11-character NDC occurrences in revenue order."""
    values = []
    for line in normalize_collection(lines):
        value = line_value(line, "REV_CNTR_IDE_NDC_UPC_NUM", "revCntrIdeNdcUpcNum",
                           "ndcNumber", "investigationalDeviceExemption")
        if value is None or not str(value).strip():
            continue
        text = str(value).strip()
        if len(text) != 11:
            raise LookupError("Shared IDE/NDC/UPC source value does not have the CMS 11-character width")
        # Preserve the raw CHAR value for source-copy verification. Numeric
        # validity is an independent INT-NDC check, so a faithfully copied bad
        # source code never makes the whole stage pass.
        values.append(text)
        if len(values) == 10:
            break
    return values


ORGAN_TYPES = {"0810": "K1", "0811": "K2", "0812": "K3", "0813": "K4",
               "0814": "K5", "0815": "H1", "0816": "H2", "0817": "L1", "0819": "01"}
VALUE_FIELDS = {"18": "medpar_disproportionate_0360", "19": "medpar_ime_amount_0370",
                "77": "medpar_new_tech_add_on_amt_0860", "73": "medpar_sqstrtn_rdctn_amt_1130",
                "Q7": "medpar_islet_addon_pmt_amt_1450", "Q1": "medpar_val_q1_pmt_rdctn_amt_1470",
                "QB": "medpar_val_qb_pmt_adj_amt_1500"}
MONEY_MOVES={"ppsFlexiblePayment7":"medpar_ipps_flex7_amt_1220","baseOperatingDrgAmount":"medpar_base_oprtg_drg_amt_0870",
             "operatingHspAmount":"medpar_oprtg_hsp_amt_0880",
             "uncompensatedCarePayment":"medpar_uncmp_care_pmt_amt_1140",
             "bundledAdjustmentPayment":"medpar_bndld_adjstmt_amt_1150",
             "vbpAdjustmentPayment":"medpar_vbp_adjstmt_amt_1160",
             "hrrAdjustmentPayment":"medpar_hrr_adjstmt_amt_1170",
             "ehrAdjustmentPayment":"medpar_ehr_adjstmt_amt_1180",
             "ppsStandardValuePayment":"medpar_pps_std_val_amt_1190",
             "finalStandardAmount":"medpar_finl_std_amt_1200",
             "ppsHacPayment":"medpar_hac_rdctn_pmt_amt_1210",
             "modelReimbursmentAmount":"medpar_clm_modl_reimb_amt_1480",
             "ltchDischargePercentAmount":"medpar_ltch_dpp_adj_amt_1540",
             "siteNtrlCostAmount":"medpar_s_ntrl_pmt_cst_amt_1290",
             "siteNtrlIppsAmount":"medpar_s_ntrl_pmt_ipps_am_1300",
             "fullStandardAmount":"medpar_full_std_pmt_amt_1310",
             "ssoStandardAmount":"medpar_sso_std_pmt_amt_1320",
             "reimbursement_amount":"medpar_amt_reimb_0420",
             "primary_payment_amount":"medpar_primary_amount_0340",
             "totalCharges":"medpar_tot_chrg_0400", "inPatientDeduction":"medpar_inpat_ded_0320",
             "coinsuranceAmount":"medpar_coin_amt_0310", "bloodDeductable":"medpar_blood_ded_0330",
             "capitalTotal":"medpar_capital_acc92_0382", "outlierAmount":"medpar_outlier_amount_0350",
             "lowVolumePaymentAmount":"medpar_ip_low_vol_pmt_amt_0386"}

# Recovered CMS sprint demonstrations LD-1407/1408 provide these JSON mappings.
DIRECT_MOVES = {
    "beneficiary_gender": "medpar_sex_0040", "medicare_status": "medpar_mscode_0060",
    "county_code": "medpar_bene_coun_0072", "hmoPaidIndicator": "medpar_hmo_readm_0110",
    "bill_count": "medpar_no_bills_0150", "utilization_days": "medpar_cov_days_0280",
    "daysCoinsurance": "medpar_coin_days_0290", "daysLRTotal": "medpar_life_res_0300",
    "provider_id": "medpar_prvdr_full_num_1660", "primaryPaymentCode": "medpar_primry_pyr_0540",
    "pintsFurnished": "medpar_blood_pints_0520", "dischargeDestination": "med_disch_dest_0532",
    "outlierCode": "med_outlier_code_0533", "admissionSource": "medpar_adm_source_0560",
    "admissionType": "medpar_type_admis_0570", "fiscal_intermediary": "medpar_intmd_num_0580",
    "attendingPhysicianNpi": "medpar_at_phys_0650", "operatingPhysicianNpi": "medpar_op_phys_0660",
    "pricerVersion": "medpar_clm_prcr_vrsn_1600", "grouperVersion": "medpar_clm_drg_grpr_vrsn_1610",
    "patientRelationship": "medpar_clm_pnt_rltnshp_cd_0700",
    "careImprovementModel1": "medpar_car_imprv_mod_1_cd_0710",
    "careImprovementModel2": "medpar_car_imprv_mod_2_cd_0720",
    "careImprovementModel3": "medpar_car_imprv_mod_3_cd_0730",
    "careImprovementModel4": "medpar_car_imprv_mod_4_cd_0740",
    "vbpParticipantIndicator": "medpar_vbp_prtcpnt_ind_cd_0750",
    "hrrParticipantIndicator": "medpar_hrr_prtcpnt_ind_cd_0760",
    "bundledM1Percent": "medpar_bndld_mod_dsct_pct_0770",
    "vbpAdjustmentPercent": "medpar_vbp_adjstmt_pct_0780",
    "hrrAdjustmentPercent": "medpar_hrr_adjstmt_pct_0790",
    "hacReductionIndicatorSwitch": "medpar_hac_pgm_rdctn_ind_1240",
    "ehrReductionIndicatorSwitch": "medpar_ehr_pgm_rdctn_ind_1250",
    "priorAuthorizationInd": "medpar_prior_authrztn_ind_1260",
    "uniqueTrackingNumber": "medpar_uniq_trkng_num_1270",
    "residualPaymentIndicatorCode": "medpar_rsdl_pmt_ind_cd_1380",
    "rpIndicator": "medpar_clm_rp_ind_cd_1390",
    "acoId": "medpar_aco_id_num_1410",
    "mbiId": "medpar_mbi_id_1420",
    "beneIdTypeCode": "medpar_clm_bene_id_typ_cd_1430",
    "initialMedicareSeverityDrgCode": "medpar_ip_initl_ms_drg_cd_1460",
}


def validate_business_rules(source: SourceRecord, target: SourceRecord,
                            resolver: FieldResolver, *, revenue_category_ranges=None, calculation_sink=None) -> list[RuleResult]:
    """Calculate supported Intermediate expectations from source operands and compare them with the
    matched target, emitting field-specific evidence.
    """
    results: list[RuleResult] = []

    def get(field: str, *alternates: str) -> Any:
        """Read the source-only operand using the first populated alternate name. Alias resolution
        and missing-value handling follow the code below.
        """
        for name in (field, *alternates):
            value = resolver.get(source.data, name)
            if value is not None and value != "":
                return value
        return None

    def required(field: str, *alternates: str) -> Any:
        """Read a mandatory resolved source operand; raise instead of substituting an output value
        when it is missing.
        """
        value = get(field, *alternates)
        if value is None:
            raise LookupError(f"Missing source operand: {field}")
        return value

    def required_date(field: str, *alternates: str) -> date:
        """Read a required source date, reject blank/zero operands and parse it before any
        calculation.
        """
        from medpar_qa.normalization.dates import is_missing_date
        value = required(field, *alternates)
        if is_missing_date(value):
            raise LookupError(f"Missing source date operand: {field}")
        return parse_date(value, allow_none=False)

    def check(rule: str, field: str, calculate: Callable[[], Any], numeric: bool = False, *, date_value: bool = False) -> None:
        """Compare the local independently calculated expectation with the target field and append
        a traced rule outcome. Missing operands/output and invalid values use the explicit
        status branches below.
        """
        observed = resolver.get(target.data, field)
        calculated=False
        try:
            expected = calculate()
            calculated=True
            if calculation_sink is not None:
                calculation_sink(field, expected, None)
                return
            if observed in (None, ""):
                status = ValidationStatus.PASS if expected is None else ValidationStatus.NOT_APPLICABLE
            else:
                comparable = parse_date(observed) if date_value else to_decimal(observed) if numeric else str(observed).strip()
                expected_value = parse_date(expected) if date_value else to_decimal(expected) if numeric and expected is not None else (str(expected).strip() if expected is not None else None)
                status = ValidationStatus.PASS if comparable == expected_value else ValidationStatus.FAIL
            message = "Derived value matches" if status == ValidationStatus.PASS else "Calculated expectation; output field absent" if status == ValidationStatus.NOT_APPLICABLE else "Derived value mismatch"
        except LookupError as exc:
            calculated=False
            expected, status, message = str(exc), ValidationStatus.BLOCKED if observed not in (None, "") else ValidationStatus.NOT_APPLICABLE, str(exc)
        except (ValueError, TypeError, ArithmeticError) as exc:
            calculated=False
            expected, status, message = "Valid source operands", ValidationStatus.FAIL, str(exc)
        if calculation_sink is not None:
            calculation_sink(field, None, message)
            return
        results.append(RuleResult(stage=Stage.INTERMEDIATE, rule_id=rule, field_name=field,
                                  status=status, message=message, expected=str(expected) if isinstance(expected, Decimal) else expected,
                                  actual=observed, record_ids=list(dict.fromkeys([source.record_id, target.record_id])),
                                  source_files=list(dict.fromkeys([source.source.file_path, target.source.file_path])),
                                  evidence={"source_record_id": source.record_id, "target_record_id": target.record_id,
                                            "calculation_completed": calculated,
                                            "specification": "V3 pp26–34; Byte-by-Byte pp4–6"}))

    def admission() -> date:
        """Read source admission date with the documented stay-from fallback."""
        return parse_date(get("admission_date") or required("stay_from_date"), allow_none=False)

    def thru() -> date:
        """Read the required source stay-thru date."""
        return parse_date(required("stay_thru_date"), allow_none=False)

    def status() -> Any:
        """Read source discharge status using the supported aliases."""
        return required("discharge_status", "patient_discharge_status", "patientStatus")

    check("INT-LOS-CALCULATION", "medpar_lgth_stay_0260", lambda: length_of_stay(admission(), thru(), status()), True)
    check("INT-AGE-CALCULATION", "medpar_age_0030", lambda: age_at_admission(required_date("beneficiary_date_of_birth", "date_of_birth", "birthDate", "beneficiaryBirthDate"), admission(), get("medicare_status")), True)
    check("INT-DISCHARGE-STATUS-CALCULATION", "medpar_dischg_status_0100", lambda: "B" if str(status()).strip() in {"20","B"} else "C" if str(status()).strip() in {"30","C"} else "A")

    # DOD lookup requires the external EDB match. This explicitly provided source
    # field is the matched DOD, not the derived output DOD.
    def dod() -> date | None:
        """Use the actual DOD lookup/source date or dead-status thru-date fallback; distinguish a
        confirmed no-match from an unavailable feed.
        """
        from medpar_qa.normalization.dates import is_missing_date
        death = get("matched_date_of_death") if get("dod_reference_available") else get("date_of_death")
        if not is_missing_date(death):
            return parse_date(death, allow_none=False)
        if str(status()).strip() in {"20","B"}:
            return thru()
        if get("dod_reference_available"):
            return None
        raise LookupError("DOD requires EDB reference; an absent source date is not a confirmed no-match")

    check("INT-DEATH-DAYS-CALCULATION", "medpar_death_after_adm_0611", lambda: death_after_admission(admission(), dod()), True)
    check("INT-DOD-CALCULATION", "medpar_himaster_dod_0230", lambda: dod().strftime("%Y%j") if dod() else None, date_value=True)
    def death_verify() -> Any:
        """Use the matched DOD verification switch, dead-status fallback B, or confirmed absent
        match; missing lookup evidence blocks the calculation.
        """
        if get("dod_reference_matched"):
            return required("matched_dod_verify_switch")
        if str(status()).strip() in {"20","B"}:
            return "B"
        if get("dod_reference_available"):
            return None
        raise LookupError("DOD verify requires matched EDB reference or dead-status fallback")
    check("INT-DOD-VERIFY", "medpar_dod_ind_0240", death_verify)
    from medpar_qa.reference_data import ssi_days
    def ssi_count() -> int:
        """Require an available SSI reference and inpatient stay before calculating monthly-overlap
        days.
        """
        if not get("ssi_reference_available"):
            raise LookupError("SSI reference feed not supplied")
        if str(required("transaction_code")) in {"0","4"}:
            raise LookupError("SSI calculation applies to inpatient stays only")
        return ssi_days(admission(),thru(),get("ssi_month_flags") or {})
    check("INT-SSI-DAYS", "medpar_ssi_data_0251", ssi_count, True)
    def ssi_match():
        if not get("ssi_reference_available"):
            raise LookupError("SSI reference feed not supplied")
        return required("ssi_reference_matched")
    check("INT-SSI-MATCH-INDICATOR", "medpar_ssi_data_0252", lambda: "Y" if ssi_match() else "N")
    # Byte-by-Byte p5: duplicate SSNs merge monthly flags; any positive flag => 1.
    check("INT-SSI-ELIGIBILITY-INDICATOR", "medpar_ssi_data_0253",
          lambda: "1" if ssi_match() and any(to_decimal(v) > 0 for v in (get("ssi_month_flags") or {}).values()) else "0")
    def revenue_codes() -> list[str]:
        """Read the required source revenue-line codes and normalize them to four characters."""
        return [code.zfill(4) for code in codes(required("revenue_lines"), "revenueCode", "revCntrCd", "REV-CNTR-CD")]
    ndc_observed = resolver.get(target.data, "medpar_rev_cntr_ndc_num_1550")
    try:
        ndc_expected = ndc_values_from_revenue(required("revenue_lines"))
        ndc_actual = [str(value).strip() for value in normalize_collection(ndc_observed)]
        ndc_status = ValidationStatus.NOT_APPLICABLE if ndc_observed is None else ValidationStatus.PASS if ndc_actual == ndc_expected else ValidationStatus.FAIL
        ndc_message = "First ten NDC occurrences match source revenue order"
    except LookupError as exc:
        ndc_expected, ndc_message = str(exc), str(exc)
        ndc_actual = ndc_observed
        ndc_status = ValidationStatus.NOT_APPLICABLE if ndc_observed is None else ValidationStatus.BLOCKED
    results.append(RuleResult(stage=Stage.INTERMEDIATE, rule_id="INT-NDC-SOURCE-DERIVATION",
                              status=ndc_status, field_name="medpar_rev_cntr_ndc_num_1550",
                              message=ndc_message, expected=ndc_expected, actual=ndc_actual,
                              record_ids=[source.record_id, target.record_id],
                              evidence={"specification": "CMS MedPAR CR18 p125, field241"}))
    def organ_type() -> str:
        """Choose the highest valid organ-acquisition code from the explicit mapping; no valid code
        returns blank.
        """
        matched=set(revenue_codes()) & ORGAN_TYPES.keys()
        if not matched:
            return ""  # CMS CR14 p140: no organ acquisition is blank.
        return ORGAN_TYPES[max(matched)]
    check("INT-ORGAN-TYPE-CALCULATION", "medpar_organ_ind_0487", organ_type)
    check("INT-OUTPATIENT-SERVICES", "medpar_outpatient_srv_ind_0486", lambda: outpatient_services_indicator(revenue_codes()))
    check("INT-INTENSIVE-CARE-IND-0481", "medpar_intensive_care_ind_0481", lambda: care_unit_indicator(required("revenue_lines"), "020"))
    check("INT-CORONARY-CARE-IND-0482", "medpar_coronary_care_ind_0482", lambda: care_unit_indicator(required("revenue_lines"), "021"))
    check("INT-RADIOLOGY-INDICATORS", "medpar_radiology_ind_0485", lambda: "".join("1" if any(lo <= int(c) <= hi for c in revenue_codes()) else "0" for lo, hi in ((280,289),(320,329),(330,339),(340,349),(350,359),(400,409))))
    def condition_codes() -> list[str]:
        """Read condition codes from the required source condition collection."""
        return codes(required("condition_codes"), "conditionCode", "CLM-RLT-COND-CD")
    check("INT-ESRD-CONDITION", "medpar_esrd_condition_0550", lambda: max((c for c in condition_codes() if c in {str(n) for n in range(71,77)}), default="00"), True)
    check("INT-PPS-CALCULATION", "medpar_pps_ind_0120", lambda: "2" if "65" not in condition_codes() and str(required("provider_id"))[2:3].isdigit() else "0")
    check("INT-BASE-FACILITY-CCN", "medpar_prvdr_base_fac_ccn_1650", lambda:base_facility_ccn(required("provider_id")))
    for field, index in (("medpar_accommodation_days_0450",0),("medpar_accommodation_chrg_0460",1)):
        observed=resolver.get(target.data,field)
        try:
            expected=accommodation_totals(required("revenue_lines"))[index]
            actual_values=[to_decimal(v) for v in observed] if isinstance(observed,list) else None
            result_status=ValidationStatus.NOT_APPLICABLE if observed is None else ValidationStatus.PASS if actual_values==expected else ValidationStatus.FAIL
            message="Five accommodation groups derived from revenue codes"
        except LookupError as exc:
            expected,message=str(exc),str(exc)
            result_status=ValidationStatus.BLOCKED if observed is not None else ValidationStatus.NOT_APPLICABLE
        except (ValueError,TypeError,ArithmeticError) as exc:
            expected,message="Valid accommodation lines",str(exc)
            result_status=ValidationStatus.FAIL
        if calculation_sink is not None:
            calculation_sink(field,[str(v) for v in expected] if isinstance(expected,list) else None,None if isinstance(expected,list) else message)
            continue
        results.append(RuleResult(stage=Stage.INTERMEDIATE,rule_id="INT-ACCOMMODATION-CATEGORIES",status=result_status,
            message=message,field_name=field,expected=[str(v) for v in expected] if isinstance(expected,list) else expected,
            actual=observed,record_ids=[source.record_id,target.record_id]))

    def value_lines() -> list[Any]:
        """Read the required source value-code collection with supported alternate field naming."""
        return normalize_collection(required("value_lines", "clm_val_grp"))
    def value_total(code: str) -> Decimal:
        """Sum all signed amounts for a given source value code before whole-dollar rounding;
        missing line amounts are not guessed.
        """
        amounts = []
        for line in value_lines():
            if str(line_value(line, "code", "valueCode", "CLM-VAL-CD")).strip().upper() == code:
                amount = line_value(line, "amount", "valueAmount", "CLM-VAL-AMT")
                if amount in (None, ""):
                    raise LookupError(f"Missing amount for value code {code}")
                amounts.append(to_decimal(amount))
        return whole_dollars(sum(amounts, Decimal(0)))
    for code, field in VALUE_FIELDS.items():
        check("INT-VALUE-CODE-AMOUNT", field, lambda code=code: value_total(code), True)
    check("INT-DEVICE-CREDIT-SWITCH", "medpar_cr_rcv_repl_dvc_sw_0840", lambda: "Y" if "FD" in codes(value_lines(), "valueCode", "CLM-VAL-CD") else "N")

    def drg_price() -> Decimal:
        """Sum payment, primary payer, coinsurance, inpatient deductible and blood deductible,
        subtract outlier payment, then round to whole dollars.
        """
        operands = [required("claim_payment_amount", "CLM-PMT-AMT", "claimPaymentAmount", "reimbursement_amount"),
                    required("primary_payer_amount", "NCH-PRMRY-PYR-CLM-PD-AMT", "primaryPayerClaimPaidAmount", "primary_payment_amount"),
                    required("coinsurance_amount", "NCH-BENE-PTA-COINSRNC-AMT", "beneficiaryCoinsuranceAmount"),
                    required("inpatient_deductible_amount", "NCH-BENE-IP-DDCTBL-AMT", "inpatientDeductibleAmount", "inPatientDeduction"),
                    required("blood_deductible_amount", "NCH-BENE-BLOOD-DDCTBL-AMT", "bloodDeductibleAmount", "bloodDeductable")]
        outlier = required("outlier_payment_amount", "NCH-DRG-OUTLIER-APRV-PMT-AMT", "outlierApprovedPaymentAmount", "outlierAmount")
        return whole_dollars(sum(map(to_decimal, operands), Decimal(0)) - to_decimal(outlier))
    check("INT-DRG-PRICE-CALCULATION", "medpar_drg_price_0380", drg_price, True)
    def warning10():
        lines=normalize_collection(required("revenue_lines"))
        if any(9000 <= int(line_value(line,"code","revenueCode","revCntrCd")) <= 9044 for line in lines):
            raise LookupError("WI10 RUG date/code mapping requires approved RIF/COBOL reference")
        return "0"
    check("INT-WARNING-10-RUG", "warning_indicator_10", warning10)
    def provider_category():
        provider = str(required("provider_id", "medpar_prvdr_full_num_1660")).strip()
        if len(provider) != 6:
            raise LookupError("Provider derivation requires a six-character provider number")
        third = provider[2].upper()
        special = third if third in "STUWYMR" else ""
        classification = "N" if third in "56UWYZ" else "S" if third in "01STMR" else "L"
        return special, classification
    check("INT-SPECIAL-UNIT-DERIVATION", "medpar_prov_code_0137", lambda: provider_category()[0])
    check("INT-PROVIDER-CLASSIFICATION", "medpar_ss_ls_snf_ind_0140", lambda: provider_category()[1])
    from .revenue_totals import FIELDS, RANGES, revenue_total, sum_line_field, covered_revenue
    def category_total(field, low, high):
        approved=(revenue_category_ranges or {}).get(field)
        if approved:
            return whole_dollars(sum((revenue_total(get("revenue_lines"), int(a), int(b), round_result=False) for a,b in approved), Decimal(0)))
        if field=="medpar_oprtg_room_amt_1100":
            raise LookupError("Operating-room range requires approved MPRPARL/RIF mapping; V3 p33 lists ambiguous 0360-0719")
        return revenue_total(get("revenue_lines"),low,high)
    for field, (low, high) in zip(FIELDS, RANGES):
        check("INT-REVENUE-CATEGORY-TOTAL", field, lambda field=field, low=low, high=high: category_total(field, low, high), True)
    check("INT-DEPARTMENTAL-TOTAL", "medpar_tot_dpt_chrg_0440", lambda: revenue_total(get("revenue_lines"), 0, 9999), True)
    check("INT-COVERED-REVENUE-TOTAL", "medpar_cov_chrg_0410", lambda: covered_revenue(get("revenue_lines"), resolver), True)
    check("INT-PATIENT-ADDON-TOTAL", "medpar_ptnt_add_on_amt_1230", lambda: sum_line_field(get("revenue_lines"), resolver, "rev_cntr_ptnt_add_on_pmt_amt"), True)
    check("INT-REVENUE-MODEL-TOTAL", "medpar_rev_cntr_modl_amt_1490", lambda: sum_line_field(get("revenue_lines"), resolver, "rev_cntr_model_reimbrsmt_amt"), True)
    def revenue_rp():
        lines=normalize_collection(required("revenue_lines"))
        return "R" if any(str(line_value(line,"rpInd","rpIndicator","revCntrRpIndCd")).strip()=="R" for line in lines) else ""
    check("INT-REVENUE-RP-INDICATOR", "medpar_rev_cntr_rp_ind_cd_1400", revenue_rp)

    for input_field, output_field in DIRECT_MOVES.items():
        if get(input_field, output_field) is not None or resolver.get(target.data, output_field) not in (None, ""):
            check("INT-DOCUMENTED-DIRECT-MOVE", output_field, lambda input_field=input_field, output_field=output_field: required(input_field, output_field))
    aco = get("ngAcoIndicatorCodes")
    if aco is not None:
        for index, field in enumerate(("medpar_ng_aco_ind_1_cd_1330", "medpar_ng_aco_ind_2_cd_1340",
                "medpar_ng_aco_ind_3_cd_1350", "medpar_ng_aco_ind_4_cd_1360", "medpar_ng_aco_ind_5_cd_1370")):
            def aco_value(index=index):
                """Return the requested source ACO array position and reject a missing/malformed
                position.
                """
                if not isinstance(aco, list) or len(aco) <= index:
                    raise LookupError(f"Missing ACO indicator at position {index+1}")
                return aco[index]
            check("INT-DOCUMENTED-ACO-MOVE", field, aco_value)
    if get("medicalRecord") is not None or get("patientControl") is not None:
        check("INT-MRN-FALLBACK", "medpar_mrn_0670", lambda: get("medicalRecord")
              if str(get("medicalRecord") or "").strip() else required("patientControl"))
    if get("claim_can") is not None:
        check("INT-FIVE-PERCENT-SAMPLE", "medpar_sample_05_0680",
              lambda: "1" if str(required("claim_can"))[7:9] in {"05","20","45","70","95"} else "0")
    def total_per_diem() -> Decimal:
        """Require nonnegative integer utilization days, round the source per-diem rate to whole
        dollars first, then multiply and round the total.
        """
        days = to_decimal(required("utilization_days"))
        if days < 0 or days != days.to_integral_value():
            raise ValueError("Utilization days must be a non-negative integer")
        # LD-1410 COBOL COMPUTE rounds the rate to whole dollars before multiplication.
        rate = to_decimal(required("pass_thru_per_diem")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return whole_dollars(rate * days)
    check("INT-SOURCE-PERDIEM-CALCULATION", "medpar_bill_tot_perdiem_0381", total_per_diem, True)
    for input_field, output_field in MONEY_MOVES.items():
        if get(input_field) is not None:
            check("INT-MONEY-MOVE-ROUNDING",output_field,lambda input_field=input_field:whole_dollars(required(input_field)),True)
    for input_field, output_field in (("admission_date","medpar_adm_date_0200"),
            ("accrete_date","medpar_accretion_date_0160"), ("benefits_exhausted_date","medpar_date_benfex_0170"),
            ("stay_thru_date","medpar_dischg_date_0210")):
        check("INT-JULIAN-CONVERSION",output_field,lambda input_field=input_field: parse_date(required(input_field),allow_none=False).strftime("%Y%j"),date_value=True)
    def spans() -> list[Any]:
        """Read the source occurrence-span collection needed by span date derivations."""
        return normalize_collection(required("occurrence_span_lines"))
    def span_date(code: str, direction: str, highest: bool = False) -> str | None:
        """Resolve/parse the span dates used by this local consolidation or derivation; code, date
        direction and maximum/first precedence follow the expression below.
        """
        matches=[line for line in spans() if str(line_value(line,"code","spanCode","occurrenceSpanCode")).strip()==code]
        names=("fromDate","from_date","from") if direction=="from" else ("toDate","thruDate","thru_date","thru")
        values=[parse_date(line_value(line,*names),allow_none=False) for line in matches]
        # Stay's span consolidation emits newest-claim groups first.
        return (max(values) if highest else values[0]).strftime("%Y%j") if values else None
    for code, direction, field in (("70","from","medpar_snf_qual_from_date_0180"), ("70","thru","medpar_snf_qual_thru_date_0190"),
            ("82","from","medpar_hosp_home_from_dt_1630"), ("82","thru","medpar_hosp_home_thru_dt_1640")):
        check("INT-SPAN-DATE-DERIVATION",field,lambda code=code,direction=direction:span_date(code,direction),date_value=True)
    check("INT-COVERED-CARE-END", "medpar_dte_cr_ended_0220",lambda:span_date("22","thru",True) if str(required("transaction_code")) in {"0","4"} else None,date_value=True)
    check("INT-TWO-MIDNIGHT", "medpar_2_midnight_stay_ind_1280",lambda:"Y" if "72" in codes(spans(),"spanCode","occurrenceSpanCode") else "N")
    check("INT-WARNING-04-CALCULATION", "warning_indicator_04", lambda: "0" if to_decimal(required("utilization_days")) == length_of_stay(admission(), thru(), status()) else "1" if to_decimal(required("utilization_days")) < length_of_stay(admission(), thru(), status()) else "2")
    check("INT-WARNING-09-CALCULATION", "warning_indicator_09", lambda: "1" if to_decimal(required("pass_thru_per_diem")) != 0 else "0")
    def warning02():
        flag = required("edit_error_present")
        if not isinstance(flag, bool):
            raise LookupError("Warning 02 requires a mapped boolean edit_error_present from the edit-code table")
        return "1" if flag else "0"
    check("INT-WARNING-02-CALCULATION", "warning_indicator_02", warning02)
    def warning03():
        payment = to_decimal(required("medicare_payment_amount", "medicarePaymentAmount", "claimPaymentAmount"))
        charges = to_decimal(required("medpar_tot_chrg_0400", "total_charges"))
        if payment < 0 and charges < 0: return "1"
        if payment < 0: return "2"
        if charges < 0: return "3"
        if payment > 0 and charges > 0: return "0"
        if payment == charges == to_decimal(required("primary_payment_amount")) == to_decimal(required("utilization_days")) == 0: return "4"
        raise LookupError("V3 p32 does not define this mixed zero/nonzero warning 03 case")
    check("INT-WARNING-03-CALCULATION", "warning_indicator_03", warning03)
    def warning07():
        state = required("state_code_valid")
        county = required("county_code_valid")
        if not isinstance(state, bool) or not isinstance(county, bool):
            raise LookupError("Warning 07 needs boolean state/county validation from approved ranges")
        return "0" if state and county else "1" if not state and not county else "2" if not state else "3"
    check("INT-WARNING-07-CALCULATION", "warning_indicator_07", warning07)
    for number in (1, 5, 6, 8):
        check("INT-WARNING-CARRY-FORWARD", f"warning_indicator_{number:02}", lambda number=number: required(f"warning_indicator_{number:02}"))
    for number in range(11,18):
        check("INT-WARNING-ZERO", f"warning_indicator_{number:02}", lambda: "0")
    return results
