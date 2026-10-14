"""Materialize supported source calculations without reading comparison output files.

Calculations are shared with validation, so self-validation is not independent CMS
acceptance. Export coverage and unavailable operands are disclosed alongside outputs.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from medpar_qa.enums import Stage
from medpar_qa.models import SourceRecord
from medpar_qa.normalization.fields import _key_form
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.decimal_values import to_decimal
from medpar_qa.stages.intermediate.business_rules import whole_dollars, line_value


class GenerationBlocked(ValueError):
    """A required source operand or export definition is unavailable."""


def put(data, field, value, resolver):
    """Write canonical values and synchronize existing aliases, including nested fields."""
    value = str(value) if isinstance(value, Decimal) else value.isoformat() if isinstance(value, date) else value
    for path in [field, *resolver.aliases.get(field, [])]:
        parts=path.split('.'); parents=[data]
        for part in parts[:-1]:
            parents=[child for parent in parents for key,child in parent.items() if _key_form(key)==_key_form(part) and isinstance(child,dict)]
        for parent in parents:
            for key in list(parent):
                if _key_form(key)==_key_form(parts[-1]):
                    # EQ-BIC may be one/two characters, while hicn is CAN + EQ-BIC.
                    # Preserve the original component; these are not interchangeable values.
                    if field=='hicn' and _key_form(key)=='claimcannchequatable' and len(str(parent[key]).strip()) in (1,2):
                        continue
                    parent[key]=deepcopy(value)
    data[field]=deepcopy(value)


def required(record, resolver, *names):
    for name in names:
        value=resolver.get(record.data,name)
        if value not in (None,''):return value
    raise GenerationBlocked('Missing source operand: '+names[0])


def stay(records, processor):
    from medpar_qa.stages.stay.merge_rules import FIRST_FIELDS,LAST_FIELDS,FIRST_FOUND_FIELDS,HIGH_DATES,LOW_DATES,SUM_FIELDS
    from medpar_qa.stages.stay.code_precedence import latest_values_by_code,strip_lineage
    from medpar_qa.stages.stay.revenue_merge import aggregate_revenue
    from medpar_qa.stages.stay.warnings import warning06,warning08
    resolver=processor.resolver;payload=[];notes=[]
    grouped=processor._group_sources(records)
    if sum(map(len,grouped.values()))!=len(records):raise GenerationBlocked('Stay grouping requires HICN, provider and admission date on every bill')
    for group in grouped.values():
        def get(record,field):return resolver.get(record.data,field)
        ordered=sorted(group,key=lambda r:(parse_date(get(r,'stay_from_date')),parse_date(get(r,'stay_thru_date')),-(parse_date(get(r,'processing_date'),allow_none=True) or date.min).toordinal(),-(parse_date(get(r,'accrete_date'),allow_none=True) or date.min).toordinal(),-int(get(r,'query_code') or 0),str(get(r,'icn') or '')))
        first,last=ordered[0],ordered[-1];row=deepcopy(first.data)
        # Single-bill original fields remain intact; consolidation applies to multi-bill stays.
        if len(group)>1:
            for fields,record in ((FIRST_FIELDS,first),(LAST_FIELDS,last)):
                for field in fields:
                    value=get(record,field)
                    if value is not None:put(row,field,value,resolver)
            for field in FIRST_FOUND_FIELDS:
                value=next((get(r,field) for r in ordered if get(r,field) not in (None,'')),None)
                if value is not None:put(row,field,value,resolver)
            for fields,chooser in ((HIGH_DATES,max),(LOW_DATES,min)):
                for field in fields:
                    values=[parse_date(get(r,field)) for r in ordered if get(r,field) not in (None,'')]
                    if values:put(row,field,chooser(values),resolver)
            for field in SUM_FIELDS:
                values=[get(r,field) for r in ordered]
                if any(v is not None for v in values):
                    if any(v is None for v in values):raise GenerationBlocked('Missing bill operand for Stay sum: '+field)
                    put(row,field,sum(map(to_decimal,values),Decimal(0)),resolver)
            put(row,'bill_count',len(group),resolver)
            for field,limit in (('condition_codes',30),('occurrence_codes',30),('occurrence_span_lines',10),('value_lines',36)):
                put(row,field,strip_lineage(latest_values_by_code(group,collection_path=field,date_paths=('processing_date','accrete_date'),resolver=resolver))[:limit],resolver)
            lines=[line for record in ordered for line in (get(record,'revenue_lines') or [])]
            put(row,'revenue_lines',aggregate_revenue(lines),resolver)
            arrays=[get(r,'ngAcoIndicatorCodes') for r in ordered]
            if any(isinstance(a,list) for a in arrays):put(row,'ngAcoIndicatorCodes',[next((a[i] for a in arrays if isinstance(a,list) and len(a)>i and a[i] not in (None,'')),'') for i in range(4)],resolver)
            counters=[get(r,'accreteCounter') for r in ordered if get(r,'accreteCounter') is not None]
            if counters:put(row,'accreteCounter',max(map(int,counters)),resolver)
        for field,limit in (('condition_codes',30),('occurrence_codes',30),('occurrence_span_lines',10),('value_lines',36)):
            put(row,field,strip_lineage(latest_values_by_code(group,collection_path=field,date_paths=('processing_date','accrete_date'),resolver=resolver))[:limit],resolver)
        if len(group)==1 and get(first,'bill_count') is None:
            put(row,'bill_count',1,resolver)
            notes.append('Single-bill count populated as one; supplied source counts are preserved because legacy 0/1 conventions conflict')
        qcs={str(get(r,'query_code')) for r in group}
        put(row,'warning_indicator_01',str(('0' in qcs)+2*('5' in qcs)),resolver)
        put(row,'warning_indicator_05','0' if len(group)==1 else '2' if str(get(first,'transaction_code')) in ('0','4') and str(get(last,'discharge_status') or get(last,'patientStatus'))=='30' else '1',resolver)
        for number,function in ((6,warning06),(8,warning08)):
            try:put(row,f'warning_indicator_{number:02}',function(group,resolver),resolver)
            except LookupError as exc:notes.append(str(exc))
        # 0380 needs all six monetary operands: no fabricated zero defaults.
        try:
            price=Decimal(0)
            for r in group:
                for names in [('claim_payment_amount','claimPaymentAmount','reimbursement_amount'),('primary_payer_amount','primary_payment_amount'),('coinsurance_amount','coinsuranceAmount'),('inpatient_deductible_amount','inPatientDeduction'),('blood_deductible_amount','bloodDeductable')]:price+=to_decimal(required(r,resolver,*names))
                price-=to_decimal(required(r,resolver,'outlier_payment_amount','outlierAmount'))
            put(row,'medpar_drg_price_0380',whole_dollars(price),resolver)
        except GenerationBlocked as exc:notes.append(str(exc))
        if len(group)>1:
            amount=get(SourceRecord(row,first.source,first.record_id),'totalCharges')
            if amount is not None:put(row,'medpar_tot_chrg_0400',whole_dollars(amount),resolver)
        spans=[line for r in group for line in (get(r,'occurrence_span_lines') or [])]
        ends=[parse_date(line_value(line,'thru','toDate','thruDate','thru_date','spanThruDate','occurrenceSpanThruDate')) for line in spans if str(line_value(line,'code','spanCode','occurrenceSpanCode'))=='22']
        put(row,'medpar_dte_cr_ended_0220',max(ends).strftime('%Y%j') if ends and str(get(first,'transaction_code')) in ('0','4') else '',resolver)
        newest=sorted(group,key=lambda r:parse_date(get(r,'processing_date'),allow_none=True) or date.min,reverse=True)
        ide=next((get(r,'investigationalDeviceExemption') for r in newest if get(r,'investigationalDeviceExemption') not in (None,'')),None)
        if ide is not None:put(row,'investigationalDeviceExemption',ide,resolver)
        put(row,'rpInd','R' if any(get(r,'rpInd')=='R' for r in group) else '',resolver)
        conditions=get(SourceRecord(row,first.source,first.record_id),'condition_codes') or []
        from medpar_qa.stages.stay.derivations import derive_condition_switch,derive_value_code_amount
        for field,code in (('medpar_infor_enctr_ind_sw_0800','04'),('medpar_ma_teach_ind_sw_0810','69')):put(row,field,derive_condition_switch(conditions,code),resolver)
        put(row,'medpar_sqstrtn_rdctn_amt_1130',derive_value_code_amount(group,resolver,code='73',scale=processor.settings.decimal_scale),resolver)
        lines=get(SourceRecord(row,first.source,first.record_id),'revenue_lines') or []
        if len(lines)>45:
            for i in range(0,len(lines),45):
                segment=deepcopy(row);put(segment,'revenue_lines',lines[i:i+45],resolver);payload.append(segment)
        else:payload.append(row)
    return payload,notes


def intermediate(records,processor):
    from medpar_qa.stages.intermediate.business_rules import validate_business_rules
    output=[];notes=['0531: approved external DRG grouper is not executed','0483/0484/0488/0850/0470/1620: complete approved mapping definitions remain unavailable'];resolver=processor.resolver
    for source in records:
        row=deepcopy(source.data)
        def calculation(field,value,error):
            if error:
                notes.append(field+': '+error)
                if resolver.get(source.data,field) not in (None,''):raise GenerationBlocked('Cannot regenerate populated field '+field+': '+error)
            else:put(row,field,'' if value is None else value,resolver)
        target=SourceRecord({},source.source,source.record_id)
        validate_business_rules(source,target,resolver,revenue_category_ranges=processor.settings.revenue_category_ranges,calculation_sink=calculation)
        def clinical(collection, code_source, version_source, extra_source, code_field, version_field, extra_field):
            lines=resolver.get(source.data,collection)
            if lines is not None and any(isinstance(line,dict) for line in lines):
                codes=[];versions=[];extras=[]
                for line in lines[:25]:
                    code=line_value(line,'code','procedureCode','diagnosisCode')
                    if not code: continue
                    version=line_value(line,'version','codeVersion','icdVersion')
                    extra=line_value(line,'date','procedureDate','surgeryDate') if collection=='procedure_lines' else line_value(line,'poa','presentOnAdmission','poaIndicator')
                    if version in (None,'') or extra in (None,''):raise GenerationBlocked('Clinical code requires source version and aligned date/POA: '+str(code))
                    codes.append(code);versions.append(version);extras.append(parse_date(extra).strftime('%Y%j') if collection=='procedure_lines' else extra)
            else:
                codes=resolver.get(source.data,code_source)
                if codes is None:codes=resolver.get(source.data,code_field)
                codes=[] if codes is None else codes
                versions=resolver.get(source.data,version_source)
                if versions is None:versions=resolver.get(source.data,version_field)
                versions=[] if versions is None else versions
                extras=resolver.get(source.data,extra_source)
                if extras is None:extras=resolver.get(source.data,extra_field)
                extras=[] if extras is None else extras
                if len(codes)!=len(versions) or len(codes)!=len(extras):raise GenerationBlocked('Clinical source arrays must align: '+collection)
                codes,versions,extras=codes[:25],versions[:25],extras[:25]
            put(row,code_field,codes,resolver);put(row,version_field,versions,resolver);put(row,extra_field,extras,resolver)
            return len(codes),len(extras)
        count,dates=clinical('procedure_lines','procedure_codes_source','procedure_versions_source','procedure_dates_source','medpar_surg_code_0513','medpar_srgcl_prcdr_vrsn_cd','medpar_surg_date_0514')
        declared=resolver.get(source.data,'medpar_no_surg_codes_0511')
        if declared not in (None,'') and int(declared)!=count:raise GenerationBlocked('Declared procedure count does not match source code arrays')
        put(row,'medpar_no_surg_codes_0511',count,resolver);put(row,'medpar_no_surg_dates_0512',dates,resolver);put(row,'medpar_surg_ind_0500','1' if count else '0',resolver)
        count,poa=clinical('diagnosis_lines','diagnosis_codes_source','diagnosis_versions_source','poa_indicators_source','medpar_diag_code_0492','medpar_dgns_vrsn_cd','medpar_poa_dgns_ind_cd')
        declared=resolver.get(source.data,'medpar_no_diag_codes_0491')
        if declared not in (None,'') and int(declared)!=count:raise GenerationBlocked('Declared diagnosis count does not match source code arrays')
        put(row,'medpar_no_diag_codes_0491',count,resolver);put(row,'medpar_poa_dgns_cd_cnt',poa,resolver)
        accommodation=resolver.get(row,'medpar_accommodation_chrg_0460')
        if accommodation is not None:put(row,'medpar_tot_acc_chrg_0430',whole_dollars(sum(map(to_decimal,accommodation),Decimal(0))),resolver)
        ndcs=[line_value(line,'ndcNumber','ndc','ndc_code') for line in (resolver.get(source.data,'revenue_lines') or [])]
        if any(ndcs):put(row,'medpar_rev_cntr_ndc_num_1550',[value for value in ndcs if value not in (None,'')][:10],resolver)
        output.append(row)
    return output,notes


def final_medpar(records,processor):
    from medpar_qa.stages.final_medpar.business_rules import bypass_required
    resolver=processor.resolver;output=[];dropped=[];notes=['Source-only export has no verified vendor DRG execution or complete revenue mapping acceptance evidence']
    for record in records:
        if bypass_required(record,resolver):
            dropped.append({'record':record.data,'reason':'Covered days exceed LOS / WI04 bypass','source_record_id':record.record_id});continue
        row=deepcopy(record.data)
        raw=resolver.get(row,'fixed_width_record')
        if raw is not None:
            encoded=raw if isinstance(raw,bytes) else str(raw).encode(processor.settings.encoding)
            if len(encoded)!=3050:raise GenerationBlocked('Final generation needs a 3050-byte Intermediate record before removing the 50-byte trailer')
            put(row,'fixed_width_record',encoded[:3000].decode(processor.settings.encoding),resolver)
        elif processor.settings.field_layout:
            from medpar_qa.processing.physical_export import encode_record
            # Encode after final classification and routing-field removal below.
        else:notes.append('Physical export unavailable: approved complete MPRRECL layout absent')
        provider=resolver.get(row,'medpar_prvdr_full_num_1660') or resolver.get(row,'provider_id')
        if provider is None or len(str(provider))!=6:raise GenerationBlocked('Final classification requires the original six-character provider number')
        char=str(provider)[2]
        put(row,'medpar_ss_ls_snf_ind_0140','N' if char in '56UWYZ' else 'S' if char in '01STMR' else 'L',resolver)
        if not processor.settings.split_indicator_in_output:
            for field in ['split_year_indicator',*resolver.aliases.get('split_year_indicator',[])]:row.pop(field,None)
        if raw is None and processor.settings.field_layout:
            try:
                put(row,'fixed_width_record',encode_record(row,resolver,processor.settings.field_layout,
                    expected_bytes=processor.settings.expected_bytes,encoding=processor.settings.encoding),resolver)
            except (ValueError,KeyError,UnicodeError) as exc:
                raise GenerationBlocked(str(exc)) from exc
        output.append(row)
    return output,notes,dropped
