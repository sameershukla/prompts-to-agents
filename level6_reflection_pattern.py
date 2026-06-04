import anthropic
import json
from dataclasses import dataclass

client = anthropic.Anthropic(api_key="your-api-key-here")

# -------------------------------------------------------
# THE REFLECTION PROMPT
# Three questions. Always asked. Always answered.
# The model critiques its own output before revision.
# This runs between generation and evaluation.
# -------------------------------------------------------

REFLECTION_PROMPT = """
You are reviewing a Glue job RCA diagnosis you just wrote.
Ask yourself these three questions about your own output:

1. DID I ANSWER EXACTLY WHAT WAS ASKED?
   Read the original error log again. Does your diagnosis
   address the specific error described? Not just the category
   of error but this specific instance with these specific details?

2. IS EVERY CLAIM SUPPORTED BY EVIDENCE?
   For each claim in your diagnosis, can you point to a specific
   line in the error log, a tool result, or a memory record that
   supports it? If you cannot, the claim is speculation.

3. WHAT WOULD MAKE THIS BETTER?
   Imagine a senior engineer reading your diagnosis.
   What would they ask for that is missing?
   A specific line of code? A note about downstream impact?
   A more precise description of the root cause?

Return your response in this JSON format only:

{
  "question_1": {
    "assessment": "one sentence answer",
    "gap": "what is missing or null if nothing"
  },
  "question_2": {
    "assessment": "one sentence answer", 
    "unsupported_claims": ["claim 1", "claim 2"] or []
  },
  "question_3": {
    "improvements": ["improvement 1", "improvement 2"]
  },
  "needs_revision": true or false,
  "revision_instructions": "specific instructions for the revision or null"
}
"""

# -------------------------------------------------------
# THE REVISION PROMPT
# Used when reflection says needs_revision is true.
# Takes the original diagnosis and the reflection output.
# Produces a stronger version of the same diagnosis.
# -------------------------------------------------------

REVISION_PROMPT = """
You wrote a Glue job RCA diagnosis. You then reflected on it
and identified specific improvements.

Your job now is to produce a revised diagnosis that addresses
every point raised in your reflection. Do not produce a 
completely different answer. Improve the answer you already have.

Be specific:
- Where you had a category, name the specific failure
- Where you had a vague fix, provide exact code or steps  
- Where you had no evidence, cite the specific line or result
- Where you had no prevention, add a concrete prevention step
"""

# -------------------------------------------------------
# DATA STRUCTURES
# -------------------------------------------------------

@dataclass
class ReflectionResult:
    needs_revision:       bool
    revision_instructions: str
    gaps:                 list
    unsupported_claims:   list
    improvements:         list

@dataclass  
class EvaluationResult:
    overall:  str
    scores:   dict
    feedback: str
    attempt:  int

# -------------------------------------------------------
# STEP 1: THE GENERATOR
# Same as Level 5. Produces initial diagnosis.
# -------------------------------------------------------

GENERATOR_PROMPT = """
You are a senior AWS Glue engineer performing root cause analysis.

You will receive memory context and an error log.
Produce a diagnosis with:
- ROOT CAUSE: specific and technical
- EVIDENCE: cite exact lines from the error log or tool results
- FIX: exact code or steps, implementable without further research
- PREVENTION: concrete steps specific to this job and this error type

If revision instructions are provided, incorporate every point.
"""

def generate_diagnosis(error_log: str,
                       memory_context: str = "",
                       revision_instructions: str = "") -> str:

    content = f"""
MEMORY CONTEXT:
{memory_context if memory_context else "No prior memory for this job."}

CURRENT ERROR LOG:
{error_log}
"""

    if revision_instructions:
        content += f"""
REVISION INSTRUCTIONS FROM YOUR OWN REFLECTION:
{revision_instructions}

Incorporate every point above into your revised diagnosis.
"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=GENERATOR_PROMPT,
        messages=[{"role": "user", "content": content}]
    )

    return response.content[0].text

# -------------------------------------------------------
# STEP 2: THE REFLECTOR
# The model reads its own output and critiques it.
# This is the new step at Level 6.
# -------------------------------------------------------

def reflect_on_diagnosis(error_log: str,
                         diagnosis: str) -> ReflectionResult:

    content = f"""
ORIGINAL ERROR LOG:
{error_log}

YOUR DIAGNOSIS TO REFLECT ON:
{diagnosis}

Now apply the three reflection questions to your own output.
Return only the JSON structure specified.
"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=REFLECTION_PROMPT,
        messages=[{"role": "user", "content": content}]
    )

    raw = response.content[0].text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    return ReflectionResult(
        needs_revision=result.get("needs_revision", False),
        revision_instructions=result.get("revision_instructions") or "",
        gaps=[result["question_1"]["gap"]]
             if result["question_1"]["gap"] else [],
        unsupported_claims=result["question_2"].get(
            "unsupported_claims", []),
        improvements=result["question_3"].get("improvements", [])
    )

# -------------------------------------------------------
# STEP 3: THE REVISER
# Only called when reflection says needs_revision is true.
# Produces a stronger version of the original diagnosis.
# -------------------------------------------------------

def revise_diagnosis(error_log: str,
                     original_diagnosis: str,
                     reflection: ReflectionResult) -> str:

    content = f"""
ORIGINAL ERROR LOG:
{error_log}

YOUR ORIGINAL DIAGNOSIS:
{original_diagnosis}

YOUR REFLECTION IDENTIFIED THESE IMPROVEMENTS:
{reflection.revision_instructions}

Produce the revised diagnosis now.
"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=REVISION_PROMPT,
        messages=[{"role": "user", "content": content}]
    )

    return response.content[0].text

# -------------------------------------------------------
# STEP 4: THE EVALUATOR
# Same rubric as Level 5.
# Now scores a pre-reflected output rather than a raw attempt.
# -------------------------------------------------------

EVALUATION_RUBRIC = """
Score this diagnosis against four criteria.
Return JSON only, no other text.

