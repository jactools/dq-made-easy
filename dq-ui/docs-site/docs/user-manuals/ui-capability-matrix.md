# UI Capability Matrix

**Time to read:** 4 minutes
**Last updated:** 2026-05-04

## Purpose
This card explains how the UI should present engine capability guidance when users author DQ Made Easy rules.

## What the UI should show

| UI element | Behavior |
| --- | --- |
| Engine selector | Let the author choose the target engine explicitly. Do not auto-switch engines. |
| Capability badge | Show `native`, `partial`, `sql`, `custom`, or `no` next to the selected rule family. |
| Supported subset list | Show the subsets that are valid for the chosen engine and rule family. |
| Fail-fast warning | Warn when the rule shape is outside the supported subset or unsupported entirely. |
| Example panel | Show a small example payload for the selected engine only. |
| Read-only assistant | Show implemented runtime guidance only. Today the assistant may show GX support rows and must omit planned SodaCL, SQL, PySpark, or custom-worker targets until those lowerers exist. |

## Recommended authoring flow

1. Pick the engine first.
2. Review the capability badge and supported subset list.
3. Narrow the rule shape until it fits the supported subset.
4. Submit the rule and let the compiler enforce the same contract again.

## If you prefer a wizard

The wizard should follow the same flow as the matrix. It can guide the user step by step, but it must still fail fast if the selected engine cannot preserve the rule semantics.

## What the UI must not do

- Do not silently switch a rule from GX to another backend.
- Do not hide unsupported subsets behind generic success states.
- Do not make the wizard the source of truth; the capability registry remains the source of truth.
- Do not present planned registry entries as implemented assistant support.

## Related cards

- [Engine Capability Guidance](/docs/user-manuals/engine-capability-guidance/)
- [GX Capability Guidance](/docs/user-manuals/gx-capability-guidance/)