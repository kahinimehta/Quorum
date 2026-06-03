"""
Patient Subgroup Agent

Purpose:
Reads evidence-like rows and identifies candidate patient subgroups.

Input:
List of dictionaries from the evidence table or backend query.
Expected fields may include:
- subgroup
- mechanism
- treatment
- source_id
- source_type
- title
- summary
"""

from collections import defaultdict
from typing import Any, Dict, List


class PatientSubgroupAgent:
    name = "Patient Subgroup Agent"

    def run(self, evidence_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        grouped = defaultdict(list)

        for row in evidence_rows:
            subgroup = row.get("subgroup")
            if subgroup:
                grouped[subgroup].append(row)

        subgroups = []

        for subgroup_name, rows in grouped.items():
            mechanisms = sorted({
                row.get("mechanism")
                for row in rows
                if row.get("mechanism")
            })

            treatments = sorted({
                row.get("treatment")
                for row in rows
                if row.get("treatment")
            })

            source_ids = sorted({
                row.get("source_id")
                for row in rows
                if row.get("source_id")
            })

            subgroups.append({
                "name": subgroup_name,
                "evidence_count": len(rows),
                "mechanisms": mechanisms,
                "treatments": treatments,
                "evidence_sources": source_ids,
                "rationale": self._make_rationale(
                    subgroup_name=subgroup_name,
                    mechanisms=mechanisms,
                    treatments=treatments,
                    evidence_count=len(rows)
                )
            })

        subgroups = sorted(
            subgroups,
            key=lambda item: item["evidence_count"],
            reverse=True
        )

        return {
            "agent": self.name,
            "subgroups": subgroups,
            "summary": f"Identified {len(subgroups)} candidate patient subgroups."
        }

    @staticmethod
    def _make_rationale(
        subgroup_name: str,
        mechanisms: List[str],
        treatments: List[str],
        evidence_count: int
    ) -> str:
        mechanism_text = ", ".join(mechanisms[:3]) if mechanisms else "available mechanism tags"
        treatment_text = ", ".join(treatments[:3]) if treatments else "potential treatment strategies"

        return (
            f"{subgroup_name} is supported by {evidence_count} evidence rows and is associated "
            f"with {mechanism_text}. Treatment-relevant signals include {treatment_text}."
        )