"""adapters/ — NIH binding: input adapters that read an EXTERNAL source (read-only) and assemble the
`input_contract` the engine consumes. Pure input boundary — no role body, no eval, no engine spine.

Owner: INT-2 (builder 1). Domain nouns are legal here (binding layer, CONVENTIONS rule 1).
"""

from __future__ import annotations

from .neurodiscover import task_from_db

__all__ = ["task_from_db"]
