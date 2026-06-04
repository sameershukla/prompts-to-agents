import anthropic
import json
from datetime import datetime, timezone
from dataclasses import dataclass

client = anthropic.Anthropic(api_key="your-api-key-here")

# -------------------------------------------------------
# THE EVALUATION RUBRIC
# Four criteria. All must pass. One failure = retry.
# Written once. Used by the Evaluator on every iteration.
# -------------------------------------------------------

EVALUATION_RUBRIC = """
Score this diagnosis against four criteria. 
For each criterion respond PASS or FAIL with one sentence of reasoning.
Return your response as JSON only, no other text.

CRITERIA:

1. ROOT_CAUSE_IDENTIFIED
   PASS: Names a specific root cause with technical detail.
   FAIL: Names only a category or is vague.

2. EVIDENCE_CITED  
   PASS: References specific evidence from the error log, tools, or memory.
   FAIL: Makes claims without citing specific evidence.

3. ACTIONABLE_FIX
   PASS: Fix is specific enough to act on without further investigation.
   FAIL: Fix requires further investigation to implement.

4. PREVENTION_INCLUDED
   PASS: Includes at least one concrete prevention step.
   FAIL: No prevention mentioned or prevention is vague.

Return exactly this JSON structure:
{
  "scores": {
    "ROOT_CAUSE_IDENTIFIED": {"result": "PASS" or "FAIL", "reason": "..."},
    "EVIDENCE_CITED":        {"result": "PASS" or "FAIL", "reason": "..."},
    "ACTIONABLE_FIX":        {"result": "PASS" or "FAIL", "reason": "..."},
    "PREVENTION_INCLUDED":   {"result": "PASS" or "FAIL", "reason": "..."}
  },
  "overall": "PASS" or "FAIL",
  "feedback": "One paragraph of specific feedback for the generator to improve on retry."
}
"""

# -------------------------------------------------------
# DATA STRUCTURES
# Make the evaluation result explicit and typed.
# Never parse freeform text when you can parse JSON.
# -------------------------------------------------------

@dataclass
class EvaluationResult:
    overall:  str          # PASS or FAIL
    scores:   dict         # per criterion results
    feedback: str          # feedback for generator on retry
    attempt:  int          # which attempt produced this result

# -------------------------------------------------------
# STEP 1: THE GENERATOR
# Produces a diagnosis from the error log.
# Same logic as Level 4 but output goes to Evaluator, not engineer.
# -------------------------------------------------------

GENERATOR_PROMPT = """
You are a senior AWS Glue engineer performing root cause analysis.

You will receive:
1. MEMORY CONTEXT: past failures and known playbooks for this job
2. CURRENT ERROR: the error being diagnosed
3. PREVIOUS FEEDBACK (on retry only): what the evaluator said was missing

Produce a diagnosis that includes:
- ROOT CAUSE: specific and technical, not a category
- EVIDENCE: cite specific lines from the error log or tool results
- FIX: exact steps or code, specific enough to act on immediately
- PREVENTION: at least one concrete step to prevent recurrence

If previous feedback is provided, address every point it raises.
"""

def generate_diagnosis(error_log: str,
                       memory_context: str,
                       previous_feedback: str = "") -> str:

    content = f"""
MEMORY CONTEXT:
{memory_context if memory_context else "No prior memory for this job."}

CURRENT ERROR LOG:
{error_log}
"""

    if previous_feedback:
        content += f"""
PREVIOUS EVALUATION FEEDBACK:
{previous_feedback}

Address every point raised in the feedback above.
"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=GENERATOR_PROMPT,
        messages=[{"role": "user", "content": content}]
    )

    return response.content[0].text

# -------------------------------------------------------
# STEP 2: THE EVALUATOR
# Scores the generator's output against the rubric.
# Returns a structured verdict. Never rewrites the output.
# A separate model call makes the evaluation more reliable.
# -------------------------------------------------------

EVALUATOR_PROMPT = f"""
You are a quality evaluator for Glue job RCA diagnoses.
Your only job is to score diagnoses against the rubric below.
Never rewrite. Never diagnose. Only evaluate.

{EVALUATION_RUBRIC}
"""

def evaluate_diagnosis(error_log: str,
                       diagnosis: str,
                       attempt: int) -> EvaluationResult:

    content = f"""
ORIGINAL ERROR LOG:
{error_log}

DIAGNOSIS TO EVALUATE:
{diagnosis}

Score this diagnosis against all four criteria.
Return only the JSON structure specified in your instructions.
"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=EVALUATOR_PROMPT,
        messages=[{"role": "user", "content": content}]
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    return EvaluationResult(
        overall=result["overall"],
        scores=result["scores"],
        feedback=result.get("feedback", ""),
        attempt=attempt
    )

