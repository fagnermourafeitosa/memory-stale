from pathlib import Path


def test_host_skills_require_semantic_memory_to_follow_prompt_language() -> None:
    repository = Path(__file__).parents[1]
    required_phrases = (
        "same natural language as the user's prompt",
        "Do not translate semantic memory to English",
        "claim, durability reason, and retrieval terms",
    )

    for relative_path in (
        Path("skills/memory-stale/SKILL.md"),
        Path("claude/skills/memory-stale/SKILL.md"),
    ):
        instructions = " ".join((repository / relative_path).read_text(encoding="utf-8").split())
        for phrase in required_phrases:
            assert phrase in instructions, f"{relative_path} is missing: {phrase}"
