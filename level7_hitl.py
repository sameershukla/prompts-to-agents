import anthropic
import json

client = anthropic.Anthropic()

# -------------------------------------------------------
# THE ERROR LOG
# Swap this out with any Glue error you want to test.
# -------------------------------------------------------

ERROR_LOG = """
GlueException: An error occurred while calling o108.pyWriteDynamicFrame.
Output path already exists: s3://prod-bucket/output/customer_data/
Job: customer_daily_transform
Role: GlueJobExecutionRole
"""

# -------------------------------------------------------
# STEP 1: GENERATE A DIAGNOSIS
# -------------------------------------------------------

def generate(error_log):
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system="""You are a senior AWS Glue engineer.
Diagnose the error and provide:
- ROOT CAUSE
- FIX
- PREVENTION
Be specific. Cite evidence from the error log.""",
        messages=[{"role": "user", "content": error_log}]
    )
    return response.content[0].text

# -------------------------------------------------------
# STEP 2: SCORE THE DIAGNOSIS
# Returns a confidence score from 0 to 100.
# This is the only new thing Level 7 adds over Level 5.
# -------------------------------------------------------

def evaluate(error_log, diagnosis):
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system="""You are a quality evaluator.
Score this Glue RCA diagnosis from 0 to 100.

90-100: all criteria pass, evidence is specific, fix is exact
70-89:  mostly good but minor gaps remain
50-69:  some criteria weak, human review recommended
below 50: significant issues, retry needed

Return JSON only:
{
  "score": 0-100,
  "verdict": "DELIVER or ESCALATE or RETRY",
  "reason": "one sentence"
}""",
        messages=[{"role": "user", "content": f"ERROR:\n{error_log}\n\nDIAGNOSIS:\n{diagnosis}"}]
    )
    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

# -------------------------------------------------------
# STEP 3: ASK THE HUMAN
# In production this is Slack or PagerDuty.
# Here it is just input() so you can run it locally.
# -------------------------------------------------------

def ask_human(diagnosis, score):
    print("\n" + "=" * 50)
    print("HUMAN REVIEW REQUESTED")
    print(f"Confidence score: {score}/100")
    print("=" * 50)
    print(diagnosis)
    print("=" * 50)
    answer = input("\nApprove this diagnosis? (y/n): ").strip().lower()
    return answer == "y"

# -------------------------------------------------------
# THE MAIN LOOP
# Three outcomes per attempt:
#   score >= 80  -> deliver automatically
#   score 50-79  -> ask the human
#   score < 50   -> retry
# -------------------------------------------------------

def run(error_log, max_attempts=3):
    print("=" * 50)
    print("LEVEL 7: Human in the Loop RCA")
    print("=" * 50)

    for attempt in range(1, max_attempts + 1):
        print(f"\n[Attempt {attempt}: generating diagnosis...]")
        diagnosis = generate(error_log)

        print(f"[Attempt {attempt}: evaluating confidence...]")
        result = evaluate(error_log, diagnosis)

        score   = result["score"]
        verdict = result["verdict"]
        reason  = result["reason"]

        print(f"[Score: {score}/100 — {verdict} — {reason}]")

        if score >= 80:
            print("\n[High confidence. Delivering automatically.]\n")
            print(diagnosis)
            return

        if score >= 50:
            approved = ask_human(diagnosis, score)
            if approved:
                print("\n[Human approved. Delivering.]\n")
                print(diagnosis)
            else:
                print("\n[Human rejected. Closing without action.]")
            return

        print(f"[Low confidence. Retrying...]\n")

    print("\n[Max attempts reached. Escalating to human regardless.]\n")
    ask_human(diagnosis, score)

if __name__ == "__main__":
    run(ERROR_LOG)
