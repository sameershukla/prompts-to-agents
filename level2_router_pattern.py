import anthropic

client = anthropic.Anthropic(api_key="your-api-key-here")
# -------------------------------------------------------
# STEP 1: THE ROUTER
# A fast cheap model reads the error and returns a category.
# It does not answer the question. It only classifies.
# -------------------------------------------------------

ROUTER_PROMPT = """
You are a classifier for AWS Glue job error logs.

Read the error log and respond with exactly one of these 
category labels and nothing else:

IAM_ERROR
PYSPARK_ERROR  
DATA_QUALITY_ERROR
S3_ERROR
NOT_A_GLUE_ERROR

Respond with the label only. No explanation. No punctuation.
"""

# -------------------------------------------------------
# STEP 2: SPECIALIZED SYSTEM PROMPTS
# Each category gets its own expert prompt.
# This is why routing produces better answers.
# -------------------------------------------------------

SPECIALIZED_PROMPTS = {
    "IAM_ERROR": """
        You are an AWS IAM and permissions expert specializing 
        in Glue job execution roles. When given an error log, 
        diagnose the missing permission and provide the exact 
        IAM policy statement needed to fix it.
    """,

    "PYSPARK_ERROR": """
        You are a PySpark expert specializing in AWS Glue 
        transformations and DynamicFrames. When given an error 
        log, identify the code issue and provide a corrected 
        code snippet.
    """,

    "DATA_QUALITY_ERROR": """
        You are a data quality expert specializing in schema 
        validation, null handling, and malformed data in 
        AWS Glue pipelines. When given an error log, identify 
        the data issue and suggest both a fix and a prevention 
        strategy.
    """,

    "S3_ERROR": """
        You are an AWS S3 and Glue integration expert. When 
        given an error log, diagnose the S3 access or path 
        issue and provide the exact fix including any bucket 
        policy or path correction needed.
    """,

    "NOT_A_GLUE_ERROR": """
        You are a helpful assistant. The log provided does not 
        appear to be a Glue job error. Politely explain what 
        the log seems to contain and ask the user to provide 
        the correct Glue error log.
    """
}

# -------------------------------------------------------
# STEP 3: THE ROUTER CALL
# Small fast model. Returns a label. Nothing else.
# -------------------------------------------------------

def route_error(error_log: str) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5",       # fast and cheap for routing
        max_tokens=20,                   # we only need one label
        system=ROUTER_PROMPT,
        messages=[
            {"role": "user", "content": error_log}
        ]
    )
    category = response.content[0].text.strip()
    print(f"[Router decision: {category}]")
    return category

# -------------------------------------------------------
# STEP 4: THE SPECIALIST CALL
# Full model with the right system prompt for this category.
# -------------------------------------------------------

def call_specialist(error_log: str, category: str) -> str:
    system_prompt = SPECIALIZED_PROMPTS.get(
        category,
        SPECIALIZED_PROMPTS["NOT_A_GLUE_ERROR"]
    )
    response = client.messages.create(
        model="claude-opus-4-5",        # full model for the answer
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {"role": "user", "content": error_log}
        ]
    )
    return response.content[0].text

# -------------------------------------------------------
# STEP 5: THE FULL ROUTER PIPELINE
# Route first. Then respond. Two calls. Better answers.
# -------------------------------------------------------

def level2_rca(error_log: str) -> str:
    category = route_error(error_log)
    answer   = call_specialist(error_log, category)
    return answer


# -------------------------------------------------------
# TEST IT
# -------------------------------------------------------

ERROR_LOGS = {

    "iam": """
        AccessDeniedException: User: arn:aws:sts::123456789:
        assumed-role/GlueJobRole/session is not authorized 
        to perform: s3:GetObject on resource: 
        arn:aws:s3:::prod-bucket/config/schema.json
    """,

    "pyspark": """
        AnalysisException: Resolved attribute(s) customer_id 
        missing from age, name, email in operator Project. 
        Job: customer_transform
        Glue version: 3.0
    """,

    "data": """
        GlueException: Error in data type conversion. 
        Column order_amount contains value 'N/A' which 
        cannot be cast to DoubleType.
        Rows affected: 14,302
    """,

    "wrong": """
        NginxError: upstream timed out (110: Connection 
        timed out) while reading response header from 
        upstream, client: 10.0.1.45, server: api.internal
    """
}

if __name__ == "__main__":
    print("=" * 55)
    print("LEVEL 2: The Router Pattern")
    print("=" * 55)

    for name, log in ERROR_LOGS.items():
        print(f"\n{'=' * 55}")
        print(f"ERROR TYPE: {name.upper()}")
        print(f"LOG: {log.strip()[:80]}...")
        print(f"{'=' * 55}")
        answer = level2_rca(log)
        print(answer)
        print()