{
  "scores": {
    "ROOT_CAUSE_IDENTIFIED": {"result": "PASS or FAIL", "reason": "..."},
    "EVIDENCE_CITED":        {"result": "PASS or FAIL", "reason": "..."},
    "ACTIONABLE_FIX":        {"result": "PASS or FAIL", "reason": "..."},
    "PREVENTION_INCLUDED":   {"result": "PASS or FAIL", "reason": "..."}
  },
  "overall": "PASS or FAIL",
  "feedback": "specific feedback for retry if overall is FAIL"
}

CRITERIA:
ROOT_CAUSE_IDENTIFIED: Names a specific technical root cause, not a category.
EVIDENCE_CITED: Every claim references specific evidence.
ACTIONABLE_FIX: Fix is implementable without further research.
PREVENTION_INCLUDED: At least one concrete prevention step specific to this job.
"""

EVALUATOR_PROMPT = f"""
You are a quality evaluator for Glue job RCA diagnoses.
Score against the rubric. Never rewrite. Only evaluate.

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

Score against all four criteria. Return only the JSON.
"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=EVALUATOR_PROMPT,
        messages=[{"role": "user", "content": content}]
    )

    raw = response.content[0].text.strip()

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
# STEP 5: THE LEVEL 6 LOOP
# Generate. Reflect. Revise if needed. Evaluate. Retry if needed.
# The reflection step is new. Everything else is Level 5.
# -------------------------------------------------------

def level6_rca(error_log: str,
               memory_context: str = "",
               max_iterations: int = 3) -> dict:

    print(f"\n[Level 6 reflective loop started]")

    previous_evaluator_feedback = ""
    history = []

    for attempt in range(1, max_iterations + 1):

        print(f"\n[Attempt {attempt}: Generating initial diagnosis...]")

        # Generate initial diagnosis
        diagnosis = generate_diagnosis(
            error_log=error_log,
            memory_context=memory_context,
            revision_instructions=previous_evaluator_feedback
        )

        print(f"[Attempt {attempt}: Reflecting on own output...]")

        # Reflect on the diagnosis
        reflection = reflect_on_diagnosis(
            error_log=error_log,
            diagnosis=diagnosis
        )

        print(f"[Reflection: needs_revision = {reflection.needs_revision}]")

        if reflection.improvements:
            for imp in reflection.improvements:
                print(f"  Improvement identified: {imp[:60]}...")

        # Revise if reflection says to
        if reflection.needs_revision and reflection.revision_instructions:
            print(f"[Attempt {attempt}: Revising based on reflection...]")
            diagnosis = revise_diagnosis(
                error_log=error_log,
                original_diagnosis=diagnosis,
                reflection=reflection
            )
            print(f"[Revision complete. Sending revised output to evaluator.]")
        else:
            print(f"[Reflection: no revision needed. Sending to evaluator.]")

        print(f"[Attempt {attempt}: Evaluating...]")

        # Evaluate the (possibly revised) diagnosis
        evaluation = evaluate_diagnosis(
            error_log=error_log,
            diagnosis=diagnosis,
            attempt=attempt
        )

        history.append({
            "attempt":    attempt,
            "diagnosis":  diagnosis,
            "reflection": reflection,
            "evaluation": evaluation
        })

        print(f"[Attempt {attempt}: Overall = {evaluation.overall}]")
        for criterion, score in evaluation.scores.items():
            symbol = "✓" if score["result"] == "PASS" else "✗"
            print(f"  {symbol} {criterion}: {score['result']}")

        if evaluation.overall == "PASS":
            print(f"\n[Passed on attempt {attempt}. Delivering.]")
            return {
                "status":    "SUCCESS",
                "diagnosis": diagnosis,
                "attempts":  attempt,
                "history":   history
            }

        previous_evaluator_feedback = evaluation.feedback
        print(f"[Evaluator feedback: {evaluation.feedback[:80]}...]")

    print(f"\n[Max iterations reached. Returning best attempt.]")
    return {
        "status":    "MAX_ITERATIONS_REACHED",
        "diagnosis": history[-1]["diagnosis"],
        "attempts":  max_iterations,
        "history":   history
    }

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
  - 2025-01-14: S3_OUTPUT_EXISTS | Fix: overwrite mode | Outcome: RESOLVED
  - 2025-01-13: S3_OUTPUT_EXISTS | Fix: overwrite mode | Outcome: RESOLVED

KNOWN PLAYBOOK FOR S3_OUTPUT_EXISTS:
  KNOWN FIX: df.write.mode("overwrite").parquet(path)
  PREVENTION: Add cleanup step at job start.
  Success rate: 100% on this error type.
"""

if __name__ == "__main__":
    print("=" * 55)
    print("LEVEL 6: The Reflective Agent")
    print("=" * 55)
    print(f"\nError log:\n{ERROR_LOG.strip()}\n")

    result = level6_rca(
        error_log=ERROR_LOG,
        memory_context=MEMORY_CONTEXT,
        max_iterations=3
    )

    print("\n" + "=" * 55)
    print(f"STATUS:   {result['status']}")
    print(f"ATTEMPTS: {result['attempts']}")
    print("=" * 55)
    print("\nFINAL DIAGNOSIS:")
    print(result["diagnosis"])
