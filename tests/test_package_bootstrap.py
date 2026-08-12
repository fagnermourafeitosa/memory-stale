def test_project_package_is_importable() -> None:
    import memory_stale

    assert memory_stale.__doc__ == "Automatic, code-anchored memory maintenance for Codex."
