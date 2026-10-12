from collections import Counter

DECISIONS = ("compliant", "non_compliant", "needs_review")


def ratio(n, d):
    return {"numerator": n, "denominator": d, "value": n / d if d else None}


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * q
    low = int(index)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)


def metrics(records, articles=None):
    matrix = {truth: dict.fromkeys((*DECISIONS, "technical_failure"), 0) for truth in DECISIONS}
    total = len(records)
    auto = correct = violations = recalled = found = negatives = false_positive = failures = 0
    types = Counter(tp=0, fp=0, fn=0)
    refs = Counter(tp=0, fp=0, fn=0)
    latency, errors, tokens = [], Counter(), Counter()
    matched_quotes = quote_count = unknown_articles = checked_quotes = 0
    type_samples = article_samples = 0
    for row in records:
        sample, result = row["sample"], row.get("response") or {}
        truth = sample["expected_decision"]
        status, decision = result.get("status", "failed"), result.get("decision")
        # Partial detections count separately, never as completed automatic decisions.
        completed = status == "completed" and decision in DECISIONS
        matrix[truth][decision if completed else "technical_failure"] += 1
        failures += not completed
        automatic = completed and decision in ("compliant", "non_compliant")
        auto += automatic
        correct += automatic and decision == truth
        violations += truth == "non_compliant"
        recalled += truth == "non_compliant" and completed and decision == "non_compliant"
        detection = (
            status in ("completed", "partial")
            and decision == "non_compliant"
            and bool(result.get("violations"))
        )
        found += truth == "non_compliant" and detection
        negatives += truth == "compliant"
        false_positive += truth == "compliant" and detection
        for key, predicted, counts in (
            ("expected_categories", {v["type"] for v in result.get("violations", [])}, types),
            (
                "expected_article_ids",
                {c["article_id"] for v in result.get("violations", []) for c in v["citations"]},
                refs,
            ),
        ):
            gold = sample.get(key)
            if gold is not None:
                expected = set(gold)
                counts.update(
                    tp=len(predicted & expected),
                    fp=len(predicted - expected),
                    fn=len(expected - predicted),
                )
                type_samples += key == "expected_categories"
                article_samples += key == "expected_article_ids"
        for violation in result.get("violations", []):
            for citation in violation["citations"]:
                quote_count += 1
                if articles is not None:
                    checked_quotes += 1
                    article = articles.get(citation["article_id"])
                    unknown_articles += article is None
                    matched_quotes += (
                        article is not None
                        and article["original_text"] == citation["original_text"]
                    )
        meta = result.get("meta", {})
        elapsed = row.get("elapsed_ms", meta.get("latency_ms"))
        if elapsed is not None:
            latency.append(elapsed)
        for key, value in meta.get("token_usage", {}).items():
            if isinstance(value, (int, float)):
                tokens[key] += value
        errors.update(e["code"] for e in result.get("errors", []))
        if row.get("runner_error"):
            errors[row["runner_error"]] += 1
    f1 = {}
    for category in DECISIONS:
        tp = matrix[category][category]
        fn = sum(matrix[category].values()) - tp
        fp = sum(matrix[other][category] for other in DECISIONS if other != category)
        f1[category] = ratio(2 * tp, 2 * tp + fp + fn)
    available = [v["value"] for v in f1.values() if v["value"] is not None]
    return {
        "samples": total,
        "confusion_matrix": matrix,
        "class_f1": f1,
        "macro_f1": sum(available) / len(available) if available else None,
        "violation_recall": ratio(recalled, violations),
        "valid_violation_detection_recall_including_partial": ratio(found, violations),
        "non_compliant_false_positive_rate": ratio(false_positive, negatives),
        "automatic_coverage": ratio(auto, total),
        "automatic_accuracy": ratio(correct, auto),
        "technical_failure_rate_including_partial": ratio(failures, total),
        "type_micro_f1": ratio(2 * types["tp"], 2 * types["tp"] + types["fp"] + types["fn"]),
        "type_labeled_samples": type_samples,
        "article_precision": ratio(refs["tp"], refs["tp"] + refs["fp"]),
        "article_recall": ratio(refs["tp"], refs["tp"] + refs["fn"]),
        "article_labeled_samples": article_samples,
        "citation_original_match": ratio(matched_quotes, checked_quotes),
        "citation_count": quote_count,
        "unknown_articles": unknown_articles if articles is not None else None,
        "latency_ms": {
            "p50": percentile(latency, 0.5),
            "p95": percentile(latency, 0.95),
            "observed": len(latency),
        },
        "token_usage": dict(tokens),
        "error_buckets": dict(errors),
        "label_status_counts": dict(Counter(r["sample"]["label_status"] for r in records)),
        "mock_samples": sum(bool((r.get("response") or {}).get("mock")) for r in records),
    }
