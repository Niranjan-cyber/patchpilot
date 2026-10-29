import pytest
from backend.contracts.models import (CheckStatus as C, EndReason as E, Outcome as O, PublishBlocker as P,
                                      RunStatus as R, decide_outcome, end_blockers, readiness, status_after_analysis)

P_, F, B = C.PASSED, C.FAILED, C.BLOCKED

@pytest.mark.parametrize("gates,end,kw,want", [
    ({"G1": B}, E.COMPLETED, {}, O.BLOCKED),                                        # row 1
    ({"G1": P_, "G2": F}, E.RETRIES_EXHAUSTED, {}, O.ENV_FAILED),                     # row 2
    ({"G2": P_, "G3": P_, "G5": P_}, E.COMPLETED, {}, O.VERIFIED_FIX),                # row 3
    ({"G2": P_, "G3": P_, "G5": P_}, E.COMPLETED, {"review_concerns": True}, O.FIX_NEEDS_ATTENTION),
    ({"G2": P_, "G3": P_, "G5": P_}, E.USER_STOPPED, {}, O.FIX_NEEDS_ATTENTION),      # row 4: stop after verify
    ({"G2": P_, "G3": P_, "G5": P_}, E.COMPLETED, {"readiness_capped": True}, O.FIX_NEEDS_ATTENTION),
    ({"G2": P_, "G3": P_, "G5": F}, E.RETRIES_EXHAUSTED, {"diagnosis_valid": True}, O.TRIAGE_ONLY),  # row 5
    ({"G2": P_, "G3": P_}, E.RETRIES_EXHAUSTED, {}, O.TRIAGE_ONLY),                    # diagnosis unavailable
    ({"G2": P_, "G3": P_}, E.USER_STOPPED, {"stopped_during_diagnose": True}, O.STOPPED),  # row 5 exception
    ({"G2": P_, "G3": F}, E.RETRIES_EXHAUSTED, {}, O.CANNOT_REPRODUCE),               # row 6
    ({"G1": P_}, E.SYSTEM_ERROR, {}, O.SYSTEM_ERROR),                                 # row 7
    ({"G1": P_}, E.USER_STOPPED, {}, O.STOPPED),                                      # row 8: stop during setup
    ({"G2": P_}, E.USER_STOPPED, {}, O.STOPPED),                                      # stop while reproducing
    ({"G2": P_}, E.PAUSE_TIMEOUT, {}, O.STOPPED),
])
def test_outcome_table(gates, end, kw, want):
    assert decide_outcome(gates, end, **kw) == want


def test_user_stop_never_publishable():
    o = decide_outcome({"G2": P_, "G3": P_, "G5": P_}, E.USER_STOPPED)
    bl = end_blockers(E.USER_STOPPED, o)
    assert P.RUN_STOPPED in bl and status_after_analysis(o, bl) == R.FINISHED


def test_inconclusive_deps_stays_awaiting_approval():
    assert status_after_analysis(O.FIX_NEEDS_ATTENTION, [P.DEPS_INCONCLUSIVE, P.NOT_APPROVED]) == R.AWAITING_APPROVAL


def test_readiness_cap():
    assert readiness(O.VERIFIED_FIX, capped=True) == "Needs attention"
    assert readiness(O.CANNOT_REPRODUCE) == "Unable to verify"
