"""The only place that starts sandbox containers (architecture §7). Repository code runs only through here."""
import os
import subprocess
from dataclasses import dataclass

SETUP_NET, PROXY = "pp_setup", "pp-proxpi"
INDEX_URL = f"http://{PROXY}:5000/index/"
RUNTIME = os.getenv("PP_DOCKER_RUNTIME", "")   # "runsc" on the MVP VM (gVisor); empty on the Docker Desktop prototype
HARDEN = [*(["--runtime", RUNTIME] if RUNTIME else []), "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
          "--pids-limit", "512", "--memory", os.getenv("PP_SANDBOX_MEM", "2g"), "--cpus", "2"]
# Files SETUP generated into /src (git-ignored ones, archived by steps.INSTALL, #26) go back over the pristine snapshot.
RESTORE = "[ -f /opt/venv/.pp-gen.tar ] && tar -xf /opt/venv/.pp-gen.tar -C /src 2>/dev/null; "


@dataclass
class Result:
    code: int
    out: str
    timed_out: bool = False


def _docker(*args: str, timeout: int = 120, input_: str | None = None) -> Result:
    try:
        p = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, input=input_)
        return Result(p.returncode, p.stdout + p.stderr)
    except subprocess.TimeoutExpired as e:
        return Result(124, (e.stdout or "") if isinstance(e.stdout, str) else "", timed_out=True)


def ensure_infra() -> None:
    """Idempotent: internal setup network + proxpi (PyPI-only cache) attached to it and to the default bridge."""
    if _docker("network", "inspect", SETUP_NET).code:
        _docker("network", "create", "--internal", SETUP_NET)
    if _docker("inspect", PROXY).code:
        # never redirect to PyPI: the sandbox can only reach proxpi
        # 8 threads (image default 2): Docker→PyPI can be ~10× slower than the host, and one slow upstream fetch hung both threads
        _docker("run", "-d", "--name", PROXY, "--restart", "unless-stopped", "-e", "PROXPI_DOWNLOAD_TIMEOUT=600", "epicwink/proxpi",
                "--bind", "0.0.0.0:5000", "--threads", "8", "--no-control-socket")
        _docker("network", "connect", SETUP_NET, PROXY)


def run(image: str, script: str, *, name: str, network: str = "none", timeout: int = 300,
        snapshot_volume: str | None = None, read_only: bool = True, keep: bool = False) -> Result:
    """Fresh container per call: snapshot (ro) is copied into a tmpfs /src, so every step starts clean."""
    args = ["run", "--name", name, *HARDEN, "--network", network, "-e", "HOME=/tmp", "-w", "/src",
            "--tmpfs", "/tmp:rw,exec,size=512m", "--tmpfs", "/src:rw,exec,size=1g,uid=1000,gid=1000"]
    if read_only:
        args.append("--read-only")
    if not keep:
        args.append("--rm")
    if snapshot_volume:
        args += ["-v", f"{snapshot_volume}:/snap:ro"]
    if network == SETUP_NET:
        # 120 s: the proxy fetches an uncached package from PyPI on first use (15.2 s for setuptools; pip gives up at 15)
        args += ["-e", f"PIP_INDEX_URL={INDEX_URL}", "-e", f"PIP_TRUSTED_HOST={PROXY}", "-e", f"UV_INDEX_URL={INDEX_URL}",
                 "-e", "PIP_DEFAULT_TIMEOUT=120"]
    prelude = "cp -a /snap/. /src/ 2>/dev/null; " + RESTORE if snapshot_volume else ""
    r = _docker(*args, image, "sh", "-c", prelude + script, timeout=timeout)
    if r.timed_out:
        _docker("kill", name)
    return r


def commit(name: str, image: str) -> Result:
    return _docker("commit", name, image)


def rm(*names: str) -> None:
    if names:
        _docker("rm", "-f", *names)


def rm_image(image: str) -> None:
    _docker("rmi", "-f", image)


def make_snapshot(volume: str, host_dir: str) -> Result:
    """Copy extracted source (written by the trusted worker) into a fresh volume via a throwaway container."""
    _docker("volume", "create", volume)
    helper = f"{volume}-load"
    r = _docker("create", "--name", helper, "-v", f"{volume}:/snap", "pp-base:3.12", "true")
    if r.code:
        return r
    r = _docker("cp", f"{host_dir}/.", f"{helper}:/snap", timeout=300)
    rm(helper)
    return r


def rm_volume(volume: str) -> None:
    _docker("volume", "rm", "-f", volume)


def start(image: str, name: str, snapshot_volume: str) -> Result:
    """Long-lived agent container (one per agent attempt): same hardening, no network, source copied into tmpfs /src."""
    return _docker("run", "-d", "--name", name, *HARDEN, "--network", "none", "--read-only", "-e", "HOME=/tmp", "-w", "/src",
                   "--tmpfs", "/tmp:rw,exec,size=512m", "--tmpfs", "/src:rw,exec,size=1g,uid=1000,gid=1000",
                   "-v", f"{snapshot_volume}:/snap:ro", image, "sh", "-c", "cp -a /snap/. /src/ || exit 1; " + RESTORE + "exec sleep 86400")


def exec_(name: str, script: str, timeout: int = 120) -> Result:
    r = _docker("exec", "-w", "/src", name, "sh", "-c", script, timeout=timeout)
    if r.timed_out:
        _docker("exec", name, "sh", "-c", "pkill -u 1000 -f -- '-c' || true")
    return r


def runtime_ok() -> tuple[bool, str]:
    """B19: if a runtime is configured it must exist; the worker refuses runs otherwise (never silently weaker)."""
    if not RUNTIME:
        return True, "default (no gVisor: prototype)"
    r = _docker("info", "--format", "{{json .Runtimes}}")
    return (RUNTIME in r.out), (RUNTIME if RUNTIME in r.out else f"{RUNTIME} configured but not installed")
