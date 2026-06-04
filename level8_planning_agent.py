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
# STEP 1: CREATE THE PLAN
# The model reads the goal and produces an ordered list
# of steps. This is the key idea at Level 8.
# The agent figures out what to do. You do not hardcode it.
# -------------------------------------------------------

def create_plan(goal):
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system="""You are a planning agent for AWS Glue incidents.
Break the goal into 4 to 6 clear steps in the right order.
Each step must build on the previous one.
Return JSON only:
{"steps": ["step 1 description", "step 2 description", ...]}""",
        messages=[{"role": "user", "content": goal}]
    )
    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())["steps"]


# -------------------------------------------------------
# STEP 2: EXECUTE EACH STEP
# Each step is its own model call.
# Prior results are passed as context so each step
# builds on what the previous step found.
# This is what makes it a plan, not just a list.
# -------------------------------------------------------

def execute_step(step, prior_results):
    context = "\n".join([
        f"Step {i+1} result: {r}"
        for i, r in enumerate(prior_results)
    ])

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system="""You are executing one step of a Glue incident response.
Use prior results as context. Be specific and concise.
Your result will be used by the next step.""",
        messages=[{"role": "user", "content": f"""
PRIOR RESULTS:
{context if context else "None yet."}

CURRENT STEP:
{step}

Execute this step now.
"""}]
    )
    return response.content[0].text.strip()


# -------------------------------------------------------
# STEP 3: PRODUCE THE FINAL REPORT
# All step results are synthesised into one incident report.
# The engineer receives a full picture, not just a diagnosis.
# -------------------------------------------------------

def produce_report(goal, steps, results):
    work_done = "\n\n".join([
        f"Step {i+1}: {step}\nResult: {result}"
        for i, (step, result) in enumerate(zip(steps, results))
    ])

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system="""Write a concise incident report with:
- What failed and why
- What was affected
- What was done to fix it
- Current status""",
        messages=[{"role": "user", "content": f"GOAL:\n{goal}\n\nWORK DONE:\n{work_done}"}]
    )
    return response.content[0].text


# -------------------------------------------------------
# RUN IT
# -------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("LEVEL 8: Planning Agent")
    print("=" * 50)
    print(f"\nGoal: {GOAL.strip()}\n")

    print("[Step 1: Creating plan...]")
    steps = create_plan(GOAL)

    print(f"[Plan created: {len(steps)} steps]")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")

    results = []
    for i, step in enumerate(steps, 1):
        print(f"\n[Executing step {i}: {step[:50]}...]")
        result = execute_step(step, results)
        results.append(result)
        print(f"[Done: {result[:80]}...]")

    print("\n[Producing incident report...]")
    report = produce_report(GOAL, steps, results)

    print("\n" + "=" * 50)
    print("INCIDENT REPORT")
    print("=" * 50)
    print(report)
