import os
import requests

api_key=os.getenv("GROQ_API_KEY")

def groq_call(system, user):
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": 0.3,
            "max_tokens": 300
        }
    )
    return res.json()["choices"][0]["message"]["content"]

# ============================================
# AGENT ROLES — Har ek specialist
# ============================================

# Role 1: Research Agent
RESEARCH_ROLE = """
You are a Research Agent — specialist in finding information.
YOUR ONLY JOB: Research the given topic and return 3-4 key facts.
Nothing else — only research facts!
"""

# Role 2: Writer Agent  
WRITER_ROLE = """
You are a Writer Agent — specialist in writing content.
YOUR ONLY JOB: Take research and write a clear 3-4 line summary.
Nothing else — only writing!
"""

# Role 3: QA Agent
QA_ROLE = """
You are a QA Agent — specialist in quality checking.
YOUR ONLY JOB: Check the content and give 2-3 improvement suggestions.
Nothing else — only quality checking!
"""

def research_agent(topic):
    print("[Research Agent] Researching...")
    return groq_call(RESEARCH_ROLE, f"Research: {topic}")

def writer_agent(research, topic):
    print("[Writer Agent] Writing...")
    return groq_call(WRITER_ROLE, f"Topic: {topic}\nResearch: {research}")

def qa_agent(content):
    print("[QA Agent] Checking quality...")
    return groq_call(QA_ROLE, f"Check this: {content}")

# ============================================
# TEST — Har role alag kaam kare
# ============================================
topic = "AI Agents in Pakistan businesses"

print("=" * 50)
print("Testing Agent Roles")
print("=" * 50)

research = research_agent(topic)
print(f"\nResearch:\n{research}")

written = writer_agent(research, topic)
print(f"\nWritten:\n{written}")

qa = qa_agent(written)
print(f"\nQA Review:\n{qa}")