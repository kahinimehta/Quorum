"""
Evidence Scoring Agent / Skeptic Agent

Purpose:
Scores strength of evidence for each subgroup-treatment connection.

The repo uses final confidence:
confidence = evidence_strength * 0.55 + commercial_potential * 0.45

This agent only calculates evidence_strength.
"""

from typing import Any, Dict, List


class EvidenceScoringAgent:
    name = "Evidence Scoring Agent"

    def run(
        self,
        treatment_output: Dict[str, Any],
        evidence_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        scored_connections = []

        for connection in treatment_output.get("connections", []):
            subgroup = connection.get("subgroup")
            evidence_count = connection.get("evidence_count", 0)
            evidence_sources = connection.get("evidence_sources", [])

            matching_rows = [
                row for row in evidence_rows
                if row.get("subgroup") == subgroup
            ]

            evidence_strength = self._score_evidence_strength(
                evidence_count=evidence_count,
                matching_rows=matching_rows
            )

            skeptic_notes = self._make_skeptic_notes(
                evidence_strength=evidence_strength,
                evidence_count=evidence_count,
                matching_rows=matching_rows
            )

            scored = {
                **connection,
                "evidence_strength": evidence_strength,
                "skeptic_notes": skeptic_notes,
                "evidence_sources": evidence_sources
            }

            scored_connections.append(scored)

        scored_connections = sorted(
            scored_connections,
            key=lambda item: item["evidence_strength"],
            reverse=True
        )

        return {
            "agent": self.name,
            "scored_connections": scored_connections,
            "summary": f"Scored {len(scored_connections)} treatment connections for evidence strength."
        }

    @staticmethod
    def _score_evidence_strength(
        evidence_count: int,
        matching_rows: List[Dict[str, Any]]
    ) -> float:
        score = 5.0

        source_types = {
            row.get("source_type")
            for row in matching_rows
            if row.get("source_type")
        }

        has_literature = "literature" in source_types
        has_trial = "trial" in source_types
        has_grant = "grant" in source_types

        if evidence_count >= 3:
            score += 1.0
        if evidence_count >= 8:
            score += 1.0
        if has_literature:
            score += 0.8
        if has_trial:
            score += 1.0
        if has_grant:
            score += 0.5

        return round(min(score, 10.0), 1)

    @staticmethod
    def _make_skeptic_notes(
        evidence_strength: float,
        evidence_count: int,
        matching_rows: List[Dict[str, Any]]
    ) -> List[str]:
        notes = []

        if evidence_count < 3:
            notes.append("Limited number of supporting evidence rows.")
        else:
            notes.append("Multiple evidence rows support this connection.")

        source_types = {
            row.get("source_type")
            for row in matching_rows
            if row.get("source_type")
        }

        if "trial" in source_types:
            notes.append("Clinical trial evidence is present.")
        else:
            notes.append("Clinical trial evidence may need deeper validation.")

        if evidence_strength >= 8:
            notes.append("Evidence strength is high enough for prioritization review.")
        elif evidence_strength >= 6.5:
            notes.append("Evidence is moderate; monitor or validate further.")
        else:
            notes.append("Evidence is early or weak; use caution.")

        return notes