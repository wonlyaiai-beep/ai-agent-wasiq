import os
import requests
import json
import smtplib
import psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pinecone import Pinecone

# CONFIG
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EMAIL = os.getenv("EMAIL")
EMAIL_PASS = os.getenv("EMAIL_PASS")

api_key=os.getenv("PINECONE_API_KEY")
index = pc.Index("eom-realestate")

conn = psycopg2.connect(
    dbname="eom_realestate",
    user="wonly.ai",
    password="",
    host="localhost"
)
cursor = conn.cursor()

client_state = {}

# SYSTEM PROMPT — Agentic Prompting
SYSTEM_PROMPT = """
You are Adam, Senior Property Consultant at EOM Real Estate, Islamabad.
You are warm, professional, and genuinely helpful.

PLANNING — Before every reply think:
1. ANALYZE: What did client say? What info do I have? What is missing?
2. PLAN: What step am I on? What should I ask or suggest?
3. EXECUTE: Reply based on plan — one thing at a time
4. REFLECT: Was my reply helpful? Did I address concern? Anything missing?

CONVERSATION FLOW — follow in ORDER:
Step 1: Greet warmly — ask property type (buy/rent/sell?)
Step 2: Ask budget range
Step 3: Ask preferred location in Islamabad
Step 4: Suggest 2-3 matching properties from our data with prices
Step 5: Ask if they want to schedule a viewing
Step 6: If yes — ask name + email
Step 7: Send confirmation email — action = confirm_booking

AGENTIC RULES:
- Always plan before replying
- Reflect after every reply
- Never skip steps
- Never ask 2 questions at once
- Max 3 lines per reply
- Warm Urdu/English mix

SELF CRITIQUE — before sending reply:
- Did I follow the correct step?
- Is my reply helpful and relevant?
- Did I suggest properties with prices?
- Is reply short enough?
If any = NO — rewrite!

TOOLS:
- Use RAG data to suggest accurate properties with prices
- Use email to send viewing confirmation

INTERNAL FORMAT — return JSON only:
{
    "user_reply": "clean text for client — max 3 lines",
    "action": "chat/ask_budget/ask_location/suggest_properties/ask_viewing/collect_info/confirm_booking",
    "data": {
        "name": null,
        "email": null,
        "property_type": null,
        "budget": null,
        "location": null,
        "property": null
    }
}
RETURN JSON ONLY — never show JSON to client!
"""

# RAG
def search_rag(query):
    try:
        r = index.search(
            namespace="default",
            query={"top_k": 2, "inputs": {"text": query}}
        )
        context = ""
        for hit in r["result"]["hits"]:
            context += hit["fields"]["text"] + "\n"
        return " ".join(context.split()[:200])
    except:
        return ""

# SELF CRITIQUE
def self_critique(reply, user_input):
    prompt = f"""
Check this real estate agent reply:
Client said: "{user_input}"
Agent replied: "{reply}"

Check:
1. Is reply relevant to what client asked?
2. If properties suggested — are prices included?
3. Is reply max 3 lines?
4. Is it helpful?

Reply ONLY: GOOD or NEEDS_IMPROVEMENT: reason
"""
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 80
        }
    )
    rjson = res.json()
    if "choices" not in rjson:
        return "GOOD"
    return rjson["choices"][0]["message"]["content"]

# EMAIL CHECK
def check_email_data(name, email, property_type, location):
    if not name or name == "null": return False
    if not email or email == "null": return False
    if not property_type or property_type == "null": return False
    return True

# SEND EMAIL
def send_email(to, name, property_type, budget, location, prop):
    try:
        subject = "EOM Real Estate — Viewing Appointment Confirmation"
        body = f"""Assalam o Alaikum {name}!

Aapki viewing appointment confirm ho gayi!

Details:
- Property Type: {property_type}
- Budget: {budget}
- Location: {location}
- Property: {prop}

Hamara consultant aapko call karega timing confirm karne ke liye.

EOM Real Estate
+92-300-1112233 | info@eomrealestate.pk
Blue Area, Islamabad"""

        msg = MIMEMultipart()
        msg['From'] = EMAIL
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[Email Error]: {e}")
        return False

