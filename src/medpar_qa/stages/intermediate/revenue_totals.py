"""Revenue amount categories explicitly listed by V3 p33 (CR7/12/15)."""
from decimal import Decimal
from .business_rules import line_value, whole_dollars
from medpar_qa.normalization.decimal_values import to_decimal
from medpar_qa.stages.common import normalize_collection

FIELDS = ('medpar_mdcl_srg_gen_amt_0890','medpar_mdcl_srg_nstrl_amt_0900','medpar_mdcl_srg_strl_amt_0910','medpar_mdcl_srg_tkhme_amt_0920','medpar_prsthtc_orthtc_amt_0930','medpar_mdcl_srg_pcmkr_amt_0940','medpar_intraocular_ln_amt_0950','medpar_oxygn_tkehome_amt_0960','medpar_othr_implants_amt_0970','medpar_othr_suppl_dvc_amt_0980','medpar_incdnt_rdlgy_amt_0990','medpar_incdnt_dgn_srv_amt_1000','medpar_mdcl_srg_drsng_amt_1010','medpar_invstgtnl_dvc_amt_1020','medpar_crdc_cathrztn_amt_1120','medpar_oprtg_room_amt_1100','medpar_mdcl_srgl_misc_amt_1030','medpar_or_labor_dlvry_amt_1110','medpar_rdlgy_oncology_amt_1040','medpar_rdlgy_dgnstc_amt_1050','medpar_rdlgy_thrptc_amt_1060','medpar_rdlgy_nuclr_md_amt_1070','medpar_rdlgy_ct_scan_amt_1080','medpar_rdlgy_othr_img_amt_1090','medpar_algnc_stem_cellamt_1440','medpar_cell_gene_prc_amt_1510','medpar_cell_tpy_drug_amt_1520','medpar_gene_tpy_drug_amt_1530')
RANGES = [(n,n) for n in range(270,280)] + [(621,621),(622,622),(623,623),(624,624),(481,481),(360,719),(620,629),(720,729),(280,289),(320,329),(330,339),(340,349),(350,359),(400,409),(815,815),(870,879),(891,891),(892,892)]

def revenue_total(lines, low, high, *, round_result=True):
    if lines is None: raise LookupError('Missing source revenue collection')
    total=Decimal(0)
    for line in normalize_collection(lines):
        raw=line_value(line,'code','revenueCode','revCntrCd','REV-CNTR-CD')
        if raw is None: raise LookupError('Missing revenue code')
        code=int(raw)
        if low <= code <= high:
            value=line_value(line,'charges','amount','totalCharge','charge','revCntrTotChrgAmt','REV-CNTR-TOT-CHRG-AMT','totalAmount')
            if value is None: raise LookupError('Missing total charge for revenue code '+str(raw))
            total+=to_decimal(value)
    return whole_dollars(total) if round_result else total


def sum_line_field(lines, resolver, field):
    if lines is None:raise LookupError('Missing revenue collection for '+field)
    values=[]
    for line in normalize_collection(lines):
        value=resolver.get(line,field)
        if value is None:raise LookupError('Missing revenue operand: '+field)
        values.append(to_decimal(value))
    return whole_dollars(sum(values,Decimal(0)))


def covered_revenue(lines, resolver):
    if lines is None:raise LookupError('Missing revenue collection')
    total=Decimal(0)
    for line in normalize_collection(lines):
        charge=line_value(line,'charges','amount','totalCharge','charge','revCntrTotChrgAmt','REV-CNTR-TOT-CHRG-AMT','totalAmount')
        noncovered=resolver.get(line,'rev_cntr_ncvr_chrg_amt')
        if charge is None or noncovered is None:raise LookupError('Covered-charge calculation requires total and non-covered charges on every revenue line')
        total+=to_decimal(charge)-to_decimal(noncovered)
    return whole_dollars(total)
