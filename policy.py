from config import POLICY_SCORE_THRESHOLDS


def decide(scores):
    """Return the deterministic aggregate score and action for agent scores."""
    values = [max(0.0, min(100.0, float(score))) for score in scores.values()]
    if not values:
        return 0, "ALLOW"

    final_score = 0.6 * max(values) + 0.4 * (sum(values) / len(values))
    if sum(score >= 60 for score in values) >= 2:
        final_score += 10
    final_score = min(100.0, final_score)

    if final_score >= POLICY_SCORE_THRESHOLDS["BLOCK"]:
        action = "BLOCK"
    elif final_score >= POLICY_SCORE_THRESHOLDS["HOLD_FOR_REVIEW"]:
        action = "HOLD_FOR_REVIEW"
    elif final_score >= POLICY_SCORE_THRESHOLDS["REQUEST_2FA"]:
        action = "REQUEST_2FA"
    else:
        action = "ALLOW"
    return round(final_score, 2), action