# Transfer improvement notes

The current improvement focus is Visparse: extracting source evidence and
communicating it faithfully through Design Profile, Design DNA, and `DESIGN.md`.
The three items below are now supported by the [structured visual detail contracts](visual-details.md).
Their effect on visual fidelity still needs evaluation with fresh isolated generations.
Changes to the external generator are recorded only as future integration hints.

## Visparse improvements

1. **Region-specific color and typography.** Associate color, text width, weight,
   line count, and spacing with explicit regions. Distinguish mechanically sampled
   screenshot colors from visual estimates; neither establishes the original CSS
   declaration. Preserve confidence, uncertainty, and unknown values for inferred
   properties such as font family or weight.
2. **Visible bounds versus estimated full bounds.** Record whether geometry
   describes the visible portion, clipping, or an inferred whole element. An
   overlapping cookie notice can hide part of a content tile; the visible fragment
   should not silently become the tile's full size. Keep unobservable extent
   unknown unless an explicitly qualified estimate is supported.
3. **Composition within media.** Describe the relative position, scale, and crop
   of important subjects inside an image, such as people and a table. Identify the
   enclosing media region and coordinate frame so internal composition cannot be
   mistaken for viewport geometry. These descriptions help transfer composition;
   they do not supply the original photographic asset.

Evaluate these changes on
the same Kirka.io and Kraft Heinz references with the generator prompt and media
constraints held fixed. Check that extracted details survive normalization and
rendering, then compare isolated generation results. A single improved generation
does not establish that an analysis change caused the improvement.

## Future generator integration hints

These suggestions are outside the current Visparse implementation scope:

- Compare generated DOM bounds with supplied region geometry at the declared
  viewport. Report deviations and, in a future generator workflow, use them to
  guide corrections. Define matching regions and tolerances explicitly; inferred
  coordinates are approximate guidance, not exact source measurements.
- Check whether supplied regional color and typography guidance was followed.
  Separate missing analysis from supplied guidance that the implementation did
  not follow.
- Distinguish DOM boxes from visible artwork bounds. Transparent padding, text
  metrics, transforms, and cropping can make an element's box a poor proxy for
  its visible footprint.
- Treat asset availability as an independent constraint. The experiments used
  code-native artwork without external photos or fonts, so better analysis alone
  cannot remove every photographic or font difference.

In the September 8, 2026 cycle 3 Kraft Heinz experiment, the supplied wordmark
width estimate was 0.16 of a 1440-pixel viewport (about 230 pixels), while the
generated wordmark DOM width was about 165 pixels. This is evidence of a supplied
estimate not being followed, rather than an absent width estimate. It is not an
exact measurement of the source logo's visible pixels. Local experiment evidence
is retained under `artifacts/cycle-3-20260908/` in the per-case geometry reports,
layout measurements, and Japanese report.
