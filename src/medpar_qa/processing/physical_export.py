"""Encode only an explicitly supplied, complete physical layout; never infer offsets."""
from decimal import Decimal


def encode_record(data, resolver, layout, *, expected_bytes=3000, encoding='ascii'):
    """Use one-based positions with explicit filler, text or integer specifications.

    Full coverage is mandatory, including filler. No silent truncation, overlap,
    fractional integer conversion or replacement of missing values is allowed.
    """
    if not layout:
        raise ValueError('Approved MPRRECL field layout is required for physical export')
    output = bytearray(b' ' * expected_bytes)
    covered = set()
    for spec in layout:
        name = str(spec.get('name', 'unnamed'))
        start, length = int(spec['start']) - 1, int(spec['length'])
        positions = set(range(start, start + length))
        if start < 0 or length < 1 or start + length > expected_bytes:
            raise ValueError(f'{name}: byte range is outside the record')
        if covered & positions:
            raise ValueError(f'{name}: overlapping byte range')
        covered |= positions
        kind = spec.get('type', 'text')
        if kind == 'filler':
            value = spec.get('value', ' ')
            if len(str(value).encode(encoding)) != 1:
                raise ValueError(f'{name}: filler must encode to one byte')
            encoded = str(value).encode(encoding) * length
        else:
            value = resolver.get(data, name)
            if value is None:
                if 'default' not in spec:
                    raise ValueError(f'{name}: missing required layout value')
                value = spec['default']
            if isinstance(value, (dict, list)):
                raise ValueError(f'{name}: layout needs explicit occurrence fields')
            if kind == 'integer':
                number = Decimal(str(value))
                if not number.is_finite() or number != number.to_integral_value():
                    raise ValueError(f'{name}: expected whole integer')
                if number < 0:
                    raise ValueError(f'{name}: signed numeric encoding must be explicitly defined')
                text = str(int(number)).rjust(length, '0')
            elif kind == 'text':
                text = str(value).ljust(length, ' ')
            else:
                raise ValueError(f'{name}: unsupported layout type {kind}')
            encoded = text.encode(encoding)
            if len(encoded) != length:
                raise ValueError(f'{name}: value exceeds configured byte width')
        output[start:start + length] = encoded
    if len(covered) != expected_bytes:
        raise ValueError(f'Incomplete physical layout: {expected_bytes-len(covered)} byte positions undefined')
    return bytes(output).decode(encoding)
