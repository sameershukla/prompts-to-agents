import anthropic
import json

client = anthropic.Anthropic(api_key="your-api-key-here")

system_prompt = """You are a senior data engineering assistant 
specializing in AWS Glue and PySpark. When given an error log, 
identify the root cause and suggest a fix. Be concise and direct."""

user_message = """
GlueException: An error occurred while calling o108.pyWriteDynamicFrame.
Output path already exists: s3://my-bucket/output/customer_data/
"""

response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    system=system_prompt,
    messages=[
        {"role": "user", "content": user_message}
    ]
)

result = response.content[0].text
print(result)
