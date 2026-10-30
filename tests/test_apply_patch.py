"""infra/apply_patch.py: the sandbox's apply_patch for the '*** Begin Patch' format gpt-oss reaches for (runs 8, 10)."""
import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location("apply_patch", pathlib.Path(__file__).parents[1] / "infra" / "apply_patch.py")
AP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AP)

SRC = "def loads(s):\n    return use_serializer.loads(s)\n\n\ndef dumps(o):\n    return x\n"


def test_update_replaces_the_matching_lines(tmp_path):
    (tmp_path / "m.py").write_text(SRC)
    AP.apply("""*** Begin Patch
*** Update File: m.py
@@ def loads(s):
-    return use_serializer.loads(s)
+    return use_serializer.loads(s, **kwargs)
*** End Patch""", tmp_path)
    assert (tmp_path / "m.py").read_text() == ("def loads(s):\n    return use_serializer.loads(s, **kwargs)\n\n\n"
                                               "def dumps(o):\n    return x\n")


def test_context_lines_anchor_the_hunk(tmp_path):
    (tmp_path / "m.py").write_text("a\nx\nb\nx\nc\n")
    AP.apply("*** Begin Patch\n*** Update File: m.py\n@@\n b\n-x\n+y\n c\n*** End Patch", tmp_path)
    assert (tmp_path / "m.py").read_text() == "a\nx\nb\ny\nc\n"


def test_add_and_delete_files(tmp_path):
    (tmp_path / "old.py").write_text("x\n")
    AP.apply("*** Begin Patch\n*** Add File: tests/test_new.py\n+import pytest\n+\n+def test_a():\n+    assert 1\n"
             "*** Delete File: old.py\n*** End Patch", tmp_path)
    assert (tmp_path / "tests" / "test_new.py").read_text() == "import pytest\n\ndef test_a():\n    assert 1\n"
    assert not (tmp_path / "old.py").exists()


def test_trailing_whitespace_differences_still_match(tmp_path):
    (tmp_path / "m.py").write_text("a  \nb\n")
    AP.apply("*** Begin Patch\n*** Update File: m.py\n@@\n-a\n+z\n b\n*** End Patch", tmp_path)
    assert (tmp_path / "m.py").read_text() == "z\nb\n"


def test_a_hunk_that_does_not_match_fails_loudly_and_changes_nothing(tmp_path):
    (tmp_path / "m.py").write_text(SRC)
    with pytest.raises(AP.PatchError, match="m.py"):
        AP.apply("*** Begin Patch\n*** Update File: m.py\n@@\n-    return nothing_like_this\n+    pass\n*** End Patch", tmp_path)
    assert (tmp_path / "m.py").read_text() == SRC


def test_missing_begin_marker_is_an_error(tmp_path):
    with pytest.raises(AP.PatchError):
        AP.apply("diff --git a/m.py b/m.py", tmp_path)
