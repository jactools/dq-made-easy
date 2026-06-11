# Catalog Term Comparison Words

This note records the catalog-term matching behavior for rule draft search.

Comparison and threshold phrases such as `lower than`, `less than`, `under`, `below`, `between`, `equal`, `max`, and `at least` are treated as DQ comparison noise when scoring business-term matches.

The matcher also normalizes `percentage` to `percent`, so prompts like `a percentage must be lower than 10%` still match `discount_percent` instead of dropping out as the prompt grows.

The match list shows the score directly as `Match score: NN%` to make the ranking visible in the UI.