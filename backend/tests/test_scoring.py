"""Suspicion scoring formula + default weights."""
from app.services.scoring import DEFAULT, ScoringWeights, branch_score


def test_default_weights_match_blueprint():
    assert DEFAULT.high_risk_event == 10
    assert DEFAULT.medium_risk_event == 5
    assert DEFAULT.low_risk_event == 1
    assert DEFAULT.blocked_event == 4
    assert DEFAULT.malware_botnet == 15
    assert DEFAULT.known_false_positive == -3


def test_branch_score_zero_when_no_events():
    s = branch_score(high_risk=0, medium_risk=0, low_risk=0, blocked=0, ids_ips=0, w=DEFAULT)
    assert s == 0


def test_branch_score_combines_weights():
    s = branch_score(high_risk=2, medium_risk=4, low_risk=10, blocked=5, ids_ips=3, w=DEFAULT)
    # 2*10 + 4*5 + 10*1 + 5*4 + 3*6 = 20 + 20 + 10 + 20 + 18 = 88
    assert s == 88


def test_branch_score_respects_custom_weights():
    custom = ScoringWeights(high_risk_event=100, medium_risk_event=0, low_risk_event=0, blocked_event=0, outbound_suspicious=0)
    s = branch_score(high_risk=3, medium_risk=999, low_risk=999, blocked=999, ids_ips=999, w=custom)
    assert s == 300
