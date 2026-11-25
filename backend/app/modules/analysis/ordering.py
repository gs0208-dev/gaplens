from app.modules.analysis.citations import ChunkText, VerifiedFinding

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def order_findings(
    findings: list[VerifiedFinding], chunks: list[ChunkText]
) -> tuple[list[VerifiedFinding], int]:
    """Sort by severity, then by where the evidence is in the document, and drop near-duplicates.

    A finding with no citations goes after the others of its severity. Two findings of the same
    kind citing the same chunks are one gap said twice; the first, the more severe, is kept.
    Returns the ordered findings and how many duplicates were removed.
    """
    index_of = {chunk.id: chunk.chunk_index for chunk in chunks}

    def first_position(finding: VerifiedFinding) -> float:
        positions = [index_of[c.chunk_id] for c in finding.citations if c.chunk_id in index_of]
        return min(positions) if positions else float("inf")

    ordered = sorted(findings, key=lambda f: (SEVERITY_RANK[f.severity], first_position(f)))
    kept: list[VerifiedFinding] = []
    seen: set[tuple[str, frozenset[object]]] = set()
    for finding in ordered:
        cited = frozenset(c.chunk_id for c in finding.citations)
        if cited and (finding.kind, cited) in seen:
            continue
        seen.add((finding.kind, cited))
        kept.append(finding)
    return kept, len(findings) - len(kept)
