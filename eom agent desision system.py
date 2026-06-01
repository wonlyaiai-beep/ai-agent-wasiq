import os
import requests
import json
import smtplib
import psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pinecone import Pinecone

# ============================================
# CONFIG
# ============================================
api_key=os.getenv("GROQ_API_KEY")
FROM_EMAIL = "wasiq3910@gmail.com"
EMAIL_PASS = "bztb qsjh xmax sjyt"

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

# ============================================
# SYSTEM PROMPT — Full Agentic Prompting
# ============================================
SYSTEM_PROMPT = """
You are Adam, Senior Property Consultant at EOM Real Estate, Islamabad.
You are warm, professional, and genuinely helpful like a trusted friend.

ROLE:
Help clients find their perfect property in Islamabad.
Listen carefully, understand their needs, suggest best options,
and book viewing appointments.

PLANNING — Before every reply think:
1. ANALYZE: What did client say? What info do I have? What is missing?
2. PLAN: What is the best next step right now?
3. EXECUTE: Do that one thing — max 3 lines
4. REFLECT: Was my reply helpful? Anything missing? Fix if needed!

DECISION FRAMEWORK — Make smart decisions yourself:
- Client just arrived = Greet warmly + ask property type
- Property type known, no budget = Ask budget
- Budget known, no location = Ask location  
- All info collected = Suggest 2-3 matching properties with prices
- Client likes a property = Ask if they want to schedule viewing
- Client wants viewing = Ask name + email
- Name + email received = action must be "confirm_booking"
- Client is unsure = Give more details + reassure
- Client asks question = Answer from property data first

TOOL USAGE:
- RAG data is available — always use it for accurate property info
- Always mention prices when suggesting properties
- Email is sent automatically when action = confirm_booking

SELF CRITIQUE — Before sending reply check:
- Is my reply relevant to what client asked?
- If suggesting properties — are prices included?
- Is reply max 3 lines?
- Am I making the right decision for this moment?
- If any answer is NO — rewrite!

CONVERSATION STYLE:
- Warm Urdu/English mix
- Max 3 lines per reply
- One question at a time
- Never rush — listen first
- Be confident in your decisions

INTERNAL JSON FORMAT — return this only:
{
    "user_reply": "clean warm text for client — max 3 lines",
    "action": "chat/suggest_properties/ask_viewing/collect_info/confirm_booking",
    "data": {
        "name": null,
        "email": null,
        "property_type": null,
        "budget": null,
        "location": null,
        "property": null
    }
}
STRICT: Return JSON only — never show JSON to client!
"""

# ============================================
# RAG — Property Knowledge Base
# ============================================
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
    except Exception as e:
        print(f"[RAG Error]: {e}")
        return ""

# ============================================
# SELF CRITIQUE — Reply Quality Check
# ============================================
def self_critique(reply, user_input):
    prompt = f"""
Check this real estate agent reply:
Client said: "{user_input}"
Agent replied: "{reply}"

Check:
1. Is reply relevant to what client asked?
2. If properties mentioned — are prices included?
3. Is reply max 3 lines?
4. Is decision appropriate for this situation?

Reply ONLY: GOOD or NEEDS_IMPROVEMENT: reason
"""
    try:
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
    except:
        return "GOOD"

# ============================================
# EMAIL — Quality Check Before Sending
# ============================================
def check_email_data(name, email, property_type):
    if not name or name == "null" or name == "None":
        return False
    if not email or email == "null" or email == "None":
        return False
    if not property_type or property_type == "null" or property_type == "None":
        return False
    return True

