# From Prompt to Autonomous Agent
### Companion Repository · Sameer Shukla

> *The right level is always the lowest level that handles your problem reliably.*
> *Start there. Move up only when you have evidence that the current level is insufficient.*

---

## What This Repository Contains

This repository is the companion to the book **From Prompt to Autonomous Agent**. Every code example from every chapter is here, runnable on your local machine with one package and one API key.

The book teaches twelve levels of agentic AI systems by evolving a single running example across all twelve levels. That example is a root cause analysis system for AWS Glue job failures. At Level 1 it is a single API call. At Level 12 it is a society of five deliberating specialist agents. Same problem. Twelve architectures. One codebase that grows.

This repository mirrors that progression. You do not run twelve independent demos. You run one system that gains a new capability with every level.

```
agentic-ai-lab/
│
├── README.md                        ← you are here
├── requirements.txt                 ← one line: anthropic>=0.40.0
│
├── level1_basic_responder.py                            ← Basic Responder
├── level2_router_pattern.py                             ← Router Pattern
├── level3_tool_calling.py                               ← Tool Calling
├── level4_memory_augmented.py                           ← Memory Augmented Agent
├── level5_autonomous_pattern.py                         ← Autonomous Pattern
├── level6_reflection_pattern.py                         ← Reflective Agent
├── level7_hitl.py                                       ← Human in the Loop
├── level8_planning_agent.py                             ← Planning Agent
├── level9_multi_agent.py                                ← Multi-Agent Pattern
├── level10_tool_building_agent.py                       ← Tool-Building Agent
├── level11_hierarchical_multi_agent.py                  ← Hierarchical Multi-Agent
├── level12_society_of_agents.py                         ← Society of Agents
│
├── chapter13.py            ← Observability, guardrails, fallback chains
├── chapter14.py          ← Benchmark suite, scorer, alerter

```

Everything is at the root. No subfolders. Open any file and run it directly.

---

## How to Run the Programs

**Step 1: Install the one dependency**

```bash
pip install -r requirements.txt
```

**Step 2: Set your API key**

```bash
export ANTHROPIC_API_KEY=your-key-here
```

**Step 3: Run any level**

```bash
python level1.py
python level2.py
python level3.py
# ... and so on through level12.py
```

**Step 4: Run the side by side comparison**

```bash
python compare.py --levels 1,3,5,9
```

This is the most revealing command in the repo. It runs the same error log through multiple levels simultaneously and prints the outputs side by side. The difference in quality, specificity, and depth is visible in thirty seconds. Run this before reading Chapter 01. It shows you why twelve levels exist before you read a single explanation.

**There is nothing else to install.** No AWS account. No database. No Kubernetes. Every program in this repository runs with `anthropic` and a terminal.

---

## The Programs: Level by Level

Every program in this repository follows the same three rules the book sets out.

One file. Under a hundred lines where possible. Three functions maximum. Comments explain why, not what. The code is teaching code. Its job is to make one concept as clear as possible, not to be production-ready. Part V of the book tells you what to add when the teaching code becomes the seed of a real system.

---

### Level 1 — Basic Responder
**File:** `level1.py`

The foundation everything else is built on. One function. One API call. The engineer pastes a Glue error log. The model returns a root cause and fix from its training knowledge alone.

This program has no loops, no tools, no memory, no routing. It exists to show the simplest possible thing that works and to establish the pattern that every subsequent level extends. The system prompt is the only thing you control. The quality of the output is almost entirely determined by the quality of what you write there.

Running Level 1 also prints a list at the end: *what Level 1 cannot do*. That list is the table of contents for Levels 2 through 7.

```
What Level 1 cannot do:
  - Route IAM errors to an IAM expert       → Level 2 fixes this
  - Look up actual job history               → Level 3 fixes this
  - Remember this job from last session      → Level 4 fixes this
  - Run without a human asking               → Level 5 fixes this
  - Check its own work before delivering    → Level 6 fixes this
  - Pause before taking irreversible action  → Level 7 fixes this
```

