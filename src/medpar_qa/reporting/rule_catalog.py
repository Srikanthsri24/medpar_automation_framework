from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleMetadata:
    title: str
    requirement: str
    validation: str
    logic: str
    pass_meaning: str
    fail_meaning: str
    remediation: str


def _meta(
    title: str,
    requirement: str,
    validation: str,
    logic: str,
    remediation: str,
) -> RuleMetadata:
    return RuleMetadata(
        title=title,
        requirement=requirement,
        validation=validation,
        logic=logic,
        pass_meaning="The observed data satisfies the stated business requirement.",
        fail_meaning="The observed data does not satisfy the stated business requirement.",
        remediation=remediation,
    )


CATALOG: dict[str, RuleMetadata] = {
    "INGEST-DISCOVERY": _meta(
        "Input file discovery",
        "Every configured relative file path or wildcard must resolve to at least one input file.",
        "Resolve the configured source, actual, or expected path and count matching files.",
        "PASS when one or more files are found; FAIL when no file matches or discovery raises an error.",
        "Correct the relative path, filename, wildcard, or working project folder.",
    ),
    "INGEST-READ-FILE": _meta(
        "Input file readability",
        "Every discovered JSON or Parquet file must be readable and parse into records.",
        "Open the file, parse its content, normalize the root structure, and count records.",
        "PASS when parsing succeeds; FAIL for malformed JSON, unreadable Parquet, unsupported format, or read errors.",
        "Repair the input file or use a supported JSON/Parquet format.",
    ),
    "INGEST-NO-RECORDS": _meta(
        "Input record availability",
        "A requested stage cannot run without at least one valid input record.",
        "Count records successfully loaded for the stage.",
        "PASS is not possible when zero records are available; the stage must fail clearly.",
        "Supply at least one valid source file and resolve preceding ingestion failures.",
    ),
    "STAGE-FINAL-SUMMARY": _meta(
        "Stage completion summary",
        "A stage passes only when it has no FAIL or BLOCKED validation results.",
        "Count PASS, FAIL, BLOCKED, and NOT_APPLICABLE results emitted by the stage.",
        "PASS when FAIL=0 and BLOCKED=0; otherwise FAIL.",
        "Review the failed or blocked rule cards earlier in the same stage section.",
    ),

    # Final Action
    "FA-PRE-SOURCE-FILES": _meta("Final Action source availability", "Final Action requires source claim records.", "Confirm at least one source-role record was supplied.", "PASS when source count is greater than zero.", "Add a Final Action source file path."),
    "FA-PRE-SCHEMA": _meta("Final Action required-field validation", "Each claim must contain valid identity, provider, dates, transaction code, query code, ICN, and processing data.", "Validate required fields, data types, allowed codes, and date formats for each record.", "PASS only when every mandatory field is present and valid.", "Correct the field shown in the failed card and rerun the same file."),
    "FA-PRE-GROUPING": _meta("Final Action claim grouping", "Claims must be grouped by record type, HICN, provider, stay-from date, and stay-thru date.", "Build the business group key for each valid record.", "PASS when a complete deterministic group key can be created.", "Populate or correct the field that prevented group-key creation."),
    "FA-PRE-ORDERING": _meta("Final Action newest-record ordering", "Rules that use first/latest records require deterministic newest-first ordering.", "Sort by processing date, accrete date, and approved source sequence.", "PASS when records have a unique order; BLOCKED when ties cannot be safely resolved.", "Provide the approved tie-breaker or correct duplicate ordering values."),
    "FA-ALL-QC0": _meta("All QC0 group", "When every claim in a group has query code 0, the complete group is dropped.", "Confirm all query codes are zero and assign DROP to every record.", "PASS when every group record receives DROP.", "Remove any QC0 record incorrectly retained in Final Action output."),
    "FA-RULE-01": _meta("Final Action Rule 1 — single claim", "A one-record group keeps approved non-zero QC values and drops QC0.", "Count the group, inspect query code, and assign KEEP or DROP.", "For the current approved requirements: QC1/QC2/QC3/QC5=KEEP and QC0=DROP.", "Correct query-code handling or the actual retained-output membership."),
    "FA-RULE-02": _meta("Final Action Rule 2 — 5-0-3 / 5-0-1", "A three-record newest-first sequence 5-0-3 or 5-0-1 keeps only QC5.", "Validate group count, newest-first QC sequence, and record decisions.", "PASS when QC5 is KEEP and the other two records are DROP.", "Correct ordering, sequence selection, or retained-output membership."),
    "FA-RULE-03": _meta("Final Action Rule 3 — same QC", "When all records have the same QC, retain only the newest record for each unique ICN.", "Group same-QC claims by ICN and select the newest record per ICN.", "PASS when kept count equals unique ICN count and no older duplicate survives.", "Drop older duplicate ICNs or restore a missing unique ICN."),
    "FA-RULE-05": _meta("Final Action Rule 5", "For the approved three-record/no-QC5/one-QC0 route, compare ICNs and retain the approved newest non-QC0 record.", "Evaluate group size, QC counts, newest-first order, and ICN equality.", "PASS when decisions match the Rule 5 flow; all-same ICNs must drop all.", "Correct ICN comparison or selected non-QC0 record."),
    "FA-RULE-06": _meta("Final Action Rule 6 — QC0/QC5 pair", "For a two-record QC0/QC5 group, matching control numbers plus QC0 transaction/action code 4 or 6 drop both records; otherwise QC5 is kept and QC0 is dropped.", "Compare QueryCode, control number, and the QC0 cancellation code.", "PASS when both are dropped for the matching-control-number 4/6 condition, or when QC5 alone is kept otherwise.", "Correct control-number comparison, cancellation-code mapping, or actual retained-output membership."),
    "FA-RULE-07": _meta("Final Action Rule 7", "With no QC5 and QC0 count dominating, retain eligible unique non-QC0 ICNs and drop QC0/duplicates.", "Compare QC counts and ICN occurrence counts.", "PASS when only eligible unique non-QC0 records remain.", "Correct QC-count routing or duplicate-ICN decisions."),
    "FA-RULE-08": _meta("Final Action Rule 8", "With no QC5, more than three records, newest QC0, and non-QC0 count dominating, retain eligible unique non-QC0 ICNs.", "Validate rule prerequisites and assign decisions using ICN uniqueness.", "PASS when QC0 and duplicate ICNs are dropped.", "Correct newest-record detection, count comparison, or ICN filtering."),
    "FA-RULE-09": _meta("Final Action Rule 9", "With no QC5 and newest non-QC0, keep eligible unique non-QC0 ICNs and drop QC0/duplicates.", "Validate the newest QC and ICN uniqueness after initial selection.", "PASS when final decisions match the Rule 9 override logic.", "Correct newest-record or duplicate-ICN processing."),
    "FA-RULE-10A": _meta("Final Action Rule 10A", "When QC5 exists, newest is QC0, and QC0 count exceeds QC5 count, apply ICN uniqueness to non-QC0 records.", "Check QC5 presence, newest QC, QC counts, and ICN matches.", "PASS when QC0 and matching ICNs are dropped and unique non-QC0 records are retained.", "Correct Rule 10A routing or ICN decisions."),
    "FA-RULE-10B": _meta("Final Action Rule 10B", "When QC5 exists and Rule 10A is false, keep the newest non-QC0 record without ICN comparison.", "Select the first/newest non-QC0 record and drop all remaining records.", "PASS when exactly the approved newest non-QC0 record is kept.", "Correct the selected record or remove unintended ICN comparison."),
    "FA-DEFAULT": _meta("Final Action default rule", "When no numbered rule applies, keep the newest non-zero QC record and drop the rest.", "Confirm no higher-priority rule applies and select the first non-zero QC.", "PASS when exactly the default-selected record remains.", "Review routing priority and the selected default record."),
    "FA-GROUP-RECONCILIATION": _meta("Final Action group reconciliation", "Every group record must receive exactly one KEEP or DROP decision.", "Compare input record IDs with decision record IDs and detect duplicates/missing decisions.", "PASS when input count equals unique decision count and each record is decided once.", "Fix missing or duplicate decisions in the selected rule."),
    "FA-STAGE-RECONCILIATION": _meta("Final Action stage reconciliation", "Every valid source claim must be decided or explicitly failed/blocked.", "Compare all valid source IDs against decisions and explicit failed/blocked IDs.", "PASS when no valid claim remains unexplained.", "Trace each undecided record to grouping, routing, or rule evaluation."),
    "FA-ACTUAL-OUTPUT-RECONCILIATION": _meta("Final Action actual-output reconciliation", "Actual retained output must exactly match expected KEEP decisions.", "Compare expected KEEP identities with actual output identities and duplicates.", "PASS when there are no missing, unexpected, or duplicate output records.", "Regenerate Final Action output or correct expected identity mapping."),
    "FA-SORT-ORDER-LD3137": _meta("Final Action LD-3137 sort-order validation", "admissionDate must be excluded from the Final Action input sort order so equal business keys remain contiguous.", "Inspect the configured sort fields and confirm admission_date/admissionDate is absent.", "PASS when the configured sort order excludes admissionDate.", "Remove admissionDate from Final Action sort configuration and rerun legacy-output comparison."),
    "FA-GROUP-CONTIGUITY-LD3137": _meta("Final Action LD-3137 grouping evidence", "Claims sharing record type, HICN, provider, from date, and thru date must be evaluated in one Final Action group even when admissionDate differs.", "Bucket all source records by the approved key and show groups containing multiple admission dates.", "PASS when admissionDate is absent from the identity and all matching records map to one bucket.", "Correct the group key or remove admissionDate from upstream sorting."),

    # Split
    "SP-PRE-SOURCE": _meta("Split source availability", "Split validation requires source claim records.", "Confirm source-role records are present.", "PASS when source count is greater than zero.", "Add Split source files."),
    "SP-PRE-DATES": _meta("Split date validation", "Admission, stay-from, and stay-thru dates must use supported valid formats.", "Parse the configured dates for each claim.", "PASS when required dates parse successfully.", "Correct the invalid or missing date field."),
    "SP-PRE-DATE-ORDER": _meta("Split stay date order", "Stay-from date must not be later than stay-thru date.", "Compare parsed stay-from and stay-thru dates.", "PASS when from <= thru.", "Correct reversed stay dates."),
    "SP-SORT-ORDER-LD3137": _meta("Split LD-3137 sort-order validation", "admissionDate must be excluded from the Split input sort order.", "Inspect configured Split sort fields.", "PASS when admissionDate is absent and the legacy business key remains contiguous.", "Remove admissionDate from Split sort configuration."),
    "SP-GROUP-CONTIGUITY-LD3137": _meta("Split LD-3137 grouping evidence", "Claims sharing the Split business identity must not be separated solely by admissionDate.", "Bucket source records using the configured identity and show multi-admission-date groups.", "PASS when admissionDate is absent from the identity.", "Correct Split identity/sort configuration."),
    "SP-REC-TYPE-BYPASS": _meta("Split transaction-code bypass", "Configured transaction codes, normally 0 and 4, bypass slicing.", "Inspect transaction code and determine whether Split is applicable.", "PASS/NOT_APPLICABLE reflects the configured bypass route.", "Correct transaction-code mapping or bypass configuration."),
    "SP-RULE-INDICATOR": _meta("Split-year indicator derivation", "Eligible claims must derive Y#0109, Y#1012, or Y99999 according to date window and reference month.", "Calculate the expected indicator and compare it with the populated indicator.", "PASS when actual indicator exactly equals the calculated value.", "Correct the split-year calculation or the output field."),
    "SP-OUTPUT-RECONCILIATION": _meta("Split output reconciliation", "Actual Split output cannot contain missing, unexpected, or duplicate claim identities.", "Compare source identities with actual output identities.", "PASS when output membership reconciles to expected routing.", "Remove duplicates/unexpected records and restore missing expected records."),
    "SP-ACTUAL-DUPLICATE-IDENTITY": _meta("Split duplicate output identity", "Each Split output identity must be unique.", "Index actual records using configured identity fields and detect duplicates.", "PASS when duplicate count is zero.", "Deduplicate actual Split output."),

    # Stay
    "ST-PRE-SOURCE": _meta("Stay source availability", "Stay processing requires source claims.", "Confirm at least one source-role claim exists.", "PASS when source count is greater than zero.", "Add Stay source files."),
    "ST-CODE-COLLECTION-STRUCTURE": _meta("Stay code collection structure", "Condition, span, occurrence, and value-code containers must use the expected list/object structure.", "Inspect collection type and each contained code object.", "PASS when the collection is structurally valid.", "Correct malformed code collections or entries."),
    "ST-DRG-PRICE-LATEST-RECORD": _meta("Stay DRG price latest-record precedence", "MEDPAR-DRG-PRICE-0380 must come from the approved latest Stay claim.", "Order claims and compare expected latest DRG price to actual.", "PASS when the latest eligible value is selected.", "Use the latest claim value according to processing-date ordering."),
    "ST-DTE-CR-ENDED-LATEST-RECORD": _meta("Stay date-created-ended latest-record precedence", "MEDPAR-DTE-CR-ENDED-0220 must use the approved latest source value.", "Select the latest source claim and compare its date to actual output.", "PASS when latest-record precedence is applied.", "Correct the source-claim selection."),
    "ST-TOTAL-CHARGE": _meta("Stay total charge", "MEDPAR-TOT-CHRG-0400 must reconcile to eligible source charges using Decimal precision.", "Convert charges directly to Decimal, sum eligible values, quantize, and compare.", "PASS when exact configured-scale totals match.", "Correct included lines, Decimal conversion, scale, or rounding mode."),
    "ST-VALUE-CODE-SEQUESTRATION": _meta("Stay sequestration reduction amount", "MEDPAR-SQSTRTN-RDCTN-AMT-1130 must derive from eligible Value Code 73 amounts.", "Select Value Code 73, preserve sign, calculate using Decimal, and compare at configured precision.", "PASS when derived and actual values exactly match.", "Correct Value Code 73 selection or Decimal rounding."),
    "ST-DECIMAL-PRECISION": _meta("Stay Decimal precision", "Stay monetary calculations must avoid binary floating-point errors and use configured three-decimal precision.", "Convert with Decimal(str(value)) and quantize using configured scale/mode.", "PASS when normalized Decimal value matches expectation.", "Remove float conversion and apply configured Decimal quantization."),
    "ST-SELECTED-DECIMAL": _meta("Stay selected amount validation", "Selected Stay amount fields must be valid numeric Decimal values.", "Parse and validate the selected amount field.", "PASS when the value is numeric and valid for the field.", "Correct nonnumeric/null value or field mapping."),
    "ST-SELECTED-DECIMAL-PRECISION": _meta("Stay selected amount scale", "Selected Stay amount fields must conform to configured calculation precision.", "Quantize and compare the selected amount at the configured scale.", "PASS when actual scale/value is correct.", "Correct Decimal scale or rounding."),
    "ST-SNF-QUAL-DATE-ORDER": _meta("Stay SNF qualification date order", "SNF qualification from-date must not be after thru-date.", "Parse and compare MEDPAR-SNF-QUAL-FROM-DATE-0180 and thru-date 0190.", "PASS when from <= thru or the rule is not applicable.", "Correct the SNF qualification dates."),
    "ST-SORT-ORDER-LD3137": _meta("Stay LD-3137 sort/group validation", "admissionDate must be excluded from the Stay input sort/group key so claims are not split into separate groups.", "Inspect Stay identity and sort fields.", "PASS when admissionDate is absent and splitYearIndicator participates in grouping.", "Remove admissionDate and use the approved Stay grouping key."),
    "ST-GROUP-CONTIGUITY-LD3137": _meta("Stay LD-3137 grouping evidence", "Stay claims with the same HICN, provider, and SplitYearIndicator must remain one bucket despite differing admission dates.", "Bucket Stay source claims and report any business group containing multiple admission dates.", "PASS when all such claims map to one identity.", "Correct Stay identity fields or upstream sort configuration."),
    "ST-SPAN-CODE-LIMIT": _meta("Stay unique Span Code consolidation", "Save unique Span Code/date groups from all claims in the combined Stay, up to 10.", "Apply latest-record precedence to duplicate codes, retain unique groups, and limit output to ten.", "PASS when the consolidated output contains no more than ten unique Span Code/date groups.", "Correct duplicate precedence, collection order, or truncation to the ten-group limit."),
    "ST-GOLDEN-COMPARISON": _meta("Stay golden regression availability", "Field-by-field golden comparison requires both actual and approved expected Stay output.", "Confirm both roles are supplied before golden comparison.", "NOT_APPLICABLE when both are not supplied; PASS/FAIL is emitted by field comparisons when they are.", "Supply actual and expected Stay files for golden mode."),
    "ST-OUTPUT-RECONCILIATION": _meta("Stay output reconciliation", "Actual Stay output must reconcile to expected Stay identities.", "Compare source-derived identities with actual-output identities.", "PASS when there are no unexpected output identities.", "Remove unexpected Stay records and restore missing expected output."),

    # Intermediate
    "INT-PRE-SOURCE": _meta("Intermediate source availability", "Intermediate validation requires Stay/intermediate source records.", "Confirm source-role records are present.", "PASS when source count is greater than zero.", "Add Intermediate source files."),
    "INT-DECIMAL-PRECISION": _meta("Intermediate Decimal precision", "Amount fields must retain configured three-decimal precision without float conversion.", "Parse with Decimal(str(value)), quantize, and compare.", "PASS when the exact Decimal value/scale is correct, including negative numbers.", "Remove float conversion and use configured Decimal rounding."),
    "INT-REPEATED-DECIMAL-PRECISION": _meta("Intermediate repeated charge precision", "Repeated amount arrays must preserve order/duplicates and each value must use Decimal precision.", "Validate every array value in position order.", "PASS when all repeated values are valid and correctly scaled.", "Correct array ordering, deduplication, or Decimal conversion."),
    "INT-ACCOMMODATION-ARRAY-ALIGNMENT": _meta("Intermediate accommodation array alignment", "Accommodation charge and day arrays must preserve corresponding positions.", "Compare array lengths and positional relationships.", "PASS when arrays align exactly.", "Correct missing/extra entries or array order."),
    "INT-ACCOMMODATION-TOTAL": _meta("Intermediate total accommodation charge", "MEDPAR-TOT-ACC-CHRG-0430 must equal the sum of accommodation charges after each individual charge is rounded to the configured scale.", "Quantize every accommodation charge first, then sum the rounded values and compare with the populated total.", "PASS when sum(round(each charge)) exactly equals the quantized total; summing raw values before rounding is incorrect.", "Move rounding before summation in rev_center_charges_01.py or correct the populated total."),
    "INT-BILL-TOT-PERDIEM-ROUNDING": _meta("Intermediate bill total per-diem rounding", "MEDPAR-BILL-TOT-PERDIEM-0381 must round passThruPerDiem before multiplying by utilizationDays.", "Quantize passThruPerDiem, multiply by utilizationDays, then compare the result.", "PASS when the populated total equals round(per-diem) × utilization days.", "Move rounding before multiplication in directMoveVariables5.py."),
    "INT-INTENSIVE-CARE-IND-0481": _meta("Intermediate intensive-care indicator", "MEDPAR-INTENSIVE-CARE-IND-0481 must search the complete approved revenue-code family, including 0200 and 0201.", "Inspect revenue-center lines for any configured intensive-care code and derive Y/N.", "PASS when the indicator is Y when a matching code exists and N otherwise.", "Add missing codes to rev_center_indicators_01.py or correct the output indicator."),
    "INT-ORGAN-IND-0487": _meta("Intermediate organ-acquisition indicator", "MEDPAR-ORGAN-IND-0487 must match the configured legacy revenue-code derivation.", "Inspect revenue-center lines against the approved organ-acquisition code list and derive Y/N.", "PASS when the output matches the configured legacy code list; BLOCKED if that list is not configured.", "Confirm the exact legacy revenue-code list and update intermediate settings."),
    "INT-ADMISSION-DAY-0090": _meta("Intermediate admission-day code", "medparAdmDay0090 must be calculated from admissionDate.", "Parse admissionDate and derive Sunday=1 through Saturday=7.", "PASS when the populated day code matches the admission calendar day.", "Correct populate_date_fields.py or confirm a different legacy day-number mapping."),
    "INT-CONDITION-SWITCH": _meta("Intermediate condition-code switch", "Configured MEDPAR indicator switches must be derived from their approved condition codes.", "Collect condition codes and compare each derived Y/N switch.", "PASS when each switch matches its configured code mapping.", "Correct condition-code mapping or output switch population."),
    "INT-REVENUE-LINE-ITEMS": _meta("Intermediate revenue-center line fields", "Revenue-center code, NDC/UPC, units, charges, patient add-on, RP indicator, and model reimbursement sub-fields must be structurally valid.", "Validate every revenue line field-by-field and retain Decimal precision for amounts.", "PASS when every line has a code, valid units, and valid Decimal amounts.", "Correct malformed revenue-center lines or alias mappings."),
    "INT-SOURCE-TO-TARGET": _meta("Intermediate direct-move field preservation", "Fields designated as direct moves must not change from Stay/source to Intermediate output.", "Compare the source field with the actual Intermediate field, using Decimal normalization for amount fields.", "PASS when source and actual values match exactly after approved normalization.", "Correct direct-move mapping or unexpected transformation."),
    "INT-PROC-MAX-25": _meta("Intermediate procedure-group maximum", "Up to 25 procedure code/version/date groups from all claims in a Stay may be populated.", "Count populated procedure groups after consolidation.", "PASS when the count is 0 through 25.", "Correct multi-claim consolidation or truncate according to the approved 25-group rule."),
    "INT-PROC-CODE-COUNT": _meta("Intermediate procedure-code count", "MEDPAR-NO-SURG-CODES-0511 must equal populated procedure-code count.", "Count valid procedure codes and compare to the reported count.", "PASS when counts match.", "Correct the count or procedure-code array."),
    "INT-PROC-DATE-COUNT": _meta("Intermediate procedure-date count", "MEDPAR-NO-SURG-DATES-0512 must equal populated procedure-date count.", "Count valid procedure dates and compare to the reported count.", "PASS when counts match.", "Correct the count or procedure-date array."),
    "INT-PROC-VERSION-ALIGNMENT": _meta("Intermediate procedure version alignment", "Procedure codes and version codes must align positionally.", "Compare array lengths and each code/version position.", "PASS when each procedure has its corresponding version.", "Correct array positions or missing versions."),
    "INT-PROC-DATE-WINDOW": _meta("Intermediate procedure date window", "Procedure dates must be inside the January-aligned five-year window.", "Calculate January 1 of run-year minus four years through run date and test each procedure date.", "PASS when every applicable date is within the window.", "Correct out-of-window dates or business run date."),
    "INT-DEATH-AFTER-ADMISSION": _meta("Intermediate death-after-admission indicator", "medparDeathAfterAdm0611 must be derived from admission date and date of death.", "Compare date of death with admission date and expected indicator.", "PASS when the populated indicator matches the date relationship.", "Correct source dates or indicator derivation."),
    "INT-AGE": _meta("Intermediate age", "MEDPAR-AGE-0030 must be a valid integer in the approved range.", "Parse age and validate configured range, currently 0 through 120.", "PASS when age is a valid in-range integer.", "Correct age source/derivation or invalid formatting."),
    "INT-NDC": _meta("Intermediate NDC number", "MEDPAR-REV-CNTR-NDC-NUM-1550 must follow configured normalization and length.", "Normalize characters/leading zeros and validate the configured length.", "PASS when normalized NDC equals the expected format.", "Correct NDC source, cleaning, or padding rules."),
    "INT-GOLDEN-COMPARISON": _meta("Intermediate golden regression availability", "Golden field comparison requires both actual and approved expected Intermediate output.", "Confirm actual and expected roles are supplied.", "NOT_APPLICABLE without both; detailed field results are emitted when supplied.", "Supply actual and expected Intermediate files for golden mode."),
    "INT-OUTPUT-RECONCILIATION": _meta("Intermediate output reconciliation", "Actual Intermediate output must contain no unexpected identities.", "Compare source and actual identity sets.", "PASS when unexpected identity count is zero.", "Remove unexpected records and restore missing expected records."),

    # Final MEDPAR
    "FM-PRE-SOURCE": _meta("Final MEDPAR source availability", "Final MEDPAR validation requires source records.", "Confirm source-role records exist.", "PASS when source count is greater than zero.", "Add Final MEDPAR source files."),
    "FM-SORT-ORDER-LD3137": _meta("Final MEDPAR LD-3137 sort-order validation", "admissionDate must be excluded from the Final Process input sort order.", "Inspect Final MEDPAR sort and identity fields.", "PASS when admissionDate is absent and records sharing the legacy key remain contiguous.", "Remove admissionDate from Final Process sort configuration."),
    "FM-GROUP-CONTIGUITY-LD3137": _meta("Final MEDPAR LD-3137 grouping evidence", "Final records sharing HICN, provider, and SplitYearIndicator must not be separated solely by admissionDate.", "Bucket Final source records using the configured identity and report multi-admission-date groups.", "PASS when admissionDate is absent from the identity.", "Correct Final MEDPAR identity/sort configuration."),
    "FM-SPLIT-YEAR-INDICATOR": _meta("Final MEDPAR split-year indicator", "Final output must contain a valid split-year indicator.", "Validate format and, in golden mode, compare the field value.", "PASS when the indicator is one of Y#0109, Y#1012, or Y99999 and matches expected when supplied.", "Correct the indicator derivation or final mapping."),
    "FM-CLASSIFICATION": _meta("Final MEDPAR SS/LS/SNF classification", "Final output must use an allowed classification such as SS, LS, or SNF.", "Compare classification against configured allowed values.", "PASS when classification is allowed.", "Correct final classification logic or configuration."),
    "FM-BYTE-LENGTH": _meta("Final MEDPAR 3000-byte length", "The serialized fixed-width Final MEDPAR record must be exactly 3000 bytes in the configured encoding.", "Encode the actual record text and count bytes.", "PASS when encoded length equals configured expected bytes.", "Correct serialization, padding, truncation, or character encoding."),
    "FM-BYTE-FIELD": _meta("Final MEDPAR byte-field layout", "Configured fixed-width fields must occupy their approved byte offsets and lengths.", "Slice the encoded record at configured positions and compare field content/width.", "PASS when the field occupies the correct bytes.", "Correct byte offsets, width, padding, or source formatting."),
    "FM-SELECTED-FIELD-PRESENCE": _meta("Final MEDPAR selected-field presence", "Configured final selected fields should be populated when applicable.", "Read each selected field from the final record.", "PASS when populated; NOT_APPLICABLE when legitimately absent under current mode.", "Correct field mapping or supply approved expected applicability."),
    "FM-GOLDEN-COMPARISON": _meta("Final MEDPAR golden regression availability", "Golden comparison requires both actual and approved expected final output.", "Confirm both roles exist.", "NOT_APPLICABLE without both; field-level comparisons run when supplied.", "Supply actual and expected Final MEDPAR files."),
    "FM-OUTPUT-RECONCILIATION": _meta("Final MEDPAR output reconciliation", "Final output cannot contain unexpected identities.", "Compare source identities with actual final identities.", "PASS when unexpected identity count is zero.", "Remove unexpected final records and restore missing expected records."),
}


