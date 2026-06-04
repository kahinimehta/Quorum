"""cua.nih — the NIH-grant binding of the engine.

The ONLY place domain nouns live (CONVENTIONS rule 1 / design §2 'Design rule'): Proposal, aim,
factor, citation, the NIH rubric. Everything here is one `Task` instantiation of the generic engine
(`cua` minus this package). Owner: builder 1 (S2 type skeletons + stub roles; S4/S5 real roles).

Kept import-light on purpose: `framework` (imported by the fixtures) pulls only `cua.types`, so the
test-data layer stays free of the LLM/runtime stack.
"""
