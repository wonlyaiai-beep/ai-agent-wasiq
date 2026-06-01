import os
import requests
import json
import smtplib
import psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pinecone import Pinecone

# CONFIG
api_key=os.getenv("GROQ_API_KEY")
EMAIL = os.getenv("EMAIL")
EMAIL_PASS = os.getenv("EMAIL_PASS")

api_key=os.getenv("PINECONE_API_KEY")
index = pc.Index("glow-med")

conn = psycopg2.connect(dbname="glow_med", user="wonly.ai", password="", host="localhost")
cursor = conn.cursor()

client_state = {}

# SYSTEM PROMPT
SYSTEM_PROMPT = """
You are Sara, AI receptionist at Glow Med Clinic, Wah Cantt.
Dr. Fahim Rao — internationally trained dermatologist (USA + UK).

YOUR ROLE:
Warm, caring medical receptionist who helps patients understand 
their treatment options and book appointments.

CONVERSATION FLOW:

STEP 1 — Patient ka concern suno:
"how can i help you?"

STEP 2 STEP 2 — Pehle problem pocho, phir options batao:
Jab enough info mile THEN treatment options with benefits batao:

Format:
"Aapke concern ke liye yeh options hain:
1. [Treatment] — [benefit]
2. [Treatment] — [benefit]
3. [Treatment] — [benefit]"— Treatment options WITH benefits batao:
Format:
"Aapke concern ke liye yeh options hain:

1. [Treatment Name] — [benefit in 1 line]
2. [Treatment Name] — [benefit in 1 line]  
3. [Treatment Name] — [benefit in 1 line]

Koi bhi option ke baare mein aur jaanna chahte hain?"

STEP 3 — Agar patient recommendation maange:
"Har skin alag hoti hai — Dr. Fahim Rao aapki skin 
condition dekh kar best option recommend karenge! kia ap appointment book krna chahty hain?"
NOTHING extra— no benefits, no treatment mention!

STEP 4 — Agar patient interested ho (okay/theek/sahi bole):
"Kya aap appointment book karna chahte hain?"

STEP 5 — Agar haan bole ya intrested ho appoint book krny main to:
"Aapka naam aur email share karein — 
main appointment confirm kar deti hun!"
NOTHING extra — no benefits, no treatment mention!

STEP 6 STEP 6 — Jab email mile:
action = confirm_booking
user_reply = ONLY say:
"Shukriya [name]! Aapki appointment confirm ho gayi. 
Email bhej di hai inbox check karein!"
NOTHING else — no treatment names!

STRICT RULES:
- Max 4 lines per reply
- Treatment ke saath benefit ZAROOR batao
-khud say kabhi recomandation nai do 
- Steps skip mat karo
- Email sirf step 5 ke baad maango
- One question at a time

REPLY FORMAT — ONLY JSON:
{
    "user_reply": "max 4 lines",
    "action": "chat/ask_booking/collect_info/confirm_booking",
    "data": {
        "name": null,
        "email": null,
        "concern": null,
        "service": null
    }
}
RETURN JSON ONLY!
"""
# RAG
def search_rag(query):
    try:
        r = index.search(
            namespace="default",
            query={"top_k": 1, "inputs": {"text": query}}
        )
        text = r["result"]["hits"][0]["fields"]["text"]
        return " ".join(text.split()[:200])
    except:
        return ""

# EMAIL — Self Critique check karo pehle
def check_email_quality(name, concern, service):
    if not name or name == "null":
        return False
    if not concern or concern == "null":
        return False
    if not service or service == "null":
        return False
    return True

def send_booking_email(to, name, concern, service):
    try:
        subject = "Glow Med — Appointment Confirmation"
        body = f"""Assalam o Alaikum {name}!

Aapki appointment confirm ho gayi hai!

Appointment Details:
- Patient: {name}
- Concern: {concern}
- Recommended Service: {service}
- Clinic: Glow Med, Wah Cantt
- Doctor: Dr. Fahim Rao
- Timings: Monday-Saturday, 9AM to 5PM

Aapko appointment se pehle call aayegi timing confirm karne ke liye.
Please 10 minutes pehle aa jayein.

Koi sawal ho to:
Phone: +92-300-5556789
Email: appointments@glowmed.pk

Get well soon!
Sara
Glow Med Clinic"""

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
        return json.loads(raw[start:end])
    except:
        return {"user_reply": raw, "action": "chat", "data": {}}

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

# SELF CRITIQUE FUNCTION
def self_critique(reply, user_input):
    prompt = f"""
You are a quality checker for a medical clinic AI.

Patient asked: "{user_input}"
AI replied: "{reply}"

Check:
1. Does reply address what patient asked?
2. If treatments mentioned — are benefits also mentioned?
3. Is reply helpful and complete?

Reply with ONLY: GOOD or NEEDS_IMPROVEMENT: [specific issue]
"""
    res = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 60
        }
    )
    rjson = res.json()
    if "choices" not in rjson:
        return "GOOD"
    return rjson["choices"][0]["message"]["content"]

# MAIN AGENT
def ask(user_input):
    context = search_rag(user_input)
    history = load_memory()

    full_system = SYSTEM_PROMPT
    if context:
        full_system += f"\n\nCLINIC DATA:\n{context}"

    messages = [{"role": "system", "content": full_system}]
    messages += history
    messages.append({"role": "user", "content": user_input})

    # Step 1: Reply generate
    raw = groq_call(messages)
    if not raw:
        return "Thoda wait karo!"

    result = parse_json(raw)
    user_reply = result.get("user_reply", "")

    # Step 2: Self Critique
    critique = self_critique(user_reply, user_input)
    if "NEEDS_IMPROVEMENT" in critique:
        fix_msg = f"Your reply needs improvement: {critique}. Rewrite with treatment benefits included. Max 4 lines. Return JSON only."
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": fix_msg})
        raw = groq_call(messages)
        if raw:
            result = parse_json(raw)
            user_reply = result.get("user_reply", user_reply)

    # Step 3: State update
    data = result.get("data", {})
    action = result.get("action", "chat")

    if data.get("name"):    client_state["name"]    = data["name"]
    if data.get("email"):   client_state["email"]   = data["email"]
    if data.get("concern"): client_state["concern"] = data["concern"]
    if data.get("service"): client_state["service"] = data["service"]

    # Step 4: Email — Self Critique check
    if action == "confirm_booking" or (
        client_state.get("email") and
        client_state.get("name") and
        client_state.get("concern")
    ):
        email_ok = check_email_quality(
            client_state.get("name"),
            client_state.get("concern"),
            client_state.get("service", "General Consultation")
        )
        if email_ok:
            sent = send_booking_email(
                client_state.get("email", ""),
                client_state.get("name", ""),
                client_state.get("concern", ""),
                client_state.get("service", "General Consultation")
            )
            if sent:
                user_reply += "\n\nAppointment confirmation email bhej di! Inbox check karein."

    save_memory(user_input, user_reply)
    return user_reply

# MAIN
print("=" * 50)
print("   Glow Med Clinic — AI Assistant")
print("   Hi! I'm Sara.")
print("=" * 50)

while True:
    user_input = input("\nPatient: ")
    if user_input.lower() == "quit":
        print("\nSara: Shukriya! Get well soon!")
        break
    print(f"\nSara: {ask(user_input)}")

cursor.close()
conn.close()