def _generic(stage: str, rule_id: str, field_name: str | None) -> RuleMetadata:
    readable_stage = stage.replace("_", " ").title()
    readable_rule = rule_id.replace("-", " ").replace("_", " ").title()
    field_text = f" for {field_name}" if field_name else ""
    if "REGRESSION" in rule_id or "GOLDEN" in rule_id:
        return _meta(
            f"{readable_stage} field regression{field_text}",
            "Actual output must match the approved expected output for the selected field.",
            f"Compare expected and actual values{field_text} using the configured field mapping.",
            "PASS when expected and actual are equal after approved normalization; otherwise FAIL.",
            "Review source-to-target mapping, derivation logic, precision, and approved expected data.",
        )
    if "DUPLICATE" in rule_id:
        return _meta(
            f"{readable_stage} duplicate identity validation",
            "Each business identity must occur only once in the applicable dataset.",
            "Index records using configured identity fields and identify repeated keys.",
            "PASS when duplicate identity count is zero.",
            "Remove or correctly merge duplicate records.",
        )
    if "MISSING-ACTUAL" in rule_id:
        return _meta(
            f"{readable_stage} missing actual output",
            "Reconcile/golden mode requires an actual application-output record for every expected identity.",
            "Look up the source identity in actual output.",
            "PASS when a matching actual record exists; FAIL when absent.",
            "Generate or supply the missing actual-output record.",
        )
    if "MISSING-EXPECTED" in rule_id:
        return _meta(
            f"{readable_stage} missing approved expected output",
            "Golden mode requires an approved expected record for every tested identity.",
            "Look up the source identity in expected output.",
            "PASS when a matching expected record exists; FAIL when absent.",
            "Create or supply the missing approved expected record.",
        )
    return _meta(
        readable_rule,
        f"The {readable_stage} process must satisfy validation {rule_id}{field_text}.",
        f"Execute the configured business check{field_text} and record expected versus observed evidence.",
        "PASS when the observed condition satisfies the configured expectation; FAIL otherwise.",
        "Review the expected/actual values, source records, and technical evidence shown in this card.",
    )


