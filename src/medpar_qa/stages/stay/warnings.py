"""V3 p24 Stay warnings 06/08 derived from input bills, never from target flags."""
from collections import Counter
from medpar_qa.normalization.dates import parse_date


def warning06(records, resolver):
    """Latest qualifying cancellation wins; its reason overrides its action code."""
    ordered = sorted(records, key=lambda r: (
        parse_date(resolver.get(r.data, 'processing_date'), allow_none=True),
        parse_date(resolver.get(r.data, 'accrete_date'), allow_none=True),
        int(resolver.get(r.data, 'query_code') or 0)), reverse=True)
    reasons = {'C': '3', 'P': '4', 'S': '5', 'D': '6', 'H': '7', 'L': '8'}
    actions = {'2': '1', '6': '1', '4': '2'}
    for record in ordered:
        reason = str(resolver.get(record.data, 'cancel_reason_code') or '').strip().upper()
        action = str(resolver.get(record.data, 'action_code') or '').strip()
        if reason in reasons:
            return reasons[reason]
        if action in actions:
            return actions[action]
    return '0'


def warning08(records, resolver, **death_options):
    """Duplicate bill identity and death before admission combine into a two-bit warning."""
    fields = ('hicn', 'admission_date', 'provider_id', 'stay_from_date', 'stay_thru_date', 'processing_date', 'query_code')
    identities = []
    death_before = False
    for record in records:
        values = []
        for field in fields:
            value = resolver.get(record.data, field)
            if value in (None, ''):
                raise LookupError(f'Warning 08 missing duplicate-identity operand: {field}')
            values.append(parse_date(value).isoformat() if field.endswith('_date') else str(value).strip())
        identities.append(tuple(values))
        from medpar_qa.stages.death_policy import effective_death
        try:
            death = effective_death(record.data, resolver, **death_options).death
        except LookupError:
            if death_options or isinstance(resolver.get(record.data, 'cacheDataInternal'), dict):
                raise
            death = None  # Existing warning-only inputs need not have an EDB match.
        if death is not None:
            death_before |= death < parse_date(resolver.get(record.data, 'admission_date'))
    duplicate = any(count > 1 for count in Counter(identities).values())
    return str(int(duplicate) + 2 * int(death_before))
