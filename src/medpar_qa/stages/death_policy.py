"""Shared, explicit claims-coverage policy for death dates (QA-REG-03).

A missing cut-off is never replaced with the execution date. Cached BIC API
matches require an approved cut-off; historical source dates remain usable.
"""
from dataclasses import dataclass
from datetime import date
from medpar_qa.normalization.dates import is_missing_date, parse_date


def cutoff_options(raw):
    value = raw.get('dod_data_cutoff_date')
    cutoff = parse_date(value, allow_none=False).isoformat() if value is not None else None
    inclusive = raw.get('dod_cutoff_inclusive', True)
    if type(inclusive) is not bool:
        raise ValueError('dod_cutoff_inclusive must be true or false')
    return dict(dod_data_cutoff_date=cutoff, dod_cutoff_inclusive=inclusive, bic_verification_mapping=raw.get('bic_verification_mapping'))


@dataclass(frozen=True)
class DeathEvidence:
    death: date | None
    verification: object
    raw_date: object
    ignored_after_cutoff: bool
    cutoff: date | None


def effective_death(data, resolver, *, dod_data_cutoff_date=None, dod_cutoff_inclusive=True, bic_verification_mapping=None):
    get = lambda name: resolver.get(data, name)
    cached = get('cacheDataInternal')
    bic = isinstance(cached, dict) and any('death' in str(k).lower() or str(k).lower() == 'bic_api_match_found' for k in cached)
    available = bool(get('dod_reference_available')) or bic
    match_flag = resolver.get(cached, 'bic_api_match_found') if isinstance(cached, dict) else None
    raw = get('matched_date_of_death') if available else get('date_of_death')
    cutoff = parse_date(dod_data_cutoff_date, allow_none=False) if dod_data_cutoff_date is not None else None
    matched = match_flag not in (False, 0, '0', 'N', 'false', 'False')
    death = parse_date(raw, allow_none=False) if matched and not is_missing_date(raw) else None
    if bic and death is not None and cutoff is None:
        raise LookupError('Approved dod_data_cutoff_date is required for cached BIC death dates; execution date is not a substitute')
    ignored = bool(death is not None and cutoff is not None and (death > cutoff or (death == cutoff and not dod_cutoff_inclusive)))
    if ignored:
        death = None
    if death is not None:
        verify = get('matched_dod_verify_switch') if available else get('dod_verify_switch')
        if bic:
            mapping = {'Y': 'V', 'N': ' ', '': ' '}
            if bic_verification_mapping is not None:
                mapping.update(bic_verification_mapping)
            key = '' if verify is None else str(verify).strip()
            if key not in mapping:
                raise ValueError(f'Unmapped BIC isDeathDateVerified value: {verify!r}')
            verify = mapping[key]
        return DeathEvidence(death, verify, raw, ignored, cutoff)
    status = str(get('discharge_status') or get('patientStatus') or '').strip()
    if status in ('20', 'B'):
        return DeathEvidence(parse_date(get('stay_thru_date'), allow_none=False), 'B', raw, ignored, cutoff)
    if available or ignored:
        return DeathEvidence(None, None, raw, ignored, cutoff)
    raise LookupError('DOD requires reference evidence; absent source date is not a confirmed no-match')


def warning08_death_bit(original, death, admission):
    """Preserve duplicate bit while deriving death bit from the effective DOD."""
    if str(original) not in ('0', '1', '2', '3'):
        raise ValueError('Warning 08 must be one of 0, 1, 2, 3')
    return str(int(original) % 2 + 2 * int(death is not None and death < admission))
