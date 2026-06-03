# Remaining Agents

This branch adds the downstream discovery agents for NeuroDiscover AI.

## Agents added

1. Patient Subgroup Agent  
2. Treatment Connection Agent  
3. Evidence Scoring / Skeptic Agent  
4. Commercial Discovery Agent  

## Purpose

These agents work downstream of the Literature Synthesis Agent. They consume evidence rows from the canonical `evidence` table and convert those rows into ranked subgroup-treatment opportunities.

## Input

Evidence rows may include:

- subgroup
- mechanism
- treatment
- source_id
- source_type
- title
- summary

## Output

The downstream agents produce:

- patient subgroups
- subgroup-treatment connections
- evidence strength scores
- commercial potential scores
- final confidence scores
- Prioritize / Monitor / Reject recommendations

## Scoring

The system uses the team formula:

```text
confidence = evidence_strength * 0.55 + commercial_potential * 0.45