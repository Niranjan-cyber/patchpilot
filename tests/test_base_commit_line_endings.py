"""The base commit must keep a repo's CRLF files byte for byte (tabulate #494 run 18062c36: the Windows host's
core.autocrlf=true stored examples/people.csv as LF, the sandbox's git saw it as modified, and the agent's
test diff "touched source", so G3 failed 3 times)."""
import os
import subprocess

from backend.sandbox.steps import commit_base


def test_crlf_files_are_unchanged_after_the_base_commit(tmp_path, monkeypatch):
    cfg = tmp_path / "host.gitconfig"
    cfg.write_text("[core]\n\tautocrlf = true\n")          # a Windows host's default
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    src = tmp_path / "src"
    src.mkdir()
    (src / "people.csv").write_bytes(b"id,name\r\n1,Alice\r\n")
    (src / "lib.py").write_bytes(b"x = 1\n")
    commit_base(src, "abc123")
    # what the sandbox's Linux git sees: no autocrlf
    st = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(src), "status", "--porcelain"],
                        capture_output=True, text=True, check=True,
                        env={"GIT_CONFIG_NOSYSTEM": "1", "PATH": os.environ["PATH"], "HOME": str(tmp_path)})
    assert st.stdout == ""
    blob = subprocess.run(["git", "-C", str(src), "show", "HEAD:people.csv"], capture_output=True, check=True).stdout
    assert blob == b"id,name\r\n1,Alice\r\n"
