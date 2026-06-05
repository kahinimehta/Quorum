"""
Commercial Discovery Agent

Purpose:
Scores commercial attractiveness for each treatment connection and calculates final confidence.

Repo formula:
confidence = evidence_strength * 0.55 + commercial_potential * 0.45
"""

from typing import Any, Dict, List


class CommercialDiscoveryAgent:
    name = "Commercial Discovery Agent"

    def run(self, evidence_scoring_output: Dict[str, Any]) -> Dict[str, Any]:
        opportunities = []

        for connection in evidence_scoring_output.get("scored_connections", []):
            commercial_potential = self._score_commercial_potential(connection)
            evidence_strength = connection.get("evidence_strength", 0)

            confidence = round(
                evidence_strength * 0.55 + commercial_potential * 0.45,
                1
            )

            recommendation = self._classify_recommendation(confidence)

            opportunities.append({
                **connection,
                "commercial_potential": commercial_potential,
                "confidence": confidence,
                "recommendation": recommendation,
                "commercial_rationale": self._make_commercial_rationale(
                    connection=connection,
                    commercial_potential=commercial_potential
                )
            })

        opportunities = sorted(
            opportunities,
            key=lambda item: item["confidence"],
            reverse=True
        )

        return {
            "agent": self.name,
            "opportunities": opportunities,
            "top_recommendation": opportunities[0] if opportunities else None,
            "summary": f"Ranked {len(opportunities)} commercial discovery opportunities."
        }

    @staticmethod
    def _score_commercial_potential(connection: Dict[str, Any]) -> float:
        subgroup = str(connection.get("subgroup", "")).lower()
        mechanism = str(connection.get("mechanism", "")).lower()
        treatment = str(connection.get("treatment_strategy", "")).lower()
        evidence_count = connection.get("evidence_count", 0)

        score = 5.5 + min(2.5, evidence_count * 0.12)

        if "gba" in subgroup or "lrrk2" in subgroup:
            score += 0.9

        if "alpha" in mechanism or "synuclein" in mechanism:
            score += 0.6

        if "lysosomal" in mechanism or "kinase" in mechanism:
            score += 0.7

        if treatment:
            score += 0.6

        return round(min(score, 10.0), 1)

    @staticmethod
    def _classify_recommendation(confidence: float) -> str:
        if confidence >= 8.0:
            return "Prioritize"
        if confidence >= 6.5:
            return "Monitor"
        return "Reject"

    @staticmethod
    def _make_commercial_rationale(
        connection: Dict[str, Any],
        commercial_potential: float
    ) -> List[str]:
        subgroup = connection.get("subgroup", "This subgroup")
        mechanism = connection.get("mechanism", "the mechanism")
        treatment = connection.get("treatment_strategy", "the treatment strategy")

        rationale = [
            f"{subgroup} is clinically meaningful if it can be identified through biomarkers or progression features.",
            f"The mechanism, {mechanism}, creates a clear scientific rationale for intervention.",
            f"The treatment strategy, {treatment}, may represent a differentiated opportunity if evidence continues to support it."
        ]

        if commercial_potential >= 8:
            rationale.append("Commercial potential is high enough for prioritization review.")
        elif commercial_potential >= 6.5:
            rationale.append("Commercial potential is moderate and should be monitored.")
        else:
            rationale.append("Commercial potential is currently limited or uncertain.")

        return rationale