# Job: A visual judge that is hard to fool

The visual judge scores renders against a brief and a rubric with a vision-language model. Published evaluations put VLM-versus-human agreement on 3D assets at about 0.70 to 0.79 pairwise, report position bias and distraction by geometric noise, and show that text placed in an image inflates multimodal judges' scores. A payment judge needs a rubric protocol that resists this: judge-owned views, text detection, two models in both orders, and escalation when they disagree.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Judge-owned views:** the rubric sees only the judge's own fixed camera ring (six orthographic-and-oblique views by default, configurable up to 24) and close-ups, never images the asset supplies; lighting is fixed by the judge.
2. **Text and metadata scan:** OCR on every rubric image and on every texture image, and a scan of glTF strings (names, extras, URIs, copyright) for instruction-like or brief-like text; any hit is reported, removed from what the model sees where possible (texture text cannot be removed, so the rule then fails or escalates, stated), and recorded in the report.
3. **Two-model, two-order protocol:** each rubric criterion is scored by two different model families (or two independently prompted runs when only one family is available, stated), with any pairwise comparison asked in both orders; only order-consistent verdicts count; disagreement beyond a threshold marks the visual rule `uncertain`, which the spec maps to fail or to a committee escalation (documented with Solive's committee tools).
4. **Measured first:** the visual rule can never turn a measured fail into a pass; its weight in the verdict is documented.
5. **Calibration:** a small labelled set (Blendworks proof assets plus deliberately bad variants and text-in-texture attacks) with agreement numbers before and after the change.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Model calls in tests use a recorded fake provider; the live calibration run is opt-in and reported.

## Rules

- Follow `CONTRIBUTING.md`. OCR must be permissively licensed and run offline inside the sandbox (or the image), with its licence stated.
- **Allowed files:** `src/judge/visual/**`, `src/judge/**` where the visual rule is wired, `bridge/judge/**` for the view ring, `docker/judge/**` for the OCR dependency, `test/judge/**`, `docs/**`.
- **Files shared with other open jobs:** judge jobs run one at a time; this one starts after animation-quality lands.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the calibration set live once and sees the reported agreement, and sees a text-in-texture attack on a proof asset flagged and not rewarded.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
