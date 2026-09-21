# Application-rate presets — research and design

21 September 2026. Owner direction: retain direct entry of application rate
(mm/hour) and application efficiency (%), and also offer common equipment types
to simplify setup. The owner's installation includes individual drippers,
spot mini-sprinklers, perforated lines and drip/soaker hose. Exact products are
not yet identified. This document records sources and a proposed UI/data design;
it does not install presets or select calibration for any valve.

## Sources inspected

| Source | Relevant evidence | Scope |
| --- | --- | --- |
| [Texas A&M, Turf Irrigation and Nutrient Management](https://irrigation.tamu.edu/wp-content/uploads/sites/3/2021/06/Turf-Irrigation-Manual.pdf), printed p. 6 | Identifies manufacturer specifications, catch-can tests and meter readings as methods for determining station precipitation rate. | Supports estimated as well as measured input; does not supply a universal rate for all products of a type. |
| [Utah State University, Drip Irrigation for Trees](https://extension.usu.edu/forestry/trees-cities-towns/tree-care/drip-irrigation) | Describes drip efficiency of 85–90%, calculates demand using plant area, and treats emitter flow and coverage separately. | A useful initial efficiency range; not a measurement of the owner's system. |
| [USU-hosted Intermountain Tree Fruit Production Guide, irrigation chapter](https://extension.usu.edu/planthealth/ipm/files/pdfs/IntermountainTFG-2020.pdf#page=169) | Gives 70–90% efficiency for well-designed micro-sprinkler or drip systems, and 60–75% for overhead sprinklers. | Orchard guidance; possible support for labelled starting estimates, not precise household equipment ratings. |
| [Rain Bird, Low-Volume Landscape Irrigation Design Manual](https://www.rainbird.com/sites/default/files/media/documents/2018-02/LowVolumeGuide.pdf#page=50), printed p. 44 | Calculates gross application rate from emitter flow, emitter spacing and lateral spacing; Table 6-1 gives example layouts. Efficiency is applied separately. | Manufacturer formulas/layout examples, particularly useful for dripline presets. The manual is historical; verify current model ratings before adding named products. |
| [Rain Bird XFD0612100 product page](https://store.rainbird.com/xfd0612100-xf-dripline-0-6-gph-12-in-spacing-100-ft-coil.html) | Identifies a specific 0.6 US gallon/hour, 12-inch emitter-spacing dripline. | A candidate product preset; installed row spacing and operating conditions remain relevant. Not identified as the owner's hose. |
| [Gardena soaker-hose technical information](https://help.gardena.com/hc/de/articles/4450468161948-Welche-technischen-Daten-hat-der-Perlregner) | Gives output per metre for its product and notes unequal flow from beginning to end. | Product-specific porous-hose evidence; not a generic dripline or universal hose rating. |

Application efficiency in our model is the fraction of gross applied water
credited to the modeled root-zone balance. Do not substitute distribution
uniformity directly or copy another controller's differently defined
“efficiency” calculation without checking its meaning.

## Proposed controls

Keep the existing rate and efficiency fields visible and editable. Add a
helper for selecting equipment, using existing OpenSprinkler form controls.

| Choice | How to obtain gross application rate |
| --- | --- |
| Custom / direct entry | Enter mm/hour and efficiency directly. Direct entry may be measured or estimated; it must not automatically be labelled measured. |
| Inline dripline / drip tape | Choose a rated emitter or product, then enter emitter spacing and spacing between parallel runs. A fully specified layout preset can fill all three, with its assumptions visible. |
| Individual drippers | Rated flow × emitter count ÷ the represented area, for a reasonably consistent zone. |
| Mini-sprinklers / micro-sprays | Product precipitation rate at its specified layout/pressure, or total flow divided by represented area. No universal mm/hour value for “mini-sprinkler.” |
| Porous soaker hose | Product-rated flow per metre × installed length ÷ represented area. Do not treat porous hose as an array of identical regulated emitters. |
| Perforated spray hose | Product flow/coverage information; do not assume perforations are pressure-compensating drippers. |

For a uniform dripline grid, with metric inputs:

```
gross application rate (mm/hour) =
    emitter flow (L/hour) / [emitter spacing (m) × row spacing (m)]
```

For a known total flow, `mm/hour = L/hour ÷ m²`. The area must be consistent
with the area represented by crop demand and soil storage, rather than chosen
only to produce a convenient runtime. Sparse planting geometry remains a
modeling issue to resolve; a small visible wet spot is not automatically the
correct demand area. A single average cannot correct severely unequal delivery
within one valve's zone.

A concrete preset example from Rain Bird's layout table is 0.6 GPH emitters on
a 12-inch by 12-inch grid: about 24.4 mm/hour gross. The same nominal flow on
an 18-inch by 18-inch grid gives about 10.9 mm/hour. This illustrates why the
layout must be part of a complete preset. These are examples, not recommended
values for the owner's garden.

## Starting efficiency estimates

Proposed initial choices for evaluation, not owner-selected calibration:

- Rated drip emitters/dripline: 85%, the lower end of the USU tree-drip range.
- Mini-sprinklers: 80%, within the cited micro-irrigation range, explicitly
  labelled an estimate extrapolated from broader guidance.
- Porous/perforated hose: leave the assumption explicit and editable; do not
  assign the drip-emitter efficiency merely because the product is a hose.

A preset describes hardware and installation assumptions; university guidance
supports an initial efficiency estimate. Neither proves actual performance.
The owner can start with an estimate and later refine it with observations or
measurement. An unknown/blank rate still blocks planning; a valid explicit
estimate need not be rejected merely because it has not been measured.

## Data and behavior to preserve

- Selecting or browsing a preset should not silently overwrite a calibrated
  value. Preview the resulting rate/efficiency and apply explicitly to the form.
- Preserve an editable numeric rate and efficiency as the engine inputs. Apply
  efficiency once; never store an efficiency-adjusted rate and then apply the
  same efficiency a second time.
- Save the selected type/product, catalog version, geometry, source and whether
  the values are estimated, measured or manually overridden. This metadata
  needs a deliberate extension to the strict draft/engine contract; the current
  v1 adapter rejects unknown properties.
- Reopening a program should explain where its values came from. Updating the
  catalog must not silently alter existing programs.
- Keep equipment calibration per valve/program, separate from the common
  garden soil/plant profile and from the existing HTTP station type.
- Validate unit conversions, geometry, manual overrides and save/reopen/export
  against the offline engine before deployment. No production defaults are
  selected by this research note.
