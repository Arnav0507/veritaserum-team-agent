"""Trusted domain vocabulary and executable simulator. No model code executes here."""

FACTS = {
    "affected_segment": {"role": "support", "values": ["eu_wallet", "us_card"],
                         "label": "Affected checkout segment"},
    "repair": {"role": "engineering", "values": ["disable_fast_checkout", "restart"],
               "label": "Engineering-verified repair"},
    "rollback_safe": {"role": "operations", "values": ["yes", "no"],
                      "label": "Rollback preserves data compatibility"},
}
ACTIONS = ["disable_fast_checkout", "rollback", "restart"]
RUNBOOK = (
    "Checkout incident response. Collect affected_segment from support, repair from engineering, "
    "and rollback_safe from operations. An operator must approve execution. Available actions: "
    "disable_fast_checkout, rollback, restart. A rollback requires explicit data compatibility. "
    "Prefer the engineering-verified repair. Verify affected and unaffected checkout segments "
    "and data compatibility before accepting any configuration change."
)
INITIAL_CONFIG = {"version": 42, "schema": 42, "fast_checkout": True, "restarts": 0}


def statement(key, value):
    return f"{FACTS[key]['label']}: {value.replace('_', ' ')}."


def assess(claims):
    values = {key: set() for key in FACTS}
    for claim in claims:
        values[claim["key"]].add(claim["value"])
    missing = [key for key, v in values.items() if not v]
    conflicts = [key for key, v in values.items() if len(v) > 1]
    eligible = []
    if not missing and not conflicts:
        eligible.append(next(iter(values["repair"])))
        if values["rollback_safe"] == {"yes"}:
            eligible.append("rollback")
    return {"missing": missing, "conflicts": conflicts, "eligible": eligible}


def checkout(config, region, method):
    if config["version"] < config["schema"]:
        return "incompatible_schema"
    if config["fast_checkout"] and region == "eu" and method == "wallet":
        return "gateway_error"
    return "paid"


def verify(config):
    checks = []
    for region, method in [("eu", "wallet"), ("us", "card"), ("eu", "card")]:
        actual = checkout(config, region, method)
        checks.append({"name": f"{region}/{method}", "expected": "paid", "actual": actual,
                       "passed": actual == "paid"})
    checks.append({"name": "data compatibility", "expected": True,
                   "actual": config["version"] >= config["schema"],
                   "passed": config["version"] >= config["schema"]})
    return checks


def simulate(config, action):
    candidate = dict(config)
    if action == "disable_fast_checkout":
        candidate["fast_checkout"] = False
    elif action == "rollback":
        candidate["version"] -= 1
    elif action == "restart":
        candidate["restarts"] += 1
    else:
        raise ValueError("Unknown action")
    checks = verify(candidate)
    return candidate, {"action": action, "before": verify(config), "checks": checks,
                       "passed": all(c["passed"] for c in checks)}
