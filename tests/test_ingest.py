from reporadio.ingest.fetcher import (
    estimate_tokens,
    is_excluded,
    parse_content,
    repo_name,
    trim_to_cap,
)

SEP = "=" * 48


def gi_block(path: str, body: str) -> str:
    return f"{SEP}\nFILE: {path}\n{SEP}\n{body}"


def test_repo_name_variants():
    assert repo_name("https://github.com/pallets/flask") == "pallets/flask"
    assert repo_name("https://github.com/pallets/flask.git") == "pallets/flask"
    assert repo_name("https://github.com/pallets/flask/tree/main") == "pallets/flask"


def test_excludes_vendored_and_binaries():
    assert is_excluded("node_modules/react/index.js")
    assert is_excluded("frontend/node_modules/x/y.js")
    assert is_excluded("uv.lock")
    assert is_excluded("assets/logo.png")
    assert is_excluded("dist/bundle.min.js")
    assert not is_excluded("src/app.py")
    assert not is_excluded("README.md")


def test_parse_content_splits_files():
    content = "\n\n".join([
        gi_block("src/app.py", "def main():\n    pass"),
        gi_block("README.md", "# Hello"),
    ])
    files = parse_content(content)
    assert set(files) == {"src/app.py", "README.md"}
    assert files["src/app.py"].startswith("def main():")
    assert files["README.md"] == "# Hello"


def test_parse_content_without_headers_is_one_blob():
    files = parse_content("just some text")
    assert files == {"_digest": "just some text"}


def test_trim_drops_largest_first():
    files = {
        "big.py": "x" * 4000,      # ~1000 tokens
        "medium.py": "y" * 2000,   # ~500 tokens
        "small.py": "z" * 400,     # ~100 tokens
    }
    trimmed, dropped = trim_to_cap(files, max_tokens=400, overhead="")
    assert dropped == ["big.py", "medium.py"]
    assert set(trimmed) == {"small.py"}


def test_trim_keeps_everything_under_budget():
    files = {"a.py": "x" * 400, "b.py": "y" * 400}
    trimmed, dropped = trim_to_cap(files, max_tokens=1000, overhead="")
    assert dropped == []
    assert set(trimmed) == {"a.py", "b.py"}


def test_trim_accounts_for_overhead():
    files = {"a.py": "x" * 2000}
    _, dropped = trim_to_cap(files, max_tokens=600, overhead="t" * 2000)
    assert dropped == ["a.py"]


def test_estimate_tokens():
    assert estimate_tokens("abcd" * 100) == 100


def test_trim_prefers_readme_and_root_over_docs():
    files = {
        "docs/guide.md": "d" * 1200,
        "README.md": "r" * 1200,
        "pyproject.toml": "p" * 1200,
        "src/app.py": "a" * 1200,
    }
    kept, dropped = trim_to_cap(files, max_tokens=900, overhead="")
    assert "README.md" in kept
    assert "pyproject.toml" in kept
    assert "docs/guide.md" in dropped


def test_truncate_tree_caps_and_labels():
    from reporadio.ingest.fetcher import truncate_tree

    tree = "\n".join(f"dir/file_{i}.py" for i in range(500))
    small = truncate_tree(tree, max_tokens=100)
    assert estimate_tokens(small) < estimate_tokens(tree)
    assert "tree truncated" in small
    assert truncate_tree("a\nb", max_tokens=100) == "a\nb"