---

### Level 2 — Router Pattern
**File:** `level2.py`

**New at this level:** `route_error()` — one function, one routing call before the main model call.

**Carries forward from Level 1:** `diagnose()` — unchanged.

A fast cheap model reads the incoming error log and returns a single category label: `IAM_ERROR`, `PYSPARK_ERROR`, `DATA_QUALITY_ERROR`, `S3_ERROR`, or `NOT_A_GLUE_ERROR`. The label determines which specialist system prompt handles the response.

The model at Level 2 is not smarter than at Level 1. The routing is smarter. An IAM error now reaches a prompt that knows about AWS policies. A PySpark error reaches a prompt that knows about dataframes. The quality improvement is free. Same model. Different starting context.

Notice the router uses `max_tokens=20`. The longest label is three tokens. Setting the budget to twenty is deliberate. Every token you do not generate is a token you do not pay for. This is the first production discipline in the book.

---

### Level 3 — Tool Calling
**File:** `level3.py`

**New at this level:** three tool definitions, `dispatch_tool()`, the tool calling loop.

**Carries forward from Level 2:** routing logic, specialist prompts.

For the first time the model reaches outside itself. Three tools are defined: `get_glue_job_history`, `check_iam_policy`, and `inspect_table_schema`. Each tool has a name, a description, and a parameter schema. The model reads the descriptions and decides when to call each tool. Your code runs them. The results come back as messages.

The core of Level 3 is the `while True` loop that continues until `stop_reason == "end_turn"`. Every iteration either calls a tool or returns the final answer. Never both. Print the raw tool call objects the first time you run this. Seeing the `tool_use` request the model sends and the `tool_result` your code returns makes the exchange concrete faster than any explanation.

The tools in this program return simulated data so no AWS credentials are needed. Swap the function bodies for real API calls when you are ready to connect real infrastructure.

---

### Level 4 — Memory Augmented Agent
**File:** `level4.py`

**New at this level:** `write_memory()`, `retrieve_episodic_memories()`, `retrieve_procedural_memory()`, `build_memory_context()`.

**Carries forward from Level 3:** tool calling loop, specialist prompts.

The model has no real memory between sessions. Level 4 builds one. After each diagnosis a memory record is written. Before the next diagnosis the relevant records are retrieved and injected into the context window ahead of the current error log.

Run this program twice on the same job. The first run has no memory. The second run reads the record from the first run. The diagnosis in Session 2 references what happened in Session 1. That is the entire Level 4 addition: context that survives session boundaries.

Two memory stores work together. A dictionary simulates a vector store for episodic and semantic memory. Another simulates a key-value store for procedural memory, the known playbook for this error type. Memory context always comes before the error log in the prompt. The model builds its understanding of the job from memory before it reads what went wrong today.

---

### Level 5 — Autonomous Pattern
**File:** `level5.py`

**New at this level:** `evaluate_diagnosis()`, the generate-evaluate loop, `simulate_eventbridge_trigger()`.

**Carries forward from Level 4:** memory retrieval and injection, `generate_diagnosis()`.

At Level 4 a human started every session. Level 5 removes that dependency. An EventBridge trigger fires when a Glue job fails. The agent runs the full loop without any engineer initiating it.

The loop is the entire Level 5 addition. `generate_diagnosis` produces an attempt. `evaluate_diagnosis` scores it against a rubric and returns `PASS` or `FAIL` with specific feedback. If it fails the feedback becomes additional context for the next attempt. Only a passing diagnosis is delivered.

A single model call produces an attempt. The loop produces a result. These are different things. Watch the token count printed on each attempt. It rises because feedback from the previous attempt is included in every retry. That rising count is the cost of quality.

---

### Level 6 — Reflective Agent
**File:** `level6.py`

**New at this level:** `reflect_on_diagnosis()`, `revise_diagnosis()`.

