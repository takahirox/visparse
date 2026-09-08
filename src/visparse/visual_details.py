"""Structured visual estimates; no pixel sampling or model execution."""
import re

from .contracts import check, items, number, shape
from .geometry import VISIBILITY, validate_bounds, validate_qualified, validate_region

# field: (DNA feature, kind, controlled values, tolerance)
APPEARANCE = {
    'foreground': ('color.foreground_hex', 'color', None, 0),
    'background': ('color.background_hex', 'color', None, 0),
    'accent': ('color.accent_hex', 'color', None, 0),
    'font_weight': ('typography.font_weight', 'number', None, 100),
    'width_style': ('typography.width_style', 'enum', ['condensed', 'normal', 'wide'], 0),
    'line_count': ('typography.line_count', 'count', None, 0),
    'letter_spacing_em': ('typography.letter_spacing_em', 'em', None, 0.02),
    'line_height_factor': ('typography.line_height_factor', 'ratio', None, 0.1),
    'text_layout': ('typography.text_layout', 'enum', ['single-block', 'multiple-blocks', 'non-text'], 0),
}
CROP = ['none', 'left', 'right', 'top', 'bottom', 'multiple']
SUBJECT_KINDS = ['person', 'people-group', 'character', 'table', 'furniture', 'product',
                 'vehicle', 'plant', 'background-region', 'other']


def validate_appearance(value):
    shape(value, {'region', 'properties'})
    validate_region(value['region'])
    shape(value['properties'], set(APPEARANCE))
    for field, (_, kind, choices, _) in APPEARANCE.items():
        estimate = value['properties'][field]
        validate_qualified(estimate, choices)
        v = estimate['value']
        if v is None:
            continue
        if kind == 'color':
            check(isinstance(v, str) and re.fullmatch(r'#[0-9a-f]{6}', v) is not None,
                  'expected lowercase six-digit hex color')
        elif kind != 'enum':
            number(v)
            if field == 'font_weight':
                number(v, 1, 1000)
            elif field == 'line_count':
                check(type(v) is int and v >= 1, 'expected positive integer line count')
            elif field == 'line_height_factor':
                check(v > 0, 'line height factor must be positive')
    properties = value['properties']
    layout = properties['text_layout']['value']
    check(properties['line_count']['value'] is None or layout == 'single-block',
          'line count requires a single text block; do not count independent labels')
    if layout == 'non-text':
        check(all(properties[k]['value'] is None for k in
                  ('font_weight', 'width_style', 'line_count', 'letter_spacing_em', 'line_height_factor')),
              'non-text regions cannot claim typography values')


def validate_media(value):
    shape(value, {'region', 'coordinate_space', 'coverage', 'subjects'})
    validate_region(value['region'])
    check(value['coordinate_space'] == 'media-ratio', 'media composition requires media-ratio coordinates')
    validate_qualified(value['coverage'], ['complete', 'partial'])
    subjects = items(value['subjects'])
    check(len(subjects) <= 32, 'at most 32 media subjects')
    seen = set()
    for subject in subjects:
        shape(subject, {'region', 'kind', 'bounds', 'visibility', 'crop'})
        validate_region(subject['region'])
        check(subject['region'] not in seen, 'duplicate media subject')
        seen.add(subject['region'])
        validate_qualified(subject['kind'], SUBJECT_KINDS)
        validate_bounds(subject['bounds'])
        validate_qualified(subject['visibility'], VISIBILITY)
        validate_qualified(subject['crop'], CROP)
        visibility, crop = subject['visibility']['value'], subject['crop']['value']
        check(visibility not in ('fully-visible', 'occluded') or crop in (None, 'none'),
              'unclipped subject cannot have cropped edges')
        check(visibility not in ('clipped', 'occluded-and-clipped') or crop != 'none',
              'clipped subject cannot claim no cropped edges')


def detail_prompt(appearance_regions, media_regions):
    return (
        'Structured visual details: use separate interpretations for geometry, appearance, and media. '
        'Each links observations from exactly one image; use neutral region identifiers. '
        'For clearly identifiable regions, especially in preserve mode, provide appearance on a typography '
        'or color_usage interpretation: {region:neutral-id,properties:{FIELD:{value:VALUE-or-null,uncertainty:text}}}. '
        f'Include ALL appearance fields from this specification: {APPEARANCE!r}; tuples describe '
        '(DNA feature, value kind, allowed enum values, comparison tolerance). '
        'Colors are approximate lowercase six-digit hex estimates of visible regional foreground, background, '
        'and accent, never sampled pixels or recovered CSS. For gradients/textures or mixed styles use null '
        'unless a representative value is supported and qualified. Font weight is a visual estimate in 1..1000; '
        'do not claim to identify the original font. Letter spacing uses em, line height a font-size multiplier. '
        'Classify text_layout as single-block, multiple-blocks, non-text, or null. A known line_count is allowed '
        'ONLY for single-block text: never add independent navigation labels, quest items or counters together. '
        'For multiple blocks use null line_count and request/describe smaller text regions when useful. '
        'For non-text regions all typography properties other than text_layout must be null. '
        'Use null with a concrete reason for non-text regions, invisible or indeterminate properties. '
        'Text block dimensions belong in separately requested geometry, not invented font metrics. '
        f'For EVERY image return exactly one appearance record for each requested region: {list(appearance_regions)!r}, '
        'including explicit unknown properties for missing regions. Additional supported appearance regions are allowed. '
        'When geometry estimation is enabled, describe important subjects inside media with an imagery_media interpretation '
        'containing media: {region:enclosing-media-id,coordinate_space:"media-ratio",'
        'coverage:{value:"complete"|"partial"|null,uncertainty:text},subjects:['
        '{region:neutral-subject-id,kind:{value:category-or-null,uncertainty:text},bounds:{x:{value:number-or-null,uncertainty:text},'
        'y:{value:number-or-null,uncertainty:text},width:{value:number-or-null,uncertainty:text},'
        'height:{value:number-or-null,uncertainty:text}},visibility:{value:category-or-null,uncertainty:text},'
        'crop:{value:category-or-null,uncertainty:text}}]}. '
        f'Subject kind categories: {SUBJECT_KINDS!r}; visibility categories: {VISIBILITY!r}; crop categories: {CROP!r}. '
        'Coordinates describe only the visible subject inside the visible enclosing media rectangle: '
        'top-left origin, x/width divided by media width, y/height by media height, all in 0..1; '
        'extents positive and x+width/y+height <=1. They are NOT viewport ratios or original asset coordinates. '
        'Crop means cutting at media edges, whereas occlusion means another object hides part of a subject. '
        'Do not reconstruct hidden subjects. Give partial/unknown coverage with a reason when visibility is limited. '
        f'For EVERY image return exactly one media record for each requested enclosing region: {list(media_regions)!r}. '
        'Missing or unidentifiable media uses empty subjects and null coverage with a reason, not invented subjects. '
        'Additional supported media regions are allowed only when geometry estimation is enabled. '
        'All these values remain interpretations with confidence and uncertainty, never measurements. '
    )
