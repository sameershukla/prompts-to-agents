import anthropic
import json

client = anthropic.Anthropic()

GOAL = """
The customer_daily_transform Glue job has failed.
Diagnose the root cause, check which downstream jobs
are affected, generate fixes in the right order,
and produce a recovery plan.
"""

# -------------------------------------------------------
# THE SPECIALISTS
# Each specialist has one domain.
# One system prompt. One area of expertise.
# The manager never does this work itself.
# -------------------------------------------------------

SPECIALISTS = {
    "pipeline": """You are a pipeline specialist for AWS Glue.
You understand job dependencies, execution order, and data lineage.
When given a task, focus on pipeline topology and job relationships.
Be specific about which jobs are affected and why.""",

    "iam": """You are an IAM and permissions specialist for AWS.
You understand IAM roles, policies, and permission boundaries.
When given an access error, identify the exact missing permission
and provide the exact policy statement needed to fix it.""",

    "pyspark": """You are a PySpark expert for AWS Glue.
You understand DynamicFrames, transformations, and memory management.
When given a code error, identify the exact line and fix it
with working PySpark code.""",

    "fix": """You are a fix generation specialist for Glue incidents.
You produce exact, implementable fixes for diagnosed problems.
No vague suggestions. Exact code changes or exact AWS console steps.""",

    "report": """You are an incident report writer for data engineering teams.
You write clear, concise incident reports for technical audiences.
Structure: what failed, why, what was affected, what was done, current status."""
}

# -------------------------------------------------------
# STEP 1: CREATE THE PLAN
# Manager creates a plan and labels each step
# with the specialist type that should handle it.
# This is the only addition to the Level 8 planner.
# -------------------------------------------------------

def create_plan(goal):
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system="""You are a manager agent for AWS Glue incident response.
Break the goal into 4 to 6 steps. For each step specify:
- What needs to be done
- Which specialist should handle it (pipeline, iam, pyspark, fix, or report)

Return JSON only:
{"steps": [
  {"description": "what to do", "specialist": "which specialist"},
  ...
]}""",
        messages=[{"role": "user", "content": goal}]
    )
    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())["steps"]


# -------------------------------------------------------
# STEP 2: EXECUTE EACH STEP WITH THE RIGHT SPECIALIST
# The dispatcher reads the specialist label from the plan
# and calls the right expert for each step.
# This is the only change from Level 8.
# -------------------------------------------------------

def execute_step(step, prior_results):
    specialist_type = step["specialist"]
    description     = step["description"]

    # Pick the right expert for this step
    system_prompt = SPECIALISTS.get(
        specialist_type,
        SPECIALISTS["report"]   # safe default
    )

    context = "\n".join([
        f"Step {i+1} result: {r}"
        for i, r in enumerate(prior_results)
    ])

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": f"""
PRIOR RESULTS:
{context if context else "None yet."}

YOUR TASK:
{description}

Execute your task now. Be specific.
Your result will be used by the next specialist.
"""}]
    )
    return response.content[0].text.strip()


# -------------------------------------------------------
# STEP 3: PRODUCE THE FINAL REPORT
# Manager assembles all specialist results
# into one incident report using the report specialist.
# -------------------------------------------------------

def produce_report(goal, steps, results):
    work_done = "\n\n".join([
        f"Step {i+1} ({s['specialist']}): {s['description']}\nResult: {r}"
        for i, (s, r) in enumerate(zip(steps, results))
    ])

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=SPECIALISTS["report"],
        messages=[{"role": "user", "content": f"GOAL:\n{goal}\n\nWORK DONE:\n{work_done}"}]
    )
    return response.content[0].text


# -------------------------------------------------------
# RUN IT
# -------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("LEVEL 9: Multi-Agent Pattern")
    print("=" * 50)
    print(f"\nGoal: {GOAL.strip()}\n")

    print("[Manager creating plan with specialist assignments...]")
    steps = create_plan(GOAL)

    print(f"[Plan created: {len(steps)} steps]")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. [{step['specialist'].upper()}] {step['description']}")

    results = []
    for i, step in enumerate(steps, 1):
        specialist = step["specialist"].upper()
        print(f"\n[Step {i}: calling {specialist} specialist...]")
        result = execute_step(step, results)
        results.append(result)
        print(f"[{specialist} done: {result[:80]}...]")

    print("\n[Manager assembling final report...]")
    report = produce_report(GOAL, steps, results)

    print("\n" + "=" * 50)
    print("INCIDENT REPORT")
    print("=" * 50)
    print(report)
