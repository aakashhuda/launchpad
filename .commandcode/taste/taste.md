# General

- Prefers enum-like domain fields (statuses, roles, channels, report reasons, etc.) modeled as first-class Python `enum.Enum` classes in the ORM rather than as plain strings guarded only by raw CHECK constraints. Confidence: 0.8
