"""Contracts for qualified, model-estimated visible viewport bounds."""
from __future__ import annotations

import re
from .contracts import check, number, shape, text

AXES = ('x', 'y', 'width', 'height')
REGION_PATTERN = r'[a-z][a-z0-9-]{0,63}'


VISIBILITY = ['fully-visible', 'occluded', 'clipped', 'occluded-and-clipped']


def validate_region(region) -> None:
    check(isinstance(region, str) and re.fullmatch(REGION_PATTERN, region) is not None,
          'geometry region must be a neutral lowercase identifier')


def validate_qualified(value, choices=None) -> None:
    shape(value, {'value', 'uncertainty'})
    text(value['uncertainty'])
    if choices is not None and value['value'] is not None:
        check(isinstance(value['value'], str) and value['value'] in choices, 'invalid qualified category')


def validate_bounds(bounds: dict, *, full: bool = False) -> None:
    shape(bounds, set(AXES))
    for axis in AXES:
        bound = bounds[axis]
        validate_qualified(bound)
        if bound['value'] is not None:
            number(bound['value'], None if full else 0, None if full else 1)
            if axis in ('width', 'height'):
                check(bound['value'] > 0, 'visible geometry extent must be positive or unknown')
    if not full:
        for offset, extent in (('x', 'width'), ('y', 'height')):
            a, b = (bounds[axis]['value'] for axis in (offset, extent))
            check(a is None or b is None or a + b <= 1 + 1e-9,
                  'visible geometry bounds extend beyond the viewport or media frame')


def validate_geometry(value: dict, *, extended: bool = False) -> None:
    shape(value, {'region', 'coordinate_space', 'bounds'}, {'visibility', 'full_bounds'} if extended else set())
    validate_region(value['region'])
    check(value['coordinate_space'] == 'viewport-ratio', 'geometry requires viewport-ratio coordinates')
    validate_bounds(value['bounds'])
    if 'visibility' in value:
        validate_qualified(value['visibility'], VISIBILITY)
    if 'full_bounds' in value:
        check('visibility' in value, 'full bounds require an explicit visibility assessment')
        validate_bounds(value['full_bounds'], full=True)
        # The inferred whole must contain the visible fragment when both are known.
        for offset, extent in (('x', 'width'), ('y', 'height')):
            v, size = (value['bounds'][a]['value'] for a in (offset, extent))
            f, total = (value['full_bounds'][a]['value'] for a in (offset, extent))
            check(v is None or f is None or f <= v + 1e-9, 'full bounds exclude visible start')
            check(size is None or total is None or total + 1e-9 >= size, 'full bounds smaller than visible extent')
            check(None in (v, size, f, total) or f + total + 1e-9 >= v + size,
                  'full bounds exclude visible end')
        if value['visibility']['value'] == 'fully-visible':
            for axis in AXES:
                v, f = value['bounds'][axis]['value'], value['full_bounds'][axis]['value']
                check(v is None or f is None or abs(v - f) <= 1e-9,
                      'fully-visible bounds disagree with full bounds')


def validate_region_requests(regions, estimate_geometry: bool) -> None:
    check(isinstance(regions, (list, tuple)) and len(regions) <= 32,
          'geometry_regions must be a list or tuple of at most 32 region names')
    check(not regions or estimate_geometry, 'geometry region requests require estimate_geometry')
    for region in regions:
        check(isinstance(region, str) and re.fullmatch(REGION_PATTERN, region) is not None,
              'invalid requested geometry region')
    check(len(set(regions)) == len(regions), 'duplicate requested geometry region')
