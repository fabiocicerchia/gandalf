# gandalf mdl style — markdown lint is cosmetic (the gate caps it at WARN), so we
# keep structural rules and drop the purely-stylistic ones that fire en masse on
# prose, skill docs, and generated files.
all
exclude_rule 'MD013'  # line length — prose/skill docs use long lines by design
exclude_rule 'MD033'  # inline HTML — needed in skill docs/templates
exclude_rule 'MD034'  # bare URLs
exclude_rule 'MD024'  # duplicate headers (chat logs, templates)
exclude_rule 'MD029'  # ordered-list numbering style
exclude_rule 'MD022'  # blank lines around headers — cosmetic, dense docs by design
exclude_rule 'MD031'  # blank lines around fenced code — cosmetic
exclude_rule 'MD032'  # blank lines around lists — cosmetic
exclude_rule 'MD040'  # language on fenced code — not all snippets have one
exclude_rule 'MD007'  # unordered-list indent width — cosmetic
exclude_rule 'MD041'  # first line top-level header — false-positive on frontmatter
exclude_rule 'MD025'  # single H1 — false-positive on frontmatter'd skill docs