**Carries forward from Level 5:** the generate-evaluate loop, `evaluate_diagnosis()`.

Before the external evaluator sees the output, the same model reads its own diagnosis and asks three questions. Did I answer exactly what was asked? Is every claim supported by evidence? What would make this better? If the reflection finds problems it produces specific revision instructions. The model rewrites before the evaluator scores.

The execution order is the lesson: `generate → reflect → revise → evaluate`. At Level 5 the order was `generate → evaluate`. Two new steps appear between generation and evaluation. The evaluator at Level 6 is scoring pre-improved work. It catches what an external reader notices. The reflector already caught what an author notices about their own work.

The model is not smarter at Level 6. It is more careful. Careful applied consistently produces better outcomes than smart applied carelessly.

---

### Level 7 — Human in the Loop
**File:** `level7.py`

**New at this level:** confidence scoring in `evaluate()`, `ask_human()`, three-zone routing logic.

**Carries forward from Level 6:** reflection loop, generate and evaluate structure.

Level 7 is deliberately the simplest program in Part II. `evaluate()` now returns a score from 0 to 100 instead of a binary PASS or FAIL. Three zones determine what happens next. Score 80 or above: deliver automatically. Score 50 to 79: print the diagnosis and ask the engineer in the terminal with `input()`. Score below 50: retry.

`ask_human()` is four lines. In production those four lines become a checkpoint write to a persistent store, a Slack notification, and a polling loop. The four-line version teaches the concept. Chapter 13 tells you what to add.

The program runs interactively. When a diagnosis lands in the amber zone you see it, read the confidence score, and type `y` or `n`. That interaction is the human in the loop.

---

### Level 8 — Planning Agent
**File:** `level8.py`

**New at this level:** `create_plan()`, `execute_step()` with prior results threading, `produce_report()`.

**Carries forward from Level 7:** confidence scoring, the observable model call pattern.

At Level 8 the agent receives a goal, not an error. It decides what steps are needed, in what order, and executes them sequentially. Each step receives all prior results as context. By step four the model has seen what steps one, two, and three found. It builds on that knowledge.

Three functions. Three ideas. `create_plan` shows the model deciding what to do without being told. `execute_step` shows each step building on the previous one. `produce_report` synthesises all results into a structured incident report.

The key line is assembling accumulated context before each step. Remove it and you have five independent questions asked in sequence. Keep it and you have a plan.

---

### Level 9 — Multi-Agent Pattern
**File:** `level9.py`

**New at this level:** `SPECIALISTS` dictionary, specialist routing in `execute_step()`.

**Carries forward from Level 8:** `create_plan()`, the execution loop, `produce_report()`.

The code change between Level 8 and Level 9 is exactly one field in the plan output and one routing lookup in the executor. That is the entire multi-agent addition.

At Level 8 `execute_step` used a generic executor prompt for every step. At Level 9 it reads `step["specialist"]` from the plan and selects the matching prompt from `SPECIALISTS`. Five specialists: `pipeline`, `iam`, `pyspark`, `fix`, and `report`. Each has a system prompt tuned for one domain.

Same number of API calls as Level 8. Same latency. Better output because every step reads a prompt that tells the model exactly who it is and what it knows.

---

### Level 10 — Tool-Building Agent
**File:** `level10.py`

**New at this level:** `TOOL_REGISTRY`, `run_in_sandbox()`, `build_and_run_tool()`, `build_tool` routing in `execute_step()`.

**Carries forward from Level 9:** specialist routing, plan creation, report generation.

When the planner labels a step `"tool": "build_tool"`, the executor writes a Python function, runs it in a controlled namespace using `exec()`, reads the result, and adds the function to `TOOL_REGISTRY` for subsequent steps.

The sandbox namespace contains only `json`. No `os`, no `subprocess`, no file access. The constraint is the product. Inside the sandbox the agent has creative freedom. Outside it cannot go.

