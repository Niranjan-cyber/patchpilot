"""B07: G4 diff policy (contracts §1.1) on crafted diffs + DIAGNOSE evidence-ID validation."""
from backend.contracts.models import CheckStatus
from backend.gates.diff_policy import check_diagnosis, g4_result, swallowed_excepts


def d(path, plus=1, minus=1, new=False, deleted=False):
    head = f"diff --git a/{path} b/{path}\n"
    if new:
        head += "new file mode 100644\n--- /dev/null\n"
    else:
        head += f"--- a/{path}\n"
    head += "+++ /dev/null\n" if deleted else f"+++ b/{path}\n"
    return head + f"@@ -1,{minus} +1,{plus} @@\n" + "-old\n" * minus + "+new\n" * plus


def reason(diff):
    r = g4_result(diff, evidence_ids=["e1"])
    return r.status, r.reason


def test_ok_source_fix():
    assert reason(d("src/click/core.py") + d("src/click/types.py", 3, 0)) == (CheckStatus.PASSED, "ok")
    assert g4_result(d("src/a.py"), evidence_ids=["e1"]).gate == "G4"


def test_rejects_test_file_edits():
    for p in ("tests/test_core.py", "src/pkg/tests/test_x.py", "testing/test_x.py", "pkg/test_util.py",
              "pkg/util_test.py", "tests/conftest.py", "conftest.py"):
        assert reason(d("src/a.py") + d(p)) == (CheckStatus.FAILED, "edits_tests"), p


def test_rejects_deleted_test():
    assert reason(d("tests/test_core.py", 0, 5, deleted=True)) == (CheckStatus.FAILED, "edits_tests")


def test_rejects_dependency_files():
    for p in ("requirements.txt", "requirements/dev.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
              "Pipfile.lock", "poetry.lock", "uv.lock", "docs/requirements-docs.txt"):
        assert reason(d(p)) == (CheckStatus.FAILED, "dependency_change"), p


def test_rejects_github_dir():
    assert reason(d(".github/workflows/ci.yml")) == (CheckStatus.FAILED, "ci_change")


def test_rejects_too_large():
    assert reason("".join(d(f"src/m{i}.py") for i in range(6))) == (CheckStatus.FAILED, "too_many_files")
    assert reason(d("src/a.py", 150, 51)) == (CheckStatus.FAILED, "too_many_lines")
    assert reason(d("src/a.py", 150, 50)) == (CheckStatus.PASSED, "ok")   # exactly 200 is allowed


def test_rejects_empty_and_binary():
    assert reason("") == (CheckStatus.FAILED, "empty_diff")
    binary = "diff --git a/src/x.bin b/src/x.bin\nGIT binary patch\nliteral 3\n"
    assert reason(binary) == (CheckStatus.FAILED, "binary_change")


def test_rename_counts_both_paths():
    ren = "diff --git a/src/a.py b/tests/test_a.py\nsimilarity index 100%\nrename from src/a.py\nrename to tests/test_a.py\n"
    assert reason(ren) == (CheckStatus.FAILED, "edits_tests")


def test_check_diagnosis():
    known = {"ev1", "ev2"}
    ok = {"hypothesis": "h", "locations": [{"path": "src/a.py", "line": 3}], "evidence_ids": ["ev1"]}
    assert check_diagnosis(ok, known, lambda p: 10 if p == "src/a.py" else None) is None
    assert check_diagnosis({**ok, "evidence_ids": ["ev9"]}, known, lambda p: 10) == "unknown_evidence_id"
    assert check_diagnosis({**ok, "evidence_ids": []}, known, lambda p: 10) == "no_evidence"
    assert check_diagnosis({**ok, "locations": [{"path": "nope.py", "line": 1}]}, known, lambda p: None) == "unknown_file"
    assert check_diagnosis({**ok, "locations": [{"path": "src/a.py", "line": 11}]}, known, lambda p: 10) == "line_out_of_range"
    assert check_diagnosis({**ok, "locations": []}, known, lambda p: 10) == "no_location"
    assert check_diagnosis({**ok, "hypothesis": " "}, known, lambda p: 10) == "no_hypothesis"
    assert check_diagnosis(None, known, lambda p: 10) == "no_result"
    assert check_diagnosis({**ok, "locations": [{"path": "../etc/passwd", "line": 1}]}, known, lambda p: 10) == "unknown_file"


def test_check_diagnosis_rejects_malformed_shapes():
    base = {"hypothesis": "h", "evidence_ids": ["ev1"]}
    assert check_diagnosis({**base, "locations": ["src/a.py:3"]}, {"ev1"}, lambda p: 10) == "no_location"
    assert check_diagnosis({**base, "locations": "src/a.py"}, {"ev1"}, lambda p: 10) == "no_result"
    assert check_diagnosis({**base, "evidence_ids": "ev1", "locations": []}, {"ev1"}, lambda p: 10) == "no_result"