# MEMORY
def save_memory(u, a):
    cursor.execute(
        "INSERT INTO memory (user_message, agent_reply) VALUES (%s, %s)", (u, a)
    )
    conn.commit()

def load_memory():
    cursor.execute(
        "SELECT user_message, agent_reply FROM memory ORDER BY created_at DESC LIMIT 6"
    )
    rows = cursor.fetchall()
    history = []
    for row in reversed(rows):
        history.append({"role": "user", "content": row[0]})
        history.append({"role": "assistant", "content": row[1]})
    return history

# JSON PARSE
def parse_json(raw):
    try:
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        start = raw.index("{")
        end = raw.rindex("}") + 1
        result = json.loads(raw[start:end])
        # Reply 3 lines limit
        reply = result.get("user_reply", "")
        lines = [l.strip() for l in reply.split("\n") if l.strip()]
        result["user_reply"] = "\n".join(lines[:3])
        return result
    except:
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        return {
            "user_reply": "\n".join(lines[:3]),
            "action": "chat",
            "data": {}
        }

# GROQ CALL
def groq_call(messages, max_tokens=400):
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": max_tokens
        }
    )
    rjson = res.json()
    if "choices" not in rjson:
        return None
    return rjson["choices"][0]["message"]["content"]

# MAIN AGENT
def ask(user_input):
    # RAG
    context = search_rag(user_input)
    history = load_memory()

    full_system = SYSTEM_PROMPT
    if context:
        full_system += f"\n\nPROPERTY DATA:\n{context}"

    messages = [{"role": "system", "content": full_system}]
    messages += history
    messages.append({"role": "user", "content": user_input})

    # Step 1: Generate reply
    raw = groq_call(messages)
    if not raw:
        return "Thoda wait karo!"

    result = parse_json(raw)
    user_reply = result.get("user_reply", "")

    # Step 2: Self Critique
    critique = self_critique(user_reply, user_input)
    if "NEEDS_IMPROVEMENT" in critique:
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": f"Improve reply: {critique}. Max 3 lines. Return JSON only."
        })
        raw2 = groq_call(messages)
        if raw2:
            result2 = parse_json(raw2)
            if result2.get("user_reply"):
                result = result2
                user_reply = result.get("user_reply", user_reply)

    # Step 3: State update
    data = result.get("data", {})
    action = result.get("action", "chat")

    if data.get("name"):          client_state["name"]          = data["name"]
    if data.get("email"):         client_state["email"]         = data["email"]
    if data.get("property_type"): client_state["property_type"] = data["property_type"]
    if data.get("budget"):        client_state["budget"]        = data["budget"]
    if data.get("location"):      client_state["location"]      = data["location"]
    if data.get("property"):      client_state["property"]      = data["property"]

    # Step 4: Email — check quality first
    if action == "confirm_booking" or (
        client_state.get("email") and
        client_state.get("name") and
        client_state.get("property_type")
    ):
        ok = check_email_data(
            client_state.get("name"),
            client_state.get("email"),
            client_state.get("property_type"),
            client_state.get("location", "Islamabad")
        )
        if ok:
            sent = send_email(
                client_state.get("email", ""),
                client_state.get("name", ""),
                client_state.get("property_type", ""),
                client_state.get("budget", ""),
                client_state.get("location", "Islamabad"),
                client_state.get("property", "Property")
            )
            if sent:
                user_reply += "\n\nViewing confirmation email bhej di! Inbox check karein."

    save_memory(user_input, user_reply)
    return user_reply

# MAIN
print("=" * 50)
print("   EOM Real Estate — Adam")
print("   Assalam o Alaikum! Kaise madad kar sakta hun?")
print("=" * 50)

while True:
    user_input = input("\nClient: ")
    if user_input.lower() == "quit":
        print("\nAdam: Shukriya! Jab zaroorat ho wapas aana!")
        break
    print(f"\nAdam: {ask(user_input)}")

cursor.close()
conn.close()