def get_rule_metadata(stage: str, rule_id: str, field_name: str | None = None) -> RuleMetadata:
    return CATALOG.get(rule_id) or _generic(stage, rule_id, field_name)


def conclusion_text(
    *,
    status: str,
    message: str,
    expected: Any,
    actual: Any,
    metadata: RuleMetadata,
) -> str:
    if status == "PASS":
        return (
            f"PASS — {message}. Observed result {actual!r} satisfied the expected "
            f"condition {expected!r}. {metadata.pass_meaning}"
        )
    if status == "FAIL":
        return (
            f"FAIL — {message}. Expected {expected!r}, but observed {actual!r}. "
            f"{metadata.fail_meaning}"
        )
    if status == "BLOCKED":
        return (
            f"BLOCKED — {message}. The framework intentionally did not guess the result. "
            f"Required expectation/context: {expected!r}; observed: {actual!r}."
        )
    return (
        f"NOT APPLICABLE — {message}. This validation was evaluated but its prerequisite "
        "did not apply to the current record or execution mode."
    )


def stage_rule_catalog(stage: str) -> list[tuple[str, RuleMetadata]]:
    prefixes = {
        "final_action": ("FA-",),
        "split": ("SP-",),
        "stay": ("ST-",),
        "intermediate": ("INT-",),
        "final_medpar": ("FM-",),
    }
    selected = {
        rule_id: metadata
        for rule_id, metadata in CATALOG.items()
        if rule_id.startswith(prefixes.get(stage, (stage.upper() + "-",)))
    }
    for rule_id in KNOWN_STAGE_RULE_IDS.get(stage, ()):
        selected.setdefault(rule_id, CATALOG.get(rule_id) or _generic(stage, rule_id, None))
    for rule_id in ("INGEST-DISCOVERY", "INGEST-READ-FILE", "INGEST-NO-RECORDS", "STAGE-FINAL-SUMMARY"):
        selected[rule_id] = CATALOG[rule_id]
    return sorted(selected.items())