RUN11 = """diff --git a/src/itsdangerous/serializer.py b/src/itsdangerous/serializer.py
--- a/src/itsdangerous/serializer.py
+++ b/src/itsdangerous/serializer.py
@@ -256,15 +256,26 @@ class Serializer(t.Generic[_TSerialized]):
         try:
+            if is_text:
+                return use_serializer.loads(payload.decode("utf-8"), **self.serializer_kwargs)
+            return use_serializer.loads(payload, **self.serializer_kwargs)
+        except TypeError:
+            # Fallback without kwargs
             if is_text:
                 return use_serializer.loads(payload.decode("utf-8"))
-
             return use_serializer.loads(payload)
         except Exception as e:
             raise BadPayload("Could not load the payload", original_error=e) from e
"""


def test_added_except_that_retries_silently_is_a_concern():   # run 11's hack
    c = swallowed_excepts(RUN11)
    assert len(c) == 1 and c[0]["severity"] == "medium" and "except TypeError:" in c[0]["text"]   # context `except Exception` isn't added


def test_removed_swallow_and_handled_excepts_are_not_concerns():
    removed = ("diff --git a/tinycalc/ops.py b/tinycalc/ops.py\n--- a/tinycalc/ops.py\n+++ b/tinycalc/ops.py\n@@ -10,4 +10,2 @@\n"
               " def divide(a, b):\n-    try:\n-        return a / b\n-    except ZeroDivisionError:\n-        return 0\n+    return a / b\n")
    assert swallowed_excepts(removed) == []                       # tinycalc #1: removing a swallow is the fix
    reraise = ("diff --git a/p/m.py b/p/m.py\n--- a/p/m.py\n+++ b/p/m.py\n@@ -1,2 +1,6 @@\n def f():\n+    try:\n+        g()\n"
               "+    except KeyError as e:\n+        raise ValueError('bad key') from e\n")
    assert swallowed_excepts(reraise) == []
    logged = reraise.replace("+        raise ValueError('bad key') from e", "+        logger.warning('no key')\n+        return None")
    assert swallowed_excepts(logged) == []


def test_broad_catch_is_a_concern_even_when_logged_and_tests_are_ignored():
    broad = ("diff --git a/p/m.py b/p/m.py\n--- a/p/m.py\n+++ b/p/m.py\n@@ -1,2 +1,6 @@\n def f():\n+    try:\n+        g()\n"
             "+    except Exception:\n+        logger.exception('x')\n")
    assert "catches every error" in swallowed_excepts(broad)[0]["text"]
    assert "catches every error" in swallowed_excepts(broad.replace("except Exception:", "except:"))[0]["text"]
    assert swallowed_excepts(broad.replace("p/m.py", "tests/test_m.py")) == []


# --- paths with spaces used to be invisible to the gate (bug:P0) ----------


def test_a_test_file_with_a_space_still_fails_g4():
    # git does not quote a space in the `diff --git a/X b/Y` header, so the old
    # \S+ pattern matched nothing and the file was never checked: the Fixer
    # could neuter the reproduction test and still pass G4.
    assert g4_result(d("tests/my test.py"), evidence_ids=[]).reason == "edits_tests"
    assert g4_result(d("tests/my_test.py"), evidence_ids=[]).reason == "edits_tests"


def test_a_workflow_with_a_space_still_fails_g4():
    assert g4_result(d(".github/workflows/my flow.yml"), evidence_ids=[]).reason == "ci_change"


def test_a_source_file_with_a_space_still_passes():
    assert g4_result(d("src/my module.py"), evidence_ids=[]).status is CheckStatus.PASSED


def test_spaced_paths_count_towards_the_file_limit():
    many = "".join(d(f"src/file {i}.py") for i in range(6))
    assert g4_result(many, evidence_ids=[]).reason == "too_many_files"


def test_a_header_that_cannot_be_parsed_fails_the_gate():
    # git quotes non-ASCII paths; a file we can't name is a file we can't check,
    # so the diff is refused rather than silently accepted.
    quoted = 'diff --git "a/tests/t\303\251st.py" "b/tests/t\303\251st.py"\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n'
    r = g4_result(d("src/ok.py") + quoted, evidence_ids=[])
    assert (r.status, r.reason) == (CheckStatus.FAILED, "unparseable_diff")


def test_diff_paths_reports_both_sides_of_a_rename():
    from backend.gates.diff_policy import diff_paths
    rename = ("diff --git a/src/old.py b/tests/new.py\nsimilarity index 100%\n"
              "rename from src/old.py\nrename to tests/new.py\n")
    paths, parsed_all = diff_paths(rename)
    assert paths == {"src/old.py", "tests/new.py"} and parsed_all
    assert g4_result(rename, evidence_ids=[]).reason == "edits_tests"


def test_an_empty_diff_is_still_empty_not_unparseable():
    assert g4_result("", evidence_ids=[]).reason == "empty_diff"
    assert g4_result("no headers here\n", evidence_ids=[]).reason == "empty_diff"


def test_a_concern_in_a_spaced_file_is_attributed_to_it():
    diff = ("diff --git a/src/my module.py b/src/my module.py\n--- a/src/my module.py\n+++ b/src/my module.py\n"
            "@@ -1,2 +1,3 @@\n try:\n     x()\n+except Exception:\n+    pass\n")
    concerns = swallowed_excepts(diff)
    assert len(concerns) == 1 and "src/my module.py" in concerns[0]["text"]
