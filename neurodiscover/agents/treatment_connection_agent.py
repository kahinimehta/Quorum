"""
Treatment Connection Agent

Purpose:
Maps patient subgroup -> mechanism -> treatment strategy.

Input:
- subgroup output from PatientSubgroupAgent
- evidence rows from the evidence table/backend query
"""

from collections import defaultdict
from typing import Any, Dict, List, Tuple


class TreatmentConnectionAgent:
    name = "Treatment Connection Agent"

    def run(
        self,
        subgroup_output: Dict[str, Any],
        evidence_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        connection_map: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

        for row in evidence_rows:
            subgroup = row.get("subgroup")
            mechanism = row.get("mechanism")
            treatment = row.get("treatment")

            if subgroup and mechanism and treatment:
                connection_map[(subgroup, mechanism, treatment)].append(row)

        connections = []

        for rank, ((subgroup, mechanism, treatment), rows) in enumerate(
            sorted(connection_map.items(), key=lambda item: len(item[1]), reverse=True),
            start=1
        ):
            source_ids = sorted({
                row.get("source_id")
                for row in rows
                if row.get("source_id")
            })

            connections.append({
                "rank": rank,
                "subgroup": subgroup,
                "mechanism": mechanism,
                "treatment_strategy": treatment,
                "evidence_count": len(rows),
                "evidence_sources": source_ids,
                "rationale": (
                    f"{subgroup} is linked to {mechanism}, suggesting a treatment strategy "
                    f"around {treatment}. This connection is supported by {len(rows)} evidence rows."
                )
            })

        return {
            "agent": self.name,
            "connections": connections,
            "summary": f"Mapped {len(connections)} subgroup-treatment connections."
        }