KNOWN_STAGE_RULE_IDS: dict[str, tuple[str, ...]] = {
    "final_action": (
        "FA-PRE-EMPTY-GROUP", "FA-PRE-SOURCE-FILES", "FA-PRE-SCHEMA", "FA-PRE-GROUPING", "FA-PRE-ORDERING", "FA-SORT-ORDER-LD3137", "FA-GROUP-CONTIGUITY-LD3137",
        "FA-ALL-QC0", "FA-RULE-01", "FA-RULE-02", "FA-RULE-03", "FA-RULE-05", "FA-RULE-06", "FA-RULE-07", "FA-RULE-08", "FA-RULE-09", "FA-RULE-10A", "FA-RULE-10B", "FA-DEFAULT",
        "FA-GROUP-RECONCILIATION", "FA-STAGE-RECONCILIATION", "FA-ACTUAL-OUTPUT-RECONCILIATION",
    ),
    "split": (
        "SP-PRE-SOURCE", "SP-PRE-DATES", "SP-PRE-DATE-ORDER", "SP-SORT-ORDER-LD3137", "SP-GROUP-CONTIGUITY-LD3137", "SP-REC-TYPE-BYPASS", "SP-RULE-INDICATOR",
        "SP-ACTUAL-DUPLICATE-IDENTITY", "SP-OUTPUT-RECONCILIATION",
    ),
    "stay": (
        "ST-PRE-SOURCE", "ST-SORT-ORDER-LD3137", "ST-GROUP-CONTIGUITY-LD3137", "ST-SPAN-CODE-LIMIT", "ST-ACTUAL-DUPLICATE-IDENTITY", "ST-EXPECTED-DUPLICATE-IDENTITY",
        "ST-ADMISSION-DATE", "ST-STAY-DATE-ORDER", "ST-BILL-COUNT", "ST-CODE-COLLECTION-STRUCTURE",
        "ST-DTE-CR-ENDED-0220-FORMAT", "ST-DTE-CR-ENDED-LATEST-RECORD", "ST-DRG-PRICE-LATEST-RECORD",
        "ST-TOTAL-CHARGE", "ST-VALUE-CODE-SEQUESTRATION", "ST-DECIMAL-PRECISION", "ST-SELECTED-DECIMAL",
        "ST-SELECTED-DECIMAL-PRECISION", "ST-SNF-QUAL-FROM-DATE-FORMAT", "ST-SNF-QUAL-THRU-DATE-FORMAT",
        "ST-SNF-QUAL-DATE-ORDER", "ST-MISSING-ACTUAL-OUTPUT", "ST-MISSING-EXPECTED-OUTPUT",
        "ST-GOLDEN-COMPARISON", "ST-OUTPUT-RECONCILIATION",
    ),
    "intermediate": (
        "INT-PRE-SOURCE", "INT-SOURCE-DUPLICATE-IDENTITY", "INT-ACTUAL-DUPLICATE-IDENTITY", "INT-EXPECTED-DUPLICATE-IDENTITY",
        "INT-DECIMAL-PRECISION", "INT-REPEATED-DECIMAL-PRECISION", "INT-SELECTED-DECIMAL", "INT-SNF-QUAL-THRU-DATE",
        "INT-ACCOMMODATION-DAYS", "INT-ACCOMMODATION-ARRAY-ALIGNMENT", "INT-ACCOMMODATION-TOTAL",
        "INT-BILL-TOT-PERDIEM-ROUNDING", "INT-INTENSIVE-CARE-IND-0481", "INT-ORGAN-IND-0487", "INT-ADMISSION-DAY-0090",
        "INT-CONDITION-SWITCH", "INT-REVENUE-LINE-ITEMS", "INT-SOURCE-TO-TARGET",
        "INT-PROC-CODE-COUNT", "INT-PROC-DATE-COUNT", "INT-PROC-MAX-25", "INT-PROC-VERSION-ALIGNMENT", "INT-PROC-DATE-WINDOW", "INT-PROC-SURGICAL-INDICATOR",
        "INT-CALENDAR-ALIGNED-DATE-WINDOW", "INT-DEATH-AFTER-ADMISSION", "INT-AGE", "INT-NDC",
        "INT-MISSING-ACTUAL-OUTPUT", "INT-MISSING-EXPECTED-OUTPUT", "INT-GOLDEN-COMPARISON", "INT-OUTPUT-RECONCILIATION",
    ),
    "final_medpar": (
        "FM-PRE-SOURCE", "FM-SORT-ORDER-LD3137", "FM-GROUP-CONTIGUITY-LD3137", "FM-SOURCE-DUPLICATE-IDENTITY", "FM-ACTUAL-DUPLICATE-IDENTITY", "FM-EXPECTED-DUPLICATE-IDENTITY",
        "FM-SPLIT-YEAR-INDICATOR", "FM-CLASSIFICATION", "FM-BYTE-LENGTH", "FM-BYTE-FIELD", "FM-SELECTED-FIELD-PRESENCE",
        "FM-MISSING-ACTUAL-OUTPUT", "FM-MISSING-EXPECTED-OUTPUT", "FM-GOLDEN-COMPARISON", "FM-OUTPUT-RECONCILIATION",
    ),
}
