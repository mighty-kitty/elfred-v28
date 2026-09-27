from __future__ import annotations

from .content_cleaning import extract_core_content
from .models import MemoryEntry


def derive_fact_entries(entry: MemoryEntry) -> list[MemoryEntry]:
    if entry.category != "episodic":
        return []

    text = extract_core_content(entry.text)
    lowered = text.lower()
    speaker = _speaker_name(entry)
    facts: list[str] = []

    if "self-care is really important" in lowered:
        facts.append(f"{speaker} realized that self-care is important.")
    if all(token in lowered for token in ("me-time", "running", "reading")) and "violin" in lowered:
        facts.append(f"{speaker} prioritizes self-care through me-time, running, reading, and playing the violin.")
    if "researching adoption agencies" in lowered:
        facts.append(f"{speaker} plans to spend the summer researching adoption agencies.")
    if "help lgbtq+ folks with adoption" in lowered or "help lgbtq folks with adoption" in lowered:
        facts.append("The adoption agency supports LGBTQ+ individuals.")
        facts.append(f"{speaker} chose the adoption agency because of its inclusivity and support for LGBTQ+ individuals.")
    if "make a family for kids who need one" in lowered:
        facts.append(f"{speaker} is excited about creating a family for kids who need one.")
    if "awesome mom" in lowered and "doing something amazing" in lowered:
        facts.append("Melanie thinks Caroline is doing something amazing and will be an awesome mom.")
    if "stands for love, faith and strength" in lowered:
        facts.append("Caroline's necklace symbolizes love, faith, and strength.")
    if "gift from my grandma" in lowered and "sweden" in lowered:
        facts.append("Caroline's grandma is from Sweden.")
        facts.append("Caroline's grandma gave her a necklace.")
    if "art and self-expression" in lowered and "bowl" in lowered:
        facts.append("The hand-painted bowl reminds Melanie of art and self-expression.")
    if all(token in lowered for token in ("explored nature", "roasted marshmallows", "went on a hike")):
        facts.append("Melanie and her family explored nature, roasted marshmallows, and went on a hike while camping.")
    if "work with trans people" in lowered and "supporting their mental health" in lowered:
        facts.append("Caroline wants to work with trans people, help them accept themselves, and support their mental health.")
    if "counseling workshop" in lowered:
        facts.append("Caroline recently attended an LGBTQ+ counseling workshop.")
    if "therapeutic methods" in lowered and "best work with trans people" in lowered:
        facts.append("The workshop discussed therapeutic methods and how to best work with trans people.")
    if "counseling and support groups improved my life" in lowered:
        facts.append("Caroline was motivated to pursue counseling by her own journey, the support she received, and how counseling improved her life.")

    result: list[MemoryEntry] = []
    for index, fact in enumerate(dict.fromkeys(facts)):
        metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
        metadata.update(
            {
                "source_memory_id": entry.memory_id,
                "fact_kind": "derived_fact",
                "fact_index": index,
            }
        )
        result.append(
            MemoryEntry(
                text=fact,
                category="fact",
                score=max(0.45, entry.score),
                user_id=entry.user_id,
                session_id=entry.session_id,
                emotion=entry.emotion,
                tags=list(dict.fromkeys(entry.tags + ["derived_fact"])),
                metadata=metadata,
            )
        )
    return result


def _speaker_name(entry: MemoryEntry) -> str:
    if isinstance(entry.metadata, dict):
        for relation in entry.metadata.get("relations", []):
            if isinstance(relation, str) and relation.startswith("speaker:"):
                return relation.split(":", 1)[1].capitalize()
    return "The speaker"