# -------------------------------------------------------
# STEP 3: THE AUTONOMOUS LOOP
# Generate. Evaluate. Retry if needed. Return when ready.
# This is the core of Level 5.
# -------------------------------------------------------

def level5_rca(error_log: str,
               memory_context: str = "",
               max_iterations: int = 3) -> dict:

    print(f"\n[Level 5 autonomous loop started]")
    print(f"[Max iterations: {max_iterations}]")

    previous_feedback = ""
    history = []

    for attempt in range(1, max_iterations + 1):

        print(f"\n[Attempt {attempt}: Generating diagnosis...]")

        # Generate
        diagnosis = generate_diagnosis(
            error_log=error_log,
            memory_context=memory_context,
            previous_feedback=previous_feedback
        )

        print(f"[Attempt {attempt}: Evaluating diagnosis...]")

        # Evaluate
        evaluation = evaluate_diagnosis(
            error_log=error_log,
            diagnosis=diagnosis,
            attempt=attempt
        )

        # Record this attempt
        history.append({
            "attempt":    attempt,
            "diagnosis":  diagnosis,
            "evaluation": evaluation
        })

        # Print evaluation results
        print(f"[Attempt {attempt}: Overall = {evaluation.overall}]")
        for criterion, score in evaluation.scores.items():
            status = score["result"]
            symbol = "✓" if status == "PASS" else "✗"
            print(f"  {symbol} {criterion}: {status}")

        # Pass: return the diagnosis
        if evaluation.overall == "PASS":
            print(f"\n[Passed on attempt {attempt}. Delivering diagnosis.]")
            return {
                "status":    "SUCCESS",
                "diagnosis": diagnosis,
                "attempts":  attempt,
                "history":   history
            }

        # Fail: set feedback for next attempt
        previous_feedback = evaluation.feedback
        print(f"[Attempt {attempt} failed. Feedback: {evaluation.feedback[:100]}...]")

    # Max iterations reached without passing
    print(f"\n[Max iterations reached. Returning best attempt.]")
    best = history[-1]
    return {
        "status":    "MAX_ITERATIONS_REACHED",
        "diagnosis": best["diagnosis"],
        "attempts":  max_iterations,
        "history":   history
    }

# -------------------------------------------------------
# SIMULATED TRIGGER
# In production EventBridge fires this when a Glue job fails.
# Here we simulate the trigger so you can run it locally.
# -------------------------------------------------------

def simulate_eventbridge_trigger(job_name: str,
                                  error_log: str,
                                  memory_context: str = ""):
    print("=" * 55)
    print("LEVEL 5: Autonomous Pattern")
    print("=" * 55)
    print(f"[EventBridge trigger received for job: {job_name}]")
    print(f"[Timestamp: {datetime.now(timezone.utc).isoformat()}]")
    print(f"[Starting autonomous RCA without human intervention...]")

    result = level5_rca(
        error_log=error_log,
        memory_context=memory_context,
        max_iterations=3
    )

    print("\n" + "=" * 55)
    print(f"STATUS:   {result['status']}")
    print(f"ATTEMPTS: {result['attempts']}")
    print("=" * 55)
    print("\nFINAL DIAGNOSIS:")
    print(result["diagnosis"])

    return result

# -------------------------------------------------------
# TEST IT
# -------------------------------------------------------

ERROR_LOG = """
GlueException: An error occurred while calling o108.pyWriteDynamicFrame.
Output path already exists: s3://prod-bucket/output/customer_data/
Job: customer_daily_transform
Role: GlueJobExecutionRole
Timestamp: 2025-01-15 02:03:47 UTC
"""

MEMORY_CONTEXT = """
PAST FAILURES FOR THIS JOB:
  - 2025-01-14: S3_OUTPUT_EXISTS | Fix: S3_OUTPUT_EXISTS | Outcome: RESOLVED
  - 2025-01-13: S3_OUTPUT_EXISTS | Fix: S3_OUTPUT_EXISTS | Outcome: RESOLVED

KNOWN PLAYBOOK FOR S3_OUTPUT_EXISTS:
  KNOWN FIX: Add overwrite mode to the write operation.
  Option 1 (recommended): df.write.mode("overwrite").parquet(path)
  Option 2: Delete the output path before writing using boto3.
  PREVENTION: Add a cleanup step at the start of every job run.
  This fix has a 100% success rate on this error type.
"""

if __name__ == "__main__":
    simulate_eventbridge_trigger(
        job_name="customer_daily_transform",
        error_log=ERROR_LOG,
        memory_context=MEMORY_CONTEXT
    )
