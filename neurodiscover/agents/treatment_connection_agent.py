"""
Treatment Connection Agent

Purpose:
Maps patient subgroup -> mechanism -> treatment strategy.

Input:
- subgroup output from PatientSubgroupAgent
- evidence rows from the evidence table/backend query
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple


class TreatmentConnectionAgent:
    name = "Treatment Connection Agent"

    def run(
        self,
        subgroup_output: Dict[str, Any],
        evidence_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        subgroup_totals = {
            sg.get("name"): sg.get("evidence_count", 0)
            for sg in subgroup_output.get("subgroups", [])
            if sg.get("name")
        }

        # Group by subgroup + treatment so minor mechanism wording does not
        # split one hypothesis into many 1-row connections.
        connection_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

        for row in evidence_rows:
            subgroup = row.get("subgroup")
            treatment = row.get("treatment")
            if not subgroup:
                continue
            if not treatment:
                # Subgroup-only rows still count toward subgroup paper totals.
                continue
            connection_map[(subgroup, treatment)].append(row)

        connections = []

        for rank, ((subgroup, treatment), rows) in enumerate(
            sorted(connection_map.items(), key=lambda item: len(item[1]), reverse=True),
            start=1,
        ):
            mechanisms = [r.get("mechanism") for r in rows if r.get("mechanism")]
            mechanism = Counter(mechanisms).most_common(1)[0][0] if mechanisms else None

            source_ids = sorted({
                row.get("source_id")
                for row in rows
                if row.get("source_id")
            })

            link_count = len(rows)
            subgroup_count = subgroup_totals.get(subgroup, link_count)

            connections.append({
                "rank": rank,
                "subgroup": subgroup,
                "mechanism": mechanism,
                "treatment_strategy": treatment,
                "evidence_count": link_count,
                "subgroup_evidence_count": subgroup_count,
                "evidence_sources": source_ids,
                "rationale": (
                    f"{subgroup} is linked to {mechanism or 'mechanism TBD'}, suggesting a "
                    f"treatment strategy around {treatment}. This connection is supported by "
                    f"{link_count} evidence rows ({subgroup_count} total for the subgroup)."
                )
            })

        return {
            "agent": self.name,
            "connections": connections,
            "summary": f"Mapped {len(connections)} subgroup-treatment connections."
        }