Watch the tool registry print at the end of the run. It starts with three predefined tools and ends with more. Every tool the agent builds in the session is available to every step that runs after it.

---

### Level 11 — Hierarchical Multi-Agent
**File:** `level11.py`

**New at this level:** `run_orchestrator()`, `run_domain_agent()`, three-layer communication, domain dependency scheduling.

**Carries forward from Level 10:** `run_specialist()` with the same specialist prompts from Level 9.

Three functions. Three layers. `run_orchestrator` calls `run_domain_agent` calls `run_specialist`. Each function calls the one below it and synthesises what comes back. The call chain is the hierarchy.

The orchestrator creates a cross-domain plan with three domain assignments: Glue, Snowflake, and OpenSearch. The dependency scheduling is four lines, the same logic as Level 8, now applied at the domain level. Glue and Snowflake run simultaneously. OpenSearch waits for both.

The engineer sends one goal. The program prints what each domain agent and each specialist found before producing the final platform incident report.

---

### Level 12 — Society of Agents
**File:** `level12.py`

**New at this level:** `phase1_independent_analysis()`, `phase2_share_and_challenge()`, `phase3_revise()`, `phase4_consensus()`, the deliberation loop.

**Carries forward from Level 11:** the five specialist identities, the same error log.

No hierarchy. No manager. Five agents read the same error log independently in Phase 1. In Phase 2 they share findings and challenge each other. In Phase 3 each agent revises based on all challenges. In Phase 4 a consensus evaluator determines whether the group has converged.

The one line that makes the deliberation real is `findings = revisions` at the end of each round. Agents do not reset to their original positions. They carry their evolved understanding forward. That is why the society converges.

If consensus is not reached after three rounds the program returns both a majority report and a minority report. Non-consensus is documented, not suppressed. The minority report is information, not a failure.

---

### Chapter 13 — Production Patterns
**File:** `chapter13_patterns.py`

Wraps the Level 1 RCA in the four production disciplines from Part V.

`model_call()` is the single point of instrumentation. Every model call goes through this one function. Logging, cost tracking, and error handling happen here and nowhere else. The prompt registry stores named versions. Roll back by changing one string.

The fallback chain has three levels. Primary: full RCA with the active prompt. Secondary: simpler prompt, smaller token budget. Tertiary: human escalation with full failure context. The tertiary never fails.

---

### Chapter 14 — Evaluation Pipeline
**File:** `chapter14_evaluation.py`

Three components. `BENCHMARK_SUITE`: reference inputs with expected output characteristics. `run_benchmark_suite()`: runs every benchmark through the system and scores each output using a separate model call. `check_for_alert()`: fires when the average score drops below threshold for two consecutive days.

The two-day rule prevents false alarms from noise. A single bad day does not alert. Two consecutive bad days do. Expand `BENCHMARK_SUITE` to at least fifty inputs before deploying.

---

### Chapter 15 — Decision Framework CLI
**File:** `chapter15_framework.py`

The twelve decision cards from the book as a command-line tool.

```bash
python chapter15_framework.py --level 5
python chapter15_framework.py --compare 8,9
python chapter15_framework.py --recommend
```

`--recommend` asks you five questions about your problem and suggests the lowest level that handles it reliably.

---

## The One Principle

Start at Level 1. Run it. Understand it. Move to Level 2 only when you see what Level 1 cannot do. Move to Level 3 only when you see what Level 2 cannot do.

The progression is the learning. Skipping to Level 9 because it looks more impressive produces a system you cannot debug when it breaks. Building from Level 1 produces a system you understand at every layer because you watched every layer get added.

The programs are small by design. The concepts are not.

---

## Author

**Sameer Shukla**
Director of Data and AI Architecture · Irving, Texas
[github.com/sameershukla](https://github.com/sameershukla) · [sameerbuilds.ai](https://sameerbuilds.ai)

*From Prompt to Autonomous Agent*

---

*One package. One API key. Twelve levels. Run them in order.*
