from pathlib import Path

from src.pipelines.daily_report.knowledge import load_approved_knowledge


def test_load_approved_knowledge_reads_all_sections(tmp_path: Path):
    base = tmp_path / "knowledge" / "daily_report"
    base.mkdir(parents=True)
    (base / "aliases.yaml").write_text("Micron: [마이크론, MU]\n", encoding="utf-8")
    (base / "concepts.yaml").write_text("HBM4:\n  concept: memory\n", encoding="utf-8")
    (base / "relations.yaml").write_text(
        "- from: memory\n  to: advanced_packaging\n  weight: 0.7\n",
        encoding="utf-8",
    )
    (base / "message_types.yaml").write_text(
        "broker_summary:\n  patterns: ['목표주가', '투자의견']\n",
        encoding="utf-8",
    )

    knowledge = load_approved_knowledge(base)

    assert knowledge.aliases["Micron"] == ["마이크론", "MU"]
    assert knowledge.concepts["HBM4"]["concept"] == "memory"
    assert knowledge.relations[0]["to"] == "advanced_packaging"
    assert "broker_summary" in knowledge.message_types
