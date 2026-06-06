import anthropic
import json
from datetime import datetime, timezone

client = anthropic.Anthropic()

# -------------------------------------------------------
# BENCHMARK SUITE
# Reference inputs with expected output characteristics.
# In production this lives in a database, not in code.
# Expand to 50 plus inputs before deploying.
# -------------------------------------------------------

BENCHMARK_SUITE = [
    {
        "id": "bench_001",
        "error_log": """GlueException: Output path already exists.
s3://prod-bucket/output/customer_data/
Job: customer_daily_transform""",
        "expected_root_cause": "S3 output path conflict",
        "expected_fix_contains": "overwrite",
        "level": 1
    },
    {
        "id": "bench_002",
        "error_log": """AccessDeniedException: not authorized to perform s3:PutObject
on arn:aws:s3:::prod-bucket/output/
Role: GlueJobExecutionRole""",
        "expected_root_cause": "IAM permissions",
        "expected_fix_contains": "s3:PutObject",
        "level": 1
    },
    {
        "id": "bench_003",
        "error_log": """AnalysisException: Resolved attribute customer_id missing
from age, name, email in operator Project.
Job: customer_transform""",
        "expected_root_cause": "missing column",
        "expected_fix_contains": "customer_id",
        "level": 1
    }
]

SYSTEM_PROMPT = """You are a senior AWS Glue engineer.
Diagnose the error. Provide:
- ROOT CAUSE: specific and technical
- FIX: exact steps implementable immediately
- PREVENTION: concrete prevention step"""

# -------------------------------------------------------
# THE SCORER
# LLM-as-a-Judge evaluation.
# Scores each output against the benchmark expectations.
# Returns a score from 0 to 100.
# -------------------------------------------------------

def score_output(error_log: str,
                 system_output: str,
                 benchmark: dict) -> dict:

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system="""You are evaluating an RCA system output.
Score the output from 0 to 100 on three criteria:
1. Root cause correctness (0-40 points)
2. Fix specificity (0-40 points)
3. Prevention quality (0-20 points)

Return JSON only:
{
  "root_cause_score": 0-40,
  "fix_score": 0-40,
  "prevention_score": 0-20,
  "total": 0-100,
  "root_cause_correct": true or false,
  "notes": "one sentence observation"
}""",
        messages=[{"role": "user", "content": f"""
ERROR LOG:
{error_log}

SYSTEM OUTPUT:
{system_output}

EXPECTED ROOT CAUSE KEYWORD: {benchmark['expected_root_cause']}
EXPECTED FIX KEYWORD: {benchmark['expected_fix_contains']}

Score this output now.
"""}]
    )

    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# -------------------------------------------------------
# THE RUNNER
# Runs every benchmark through the system.
# Scores each output.
# Returns a run report.
# -------------------------------------------------------

def run_benchmark_suite(pipeline_version: str) -> dict:
    print(f"\n[Running benchmark suite: {len(BENCHMARK_SUITE)} inputs]")
    print(f"[Pipeline version: {pipeline_version}]")

    results = []
    total_score = 0

    for bench in BENCHMARK_SUITE:
        print(f"\n[Benchmark {bench['id']}...]")

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": bench["error_log"]}]
        )
        output = response.content[0].text.strip()

        score = score_output(bench["error_log"], output, bench)
        total_score += score["total"]

        result = {
            "benchmark_id":   bench["id"],
            "level":          bench["level"],
            "score":          score["total"],
            "root_cause_ok":  score["root_cause_correct"],
            "notes":          score["notes"],
            "output_preview": output[:100]
        }
        results.append(result)

        print(f"  Score: {score['total']}/100 — {score['notes']}")

    avg_score = round(total_score / len(BENCHMARK_SUITE), 1)

    run_report = {
        "pipeline_version": pipeline_version,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "benchmark_count":  len(BENCHMARK_SUITE),
        "average_score":    avg_score,
        "results":          results
    }

    return run_report


# -------------------------------------------------------
# THE ALERTER
# Compares today's score to yesterday's score.
# Fires alert if score dropped for two consecutive days.
# -------------------------------------------------------

def check_for_alert(current_report: dict,
                    previous_score: float,
                    threshold: float = 75.0) -> bool:

    current_score = current_report["average_score"]

    print(f"\n[Alert check: current={current_score}, previous={previous_score}, threshold={threshold}]")

    if current_score < threshold:
        if previous_score < threshold:
            print(f"[ALERT] Score below threshold for two consecutive runs.")
            print(f"[ALERT] Current: {current_score}. Previous: {previous_score}. Threshold: {threshold}")
            return True
        else:
            print(f"[WARNING] Score below threshold today. Monitoring tomorrow.")
    else:
        print(f"[OK] Score above threshold: {current_score}")

    return False


# -------------------------------------------------------
# RUN IT
# -------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("CHAPTER 14: Evaluation Pipeline")
    print("=" * 55)

    # Run today's benchmark suite
    report = run_benchmark_suite(pipeline_version="rca_v1.1")

    print("\n" + "=" * 55)
    print("BENCHMARK REPORT")
    print("=" * 55)
    print(f"Pipeline version: {report['pipeline_version']}")
    print(f"Average score:    {report['average_score']}/100")
    print(f"Benchmarks run:   {report['benchmark_count']}")
    print(f"Timestamp:        {report['timestamp']}")

    print("\nPer-benchmark results:")
    for r in report["results"]:
        status = "PASS" if r["score"] >= 75 else "FAIL"
        print(f"  {r['benchmark_id']}: {r['score']}/100 [{status}] — {r['notes']}")

    # Simulate previous day score for alert check
    previous_day_score = 78.0
    alert_fired = check_for_alert(report, previous_day_score)

    if alert_fired:
        print("\n[ACTION REQUIRED: Review recent prompt or model changes.]")
        print("[Compare current outputs to pipeline version with last good score.]")
