# Structured visual details

Design Profile **0.3** adds regional appearance and media composition, and extends
geometry with visibility and separate full-element estimates. Profiles 0.1 and
0.2 remain readable with their original contracts. DNA schema remains 0.1; the new
feature vocabulary is **0.5**, with older vocabularies still accepted.
Rendering policy is **0.3**, with explicit coordinate-frame and estimate wording.

A complete [synthetic profile](../examples/design/visual-details-profile.json)
demonstrates all three extensions. Its values are illustrative, not a visual
accuracy benchmark.

```sh
visparse analyze-design viewport.png --intent preserve --estimate-geometry \
  --geometry-region lower-left-tile \
  --appearance-region hero-headline --appearance-region navigation \
  --media-region hero-photo > profile.json
visparse design-normalize profile.json > dna.json
visparse design-render dna.json --intent preserve --mode full > DESIGN.md
```

The Python options are `CodexDesignAnalyzer(appearance_regions=("hero-headline",
"navigation"), media_regions=("hero-photo",), estimate_geometry=True,
geometry_regions=("lower-left-tile",), intent="preserve")`.

Each repeatable region option requires exactly one corresponding interpretation
**per supplied image**, including targets. Missing regions need explicit unknowns,
not invented properties. Requests use unique neutral lowercase names, at most 32
per option. Appearance can be requested independently. Media composition requires
`estimate_geometry=True`, which also declares complete single-viewport input for
viewport geometry. Additional supported regions may be returned; requests are
coverage requirements, not proof that the named objects exist.

## Shared evidence contract

Each interpretation has the existing `id`, `observation_ids`, `category`,
`statement`, and `confidence_id`, and at most one structured extension. It must
cite observations from exactly one image. Extension type, image, and region
identify a unique record. Geometry uses category `layout`, appearance uses
`typography` or `color_usage`, and media uses `imagery_media`.

Every property or bound is a qualified value:

```json
{"value": null, "uncertainty": "The cookie notice hides the lower edge."}
```

Known values also require uncertainty text. Confidence comes from the linked
interpretation, so it should conservatively cover all its claims. Normalization
preserves that confidence, its source assessment, each value's uncertainty, and
source identity. All projected values are **inferred**, including hex colors;
this adapter does not sample pixels or recover original CSS. Null becomes an
unknown DNA feature, never zero. Target evidence is excluded from reference DNA.

## Regional appearance

An `appearance` object contains `region` and `properties`. All nine properties
are required; non-text, obscured, mixed, or unsupported properties use null and a
reason.

| Property | Known value | DNA feature |
| --- | --- | --- |
| `foreground` | Lowercase six-digit hex | `color.foreground_hex` |
| `background` | Lowercase six-digit hex | `color.background_hex` |
| `accent` | Lowercase six-digit hex | `color.accent_hex` |
| `font_weight` | Visual estimate, 1–1000 | `typography.font_weight` |
| `width_style` | `condensed`, `normal`, `wide` | `typography.width_style` |
| `line_count` | Positive integer | `typography.line_count` |
| `letter_spacing_em` | Finite signed number, relative to font size | `typography.letter_spacing_em` |
| `line_height_factor` | Positive font-size multiplier | `typography.line_height_factor` |
| `text_layout` | `single-block`, `multiple-blocks`, `non-text` | `typography.text_layout` |

A known `line_count` requires `single-block`. Multiple independent navigation
labels, quest items, or counters cannot be added up as one text block's line count;
use null and a reason. For `non-text`, all typography properties except
`text_layout` must be null. Distinct text blocks can have their own regional
appearance records.

Text block width can be requested separately through geometry for the same region.
These estimates cannot identify an original font or establish exact CSS values.
Gradients and textured surfaces should use unknown colors unless a representative
estimate is supported and explicitly qualified.

## Visible and full bounds

The existing `geometry.bounds` always describes the **visible fragment** in
viewport ratios. Its four qualified axes are `x`, `y`, `width`, `height`; known
values fit inside 0–1, extents are positive, and offset plus extent cannot exceed 1.
This meaning also applies when reading older profiles.

Profile 0.3 allows two additional fields:

- `visibility`: a qualified `fully-visible`, `occluded`, `clipped`,
  `occluded-and-clipped`, or null value.
- `full_bounds`: the same four qualified axes, for a separately supported estimate
  of the whole element. It requires an explicit visibility assessment. It uses the
  **same viewport frame**, so offsets may be negative and values may exceed 1.
  Known full bounds must contain known visible bounds. For a fully visible element,
  known full and visible values must agree.

Unsupported hidden extent stays null. Omission of `full_bounds` does not assert
that the visible fragment is the whole element. Normalization emits separate
`geometry.viewport_*_ratio` and `geometry.full_viewport_*_ratio` features plus
`geometry.visibility` when supplied. Rendering explicitly identifies the two
meanings, including in the generation-safe export.

## Composition inside media

A `media` object identifies its enclosing `region`, declares
`coordinate_space: "media-ratio"`, and includes qualified `coverage` and a
`subjects` array of at most 32 objects. Coverage is `complete`, `partial`, or null;
it describes the inventory of important visible subjects, not every pixel/object.
Missing or unidentifiable media uses empty subjects and unknown coverage with a
reason.

Each subject has a unique neutral `region` within that media, plus:

- `kind`: qualified `person`, `people-group`, `character`, `table`, `furniture`,
  `product`, `vehicle`, `plant`, `background-region`, `other`, or null.
- `bounds`: four qualified axes for the visible subject. Normalize against the
  **visible enclosing media rectangle**, with its top-left as origin. Values fit
  inside 0–1 with positive extents. These are neither viewport coordinates nor
  coordinates in the uncropped original asset.
- `visibility`: the same qualified categories as geometry.
- `crop`: qualified `none`, `left`, `right`, `top`, `bottom`, `multiple`, or null.
  Cropping describes cuts at media edges; occlusion describes another object
  hiding the subject. Contradictory visibility/crop claims are rejected.

Normalization creates subject evidence scoped as `media/<media-region>/<subject>`
and retains the enclosing evidence link and frame. Features
`imagery.subject_{x,y,width,height}_ratio`, `imagery.subject_visibility`,
`imagery.subject_crop`, and `imagery.subject_kind` require `relative_to` naming the
enclosing media region. `imagery.composition_coverage` belongs to the media itself.
Identical subject names inside different media stay distinct. Controlled subject
kinds survive generation-safe scope aliasing, so consumers retain the difference
between, for example, a table and a group of people.

`design-coverage` audits these features with their enclosing region. Compare
media-local claims through `design-compare`; `eval-analysis` currently has no
relationship-target field and rejects them rather than dropping the frame.

## Output and limits

Normalization directly projects these fields; semantic extraction is told which
features are already mapped. `DESIGN.md` explains frames, units, and estimated
colors, and filters low-confidence claims as before. Full rendering includes
uncertainty and evidence; generation-safe rendering omits free text but retains
controlled values, unknown/conflict gaps, and frame explanations.

Validation establishes structure and consistency, not visual accuracy. The
analyzer may still misidentify regions, estimate an edge poorly, or return invalid
output. These changes do not alter the external generator, verify that generated
code follows the guidance, obtain original assets, or establish mobile behavior
from a desktop screenshot. Generator suggestions remain in the separate
[transfer notes](transfer-improvement-notes.md).
