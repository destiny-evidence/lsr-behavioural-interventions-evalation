# Created by Lennart at 28/10/2026

import os

# For example, to check if AZURE_API_KEY was loaded:
azure_api_key = os.getenv('AZURE_API_KEY')
azure_api_base = os.getenv('AZURE_API_BASE')
azure_api_base_reduced = azure_api_base[:-9]
azure_api_key_anthropic = os.getenv('ANTHROPIC_FOUNDRY_API_KEY')
azure_api_base_anthropic = os.getenv('AZURE_API_BASE_ANTHROPIC')

print(f"AZURE_API_KEY loaded: { 'Yes' if azure_api_key else 'No' }")
if azure_api_key:
    print(f"First 5 characters of AZURE_API_KEY: {azure_api_key[:5]}...")
print(f"AZURE_API_BASE loaded: { 'Yes' if azure_api_base else 'No' }")
if azure_api_base:
    print(f"AZURE_API_BASE: {azure_api_base}")
    print(f"reduced AZURE_API_BASE: {azure_api_base_reduced}")
print(f"AZURE_API_BASE_ANTHROPIC loaded: { 'Yes' if azure_api_base_anthropic else 'No' }")
if azure_api_base_anthropic:
    print(f"AZURE_API_BASE_ANTHROPIC: {azure_api_base_anthropic}")

# print("----- DIRECT OPENAI INTERFACE -----")
# from openai import OpenAI
#
# client = OpenAI(
#     # This is the default and can be omitted
#     api_key=os.environ.get("AZURE_API_KEY"),
#     base_url=os.environ.get("AZURE_API_BASE"),
# )
#
# response = client.responses.create(
#     model="gpt-5.6-luna",
#     instructions="You greet people in a funny way",
#     input="Hello! How are you?",
# )
#
# print(response.output_text)

print("----- DSPY LM INTERFACE -----")

import dspy


# AZURE_API_BASE is the Azure "v1" endpoint (.../openai/v1), which is OpenAI-compatible.
# LiteLLM's "azure/" provider builds legacy .../openai/deployments/<model>/... URLs
# against it (-> 404), so route through the "openai/" provider instead.

# 'OpenAI'
LM = "openai/gpt-5.6-luna"
lm = dspy.LM(LM, max_tokens=5000, api_key=azure_api_key, api_base=azure_api_base)
#
# print(azure_api_base_reduced)
# LM = "azure/gpt-5.6-luna"
# lm = dspy.LM(LM, max_tokens=5000, api_key=azure_api_key, api_base=azure_api_base_reduced, api_version="v1")

# 'Anthropic - NOT WORKING YET'
# LM = "anthropic/claude-sonnet-5"
# lm = dspy.LM(LM, max_tokens=5000, api_key=azure_api_key_anthropic, api_base=azure_api_base_anthropic)

dspy.configure(lm=lm)

messages = [
    {
        "role": "system",
        "content": "You are a helpful assistant"
    },
    {
        "role": "user",
        "content": "What is the capital of France?"
    }
]

print(lm(messages = messages))