def send_confirmation_email(to, name, property_type, budget, location, prop):
    try:
        subject = "EOM Real Estate — Viewing Appointment Confirmed!"
        body = f"""Assalam o Alaikum {name}!

Aapki property viewing appointment confirm ho gayi!

Appointment Details:
- Property Type: {property_type}
- Budget: {budget if budget else 'As discussed'}
- Preferred Location: {location if location else 'Islamabad'}
- Property: {prop if prop else 'As discussed'}

Hamara consultant aapko 24 hours mein call karega
timing confirm karne ke liye.

Koi bhi sawal ho:
Phone: +92-300-1112233
Email: info@eomrealestate.pk
Office: Blue Area, Islamabad

Shukriya EOM Real Estate choose karne ke liye!

Best Regards,
Adam
EOM Real Estate, Islamabad"""

        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(FROM_EMAIL, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[Email Error]: {e}")
        return False

# ============================================
# MEMORY — Long Term
# ============================================
def save_memory(user_msg, agent_reply):
    try:
        cursor.execute(
            "INSERT INTO memory (user_message, agent_reply) VALUES (%s, %s)",
            (user_msg, agent_reply)
        )
        conn.commit()
    except Exception as e:
        print(f"[Memory Error]: {e}")

def load_memory():
    try:
        cursor.execute(
            "SELECT user_message, agent_reply FROM memory "
            "ORDER BY created_at DESC LIMIT 6"
        )
        rows = cursor.fetchall()
        history = []
        for row in reversed(rows):
            history.append({"role": "user", "content": row[0]})
            history.append({"role": "assistant", "content": row[1]})
        return history
    except:
        return []

# ============================================
# JSON PARSER — Clean + Reliable
# ============================================
def parse_json(raw):
    try:
        raw = raw.strip()
        # Markdown backticks hata do
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        # JSON block extract karo
        start = raw.index("{")
        end = raw.rindex("}") + 1
        result = json.loads(raw[start:end])
        # Reply 3 lines tak limit karo
        reply = result.get("user_reply", "")
        lines = [l.strip() for l in reply.split("\n") if l.strip()]
        result["user_reply"] = "\n".join(lines[:3])
        return result
    except:
        # Agar JSON fail — clean text return karo
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        clean = "\n".join(lines[:3])
        return {
            "user_reply": clean,
            "action": "chat",
            "data": {}
        }

# ============================================
# GROQ API CALL
# ============================================
def groq_call(messages, max_tokens=400):
    try:
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
            print(f"[Groq Error]: {rjson}")
            return None
        return rjson["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[Groq Error]: {e}")
        return None

# ============================================
# MAIN AGENT
# ============================================
def ask(user_input):
    # RAG se context lo
    context = search_rag(user_input)
    history = load_memory()

    # System prompt + context
    full_system = SYSTEM_PROMPT
    if context:
        full_system += f"\n\nPROPERTY DATA:\n{context}"

    # Messages banao
    messages = [{"role": "system", "content": full_system}]
    messages += history
    messages.append({"role": "user", "content": user_input})

    # Step 1: Reply generate karo
    raw = groq_call(messages)
    if not raw:
        return "Thoda wait karo — dobara try karein!"

    result = parse_json(raw)
    user_reply = result.get("user_reply", "")
    action = result.get("action", "chat")
    data = result.get("data", {})

    # Step 2: Self Critique — reply check karo
    critique = self_critique(user_reply, user_input)
    if "NEEDS_IMPROVEMENT" in critique:
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": f"Improve your reply. Issue: {critique}. Keep max 3 lines. Return JSON only."
        })
        raw2 = groq_call(messages)
        if raw2:
            result2 = parse_json(raw2)
            if result2.get("user_reply"):
                result = result2
                user_reply = result.get("user_reply", user_reply)
                action = result.get("action", action)
                data = result.get("data", data)

  # Step 3: Client state update karo
    if data.get("name"):          client_state["name"]          = data["name"]
    if data.get("email"):         client_state["email"]         = data["email"]
    if data.get("property_type"): client_state["property_type"] = data["property_type"]
    if data.get("budget"):        client_state["budget"]        = data["budget"]
    if data.get("location"):      client_state["location"]      = data["location"]
    if data.get("property"):      client_state["property"]      = data["property"]

    # Step 4: Email — quality check phir bhejo
    if action == "confirm_booking":
        email_ok = check_email_data(
            client_state.get("name"),
            client_state.get("email"),
            client_state.get("property_type")
        )
        if email_ok:
            sent = send_confirmation_email(
                client_state.get("email", ""),
                client_state.get("name", ""),
                client_state.get("property_type", ""),
                client_state.get("budget", ""),
                client_state.get("location", "Islamabad"),
                client_state.get("property", "")
            )
            if sent:
                user_reply += "\n\nViewing confirmation email bhej di! Inbox check karein."

    # Step 5: Memory mein save karo
    save_memory(user_input, user_reply)
    return user_reply

# ============================================
# MAIN
# ============================================
print("=" * 52)
print("   EOM Real Estate — Property Consultant")
print("   Assalam o Alaikum! Main Adam hun.")
print("=" * 52)

while True:
    user_input = input("\nClient: ")
    if user_input.lower() == "quit":
        print("\nAdam: Shukriya! Jab zaroorat ho wapas aana!")
        break
    print(f"\nAdam: {ask(user_input)}")

cursor.close()
conn.close()
