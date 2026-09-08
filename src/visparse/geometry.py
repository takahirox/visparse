"""Contracts for qualified, model-estimated visible viewport bounds."""
from __future__ import annotations

import re
from .contracts import check, number, shape, text

AXES = ('x', 'y', 'width', 'height')
REGION_PATTERN = r'[a-z][a-z0-9-]{0,63}'


def validate_geometry(value: dict) -> None:
    shape(value, {'region', 'coordinate_space', 'bounds'})
    check(isinstance(value['region'], str) and re.fullmatch(REGION_PATTERN, value['region']) is not None,
          'geometry region must be a neutral lowercase identifier')
    check(value['coordinate_space'] == 'viewport-ratio', 'geometry requires viewport-ratio coordinates')
    shape(value['bounds'], set(AXES))
    for axis in AXES:
        bound = value['bounds'][axis]
        shape(bound, {'value', 'uncertainty'})
        text(bound['uncertainty'])
        if bound['value'] is not None:
            number(bound['value'], 0, 1)
            if axis in ('width', 'height'):
                check(bound['value'] > 0, 'visible geometry extent must be positive or unknown')
    for offset, extent in (('x', 'width'), ('y', 'height')):
        a, b = (value['bounds'][axis]['value'] for axis in (offset, extent))
        check(a is None or b is None or a + b <= 1 + 1e-9,
              'visible geometry bounds extend beyond the viewport')


def validate_region_requests(regions, estimate_geometry: bool) -> None:
    check(isinstance(regions, (list, tuple)) and len(regions) <= 32,
          'geometry_regions must be a list or tuple of at most 32 region names')
    check(not regions or estimate_geometry, 'geometry region requests require estimate_geometry')
    for region in regions:
        check(isinstance(region, str) and re.fullmatch(REGION_PATTERN, region) is not None,
              'invalid requested geometry region')
    check(len(set(regions)) == len(regions), 'duplicate requested geometry region')
