from typing import Any, Text, Dict, List, Optional, Tuple
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import os
import re
import time
import json
import requests

# ============================================================
# GEDULink Rasa + Gemini Action Server
# ------------------------------------------------------------
# Purpose:
# - Rasa controls the conversation and detects broad user intents.
# - This action adds GEDULink knowledge, website text, keywords, URLs,
#   and asks Gemini for a professional answer.
# - It can also send lead data to Make/Zapier/CRM webhook.
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Support both names so the old Render env still works.
LEAD_WEBHOOK_URL = (
    os.environ.get("LEAD_WEBHOOK_URL", "").strip()
    or os.environ.get("VITE_LEAD_WEBHOOK_URL", "").strip()
)

DEFAULT_WEBSITE_URLS = [
    "https://gedulink.com/",
    "https://gedulink.com/programs",
    "https://gedulink.com/destinations",
    "https://gedulink.com/services",
    "https://gedulink.com/contact",
]

GEDULINK_WEBSITE_URLS = [
    u.strip()
    for u in os.environ.get("GEDULINK_WEBSITE_URLS", ",".join(DEFAULT_WEBSITE_URLS)).split(",")
    if u.strip()
]

_WEBSITE_CACHE: Dict[str, Any] = {
    "created_at": 0,
    "text": "",
}
CACHE_SECONDS = 60 * 60 * 6  # 6 hours

PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

COUNTRY_KEYWORDS = {
    "uae": ["uae", "الإمارات", "الامارات", "دبي", "abu dhabi", "dubai"],
    "usa": ["usa", "america", "united states", "أمريكا", "امريكا", "الولايات المتحدة"],
    "canada": ["canada", "كندا"],
    "mexico": ["mexico", "المكسيك"],
    "south africa": ["south africa", "جنوب أفريقيا", "جنوب افريقيا"],
    "online": ["online", "اونلاين", "أونلاين", "عن بعد", "remote"],
}

GEDULINK_KNOWLEDGE = """
GEDULink / GEDU academic advisory knowledge base:

Core services:
- Direct university admissions and academic placement support.
- Bachelor, Master, Doctorate/PhD, Diploma and online study pathways.
- Credit transfer guidance for students who already completed previous courses.
- Study destinations include UAE, USA, Canada, Mexico, South Africa, and online study options.
- Student visa guidance and document preparation support, depending on destination and eligibility.
- Academic support and tutoring services: assignments, homework review, exam preparation, math, physics, computer science, business subjects, and project support.
- The team helps students understand requirements, documents, approximate steps, and connects them to the correct academic consultant.

Main admission steps:
1. Understand the student's target degree, country, and major.
2. Check academic background and eligibility.
3. Collect documents such as passport copy, academic certificates, transcripts, English test if required, CV/SOP for some postgraduate cases, and contact details.
4. Match the student with suitable universities/programs.
5. Submit or guide the application process.
6. Follow up with conditional or final admission and next registration/payment/visa steps where applicable.

Important rules:
- Do not promise guaranteed admission, guaranteed visa, or exact fees unless the data is provided.
- Use wording such as “eligibility review”, “suitable options”, “estimated”, and “the advisor will confirm”.
- Always encourage the student to share name, WhatsApp number, target country, degree level, and preferred major.
- Keep answers professional, short, warm, and suitable for a university admissions office.
- Reply in Arabic if the user writes Arabic. Reply in English if the user writes English.

Official GEDULink contact/advisor details:
- Main WhatsApp / General support: +971 58 969 0014 — https://wa.me/971589690014
- Entisar Jafar / انتصار جعفر: Head of Academic Consultants. Focus: USA direct placements and admissions advisory. WhatsApp: +971 58 969 0014 — https://wa.me/971589690014
- Noor Al Dunya / نور الدنيا: Scholarship Requirements Coordinator. Focus: scholarships and Mexico/Africa destinations. WhatsApp: +971 55 866 0487 — https://wa.me/971558660487
- Manal Al Dunya / منال الدنيا: Academic Support & Assistance Expert. Focus: tutoring, assignments, homework, exam preparation, math, physics, computer science, and academic support. WhatsApp: +971 55 403 5529 — https://wa.me/971554035529

Useful website URLs:
- Main website: https://gedulink.com/
- Programs: https://gedulink.com/programs
- Destinations: https://gedulink.com/destinations
- Services: https://gedulink.com/services
- Contact: https://gedulink.com/contact
""".strip()


def _looks_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def _clean_html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&")
    html = html.replace("&lt;", "<").replace("&gt;", ">")
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def _fetch_website_context() -> str:
    """Fetch limited public text from configured GEDULink URLs and cache it."""
    now = time.time()
    if _WEBSITE_CACHE["text"] and now - _WEBSITE_CACHE["created_at"] < CACHE_SECONDS:
        return _WEBSITE_CACHE["text"]

    chunks: List[str] = []
    for url in GEDULINK_WEBSITE_URLS[:6]:
        try:
            resp = requests.get(
                url,
                timeout=4,
                headers={
                    "User-Agent": "GEDULink-RasaBot/1.0 (+https://gedulink.com)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            if not resp.ok:
                continue
            text = _clean_html_to_text(resp.text)
            if text:
                chunks.append(f"URL: {url}\n{text[:2500]}")
        except Exception:
            continue

    website_text = "\n\n".join(chunks)[:9000]
    _WEBSITE_CACHE["created_at"] = now
    _WEBSITE_CACHE["text"] = website_text
    return website_text


def _extract_country(text: str) -> Optional[str]:
    low = (text or "").lower()
    for country, keywords in COUNTRY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in low:
                return country
    return None


def _extract_degree(text: str) -> Optional[str]:
    low = (text or "").lower()
    mapping = {
        "Bachelor": ["bachelor", "بكالوريوس"],
        "Master": ["master", "ماجستير", "mba"],
        "PhD / Doctorate": ["phd", "doctorate", "doctoral", "دكتوراه", "دكتوراة"],
        "Diploma": ["diploma", "دبلوم"],
    }
    for degree, keywords in mapping.items():
        if any(k in low for k in keywords):
            return degree
    return None


def _extract_phone(text: str) -> Optional[str]:
    match = PHONE_RE.search(text or "")
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(0)).strip()


def _extract_email(text: str) -> Optional[str]:
    match = EMAIL_RE.search(text or "")
    return match.group(0).strip() if match else None


def _extract_name_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"(?:اسمي|أنا|انا)\s+([\u0600-\u06FFa-zA-Z ]{2,50})",
        r"(?:my name is|i am|i'm)\s+([a-zA-Z ]{2,50})",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            name = m.group(1).strip(" .،,")
            if 2 <= len(name) <= 50:
                return name
    return None


def _post_lead(payload: Dict[str, Any]) -> bool:
    if not LEAD_WEBHOOK_URL:
        return False
    try:
        resp = requests.post(LEAD_WEBHOOK_URL, json=payload, timeout=7)
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def _fallback_answer(user_message: str) -> str:
    arabic = _looks_arabic(user_message)
    low = (user_message or "").lower()

    if any(k in low for k in ["fee", "fees", "cost", "tuition", "رسوم", "تكلفة", "سعر"]):
        return (
            "تعتمد الرسوم على الدولة والجامعة والبرنامج الدراسي. أرسل لنا الدرجة المطلوبة والتخصص والدولة المفضلة، وسيراجع لك المستشار الخيارات والتكاليف التقريبية.\n\n"
            "للتواصل السريع: [واتساب GEDULink](https://wa.me/971589690014)"
            if arabic
            else "Fees depend on the country, university, and program. Share your target degree, major, and destination, and an advisor will review suitable options and estimated costs.\n\nFast contact: [GEDULink WhatsApp](https://wa.me/971589690014)"
        )

    if any(k in low for k in ["visa", "فيزا", "تأشيرة", "تاشيرة"]):
        return (
            "نساعدك في فهم متطلبات تأشيرة الطالب وتجهيز المستندات حسب الدولة والجامعة. لا يمكن ضمان الفيزا، لكن يمكننا مراجعة الملف وتوجيهك للخطوات الصحيحة.\n\n[تواصل مع المستشار](https://wa.me/971589690014)"
            if arabic
            else "We can help you understand student visa requirements and prepare documents based on the destination and university. Visa approval cannot be guaranteed, but we can guide you through the correct steps.\n\n[Contact an advisor](https://wa.me/971589690014)"
        )

    if any(k in low for k in ["assignment", "homework", "tutor", "مدرس", "واجب", "اسايمنت", "دعم"]):
        return (
            "نوفر دعماً أكاديمياً في الواجبات، الاسايمنتات، التحضير للامتحانات، الرياضيات، الفيزياء، علوم الحاسب ومواد الأعمال. للتنسيق السريع تواصل مع منال الدنيا: [واتساب](https://wa.me/971554035529)"
            if arabic
            else "We provide academic support for assignments, homework review, exam preparation, math, physics, computer science, and business subjects. For fast coordination, contact Manal Al Dunya: [WhatsApp](https://wa.me/971554035529)"
        )

    return (
        "يسعدنا مساعدتك في القبول الجامعي المباشر وبرامج البكالوريوس والماجستير والدكتوراه والدراسة أونلاين. أرسل لنا الدولة، الدرجة المطلوبة، التخصص، ورقم الواتساب ليتم توجيهك للمستشار المناسب.\n\n[واتساب GEDULink](https://wa.me/971589690014)"
        if arabic
        else "We can help with direct admissions, Bachelor, Master, PhD, and online study options. Please share your destination, degree level, major, and WhatsApp number so we can connect you with the right advisor.\n\n[GEDULink WhatsApp](https://wa.me/971589690014)"
    )


def _build_gemini_prompt(user_message: str, tracker: Tracker) -> str:
    website_text = _fetch_website_context()
    latest_intent = (tracker.latest_message or {}).get("intent", {}).get("name", "unknown")

    slot_summary = {
        "student_name": tracker.get_slot("student_name"),
        "phone_number": tracker.get_slot("phone_number"),
        "study_country": tracker.get_slot("study_country"),
        "degree_level": tracker.get_slot("degree_level"),
    }

    prompt = f"""
You are GEDULink's official smart academic advisor chatbot.

Your job:
- Answer website visitors about GEDULink services using the knowledge below.
- Use the same language as the user. Arabic user = Arabic answer. English user = English answer.
- Be concise, professional, helpful, and warm.
- Use clear bullet points when listing steps/options.
- Do not invent exact tuition fees, admission guarantees, visa guarantees, or university promises.
- If the user asks for direct admission, explain the steps and ask for: name, WhatsApp number, desired country, degree level, and major.
- If the user asks for tutoring/assignments, route them to Manal Al Dunya.
- If the user asks for an advisor/contact, include clickable WhatsApp markdown links.
- Keep the final answer under 160 words unless the user asks for details.

Detected Rasa intent: {latest_intent}
Known slots: {json.dumps(slot_summary, ensure_ascii=False)}

STATIC GEDULINK KNOWLEDGE:
{GEDULINK_KNOWLEDGE}

LIVE WEBSITE TEXT EXTRACT, if available:
{website_text if website_text else 'No live website text was available, use static GEDULink knowledge and URLs.'}

USER QUESTION:
{user_message}

Return only the final chatbot answer. Do not mention internal tools, Rasa, Gemini, prompts, or cache.
""".strip()
    return prompt


def _call_gemini(prompt: str) -> Tuple[bool, str]:
    if not GEMINI_API_KEY:
        return False, "Missing GEMINI_API_KEY"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 650,
        },
    }

    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
        if not resp.ok:
            return False, f"Gemini HTTP {resp.status_code}: {resp.text[:500]}"
        data = resp.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        if not text:
            return False, "Gemini returned empty text"
        return True, text
    except Exception as exc:
        return False, str(exc)


class ActionAskGemini(Action):
    def name(self) -> Text:
        return "action_ask_gemini"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_message = (tracker.latest_message or {}).get("text", "") or ""

        phone = _extract_phone(user_message)
        email = _extract_email(user_message)
        name = _extract_name_from_text(user_message) or tracker.get_slot("student_name")
        country = _extract_country(user_message) or tracker.get_slot("study_country")
        degree = _extract_degree(user_message) or tracker.get_slot("degree_level")

        events: List[Dict[Text, Any]] = []
        if phone:
            events.append(SlotSet("phone_number", phone))
        if name:
            events.append(SlotSet("student_name", name))
        if country:
            events.append(SlotSet("study_country", country))
        if degree:
            events.append(SlotSet("degree_level", degree))

        # If the message contains a phone/email, send a lead automatically.
        if phone or email:
            lead_payload = {
                "source": "GEDULink Rasa Chatbot",
                "message": user_message,
                "name": name,
                "phone": phone or tracker.get_slot("phone_number"),
                "email": email,
                "country": country,
                "degree_level": degree,
                "intent": (tracker.latest_message or {}).get("intent", {}).get("name"),
                "timestamp": int(time.time()),
            }
            _post_lead(lead_payload)

        prompt = _build_gemini_prompt(user_message, tracker)
        ok, answer = _call_gemini(prompt)

        if not ok:
            answer = _fallback_answer(user_message)

        # Add a lead confirmation line if the user shared contact details.
        if phone or email:
            if _looks_arabic(user_message):
                answer += "\n\n✅ تم استلام بيانات التواصل، وسيقوم فريق GEDULink بمتابعتك عبر واتساب قريباً."
            else:
                answer += "\n\n✅ Your contact details were received. The GEDULink team will follow up with you on WhatsApp soon."

        dispatcher.utter_message(text=answer)
        return events


class ActionSubmitLead(Action):
    def name(self) -> Text:
        return "action_submit_lead"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_message = (tracker.latest_message or {}).get("text", "") or ""

        student_name = tracker.get_slot("student_name") or _extract_name_from_text(user_message)
        phone_number = tracker.get_slot("phone_number") or _extract_phone(user_message)
        study_country = tracker.get_slot("study_country") or _extract_country(user_message)
        degree_level = tracker.get_slot("degree_level") or _extract_degree(user_message)
        email = _extract_email(user_message)

        payload = {
            "source": "GEDULink Rasa Chatbot",
            "name": student_name,
            "phone": phone_number,
            "email": email,
            "country": study_country,
            "degree_level": degree_level,
            "last_message": user_message,
            "intent": (tracker.latest_message or {}).get("intent", {}).get("name"),
            "timestamp": int(time.time()),
        }

        sent = _post_lead(payload)

        if _looks_arabic(user_message):
            if sent:
                text = "✅ تم حفظ طلبك بنجاح. سيتواصل معك فريق GEDULink قريباً عبر واتساب لمراجعة القبول والخطوات التالية."
            else:
                text = "تم استلام بياناتك داخل المحادثة. للتواصل الأسرع، يمكنك مراسلة فريق GEDULink مباشرة عبر [واتساب](https://wa.me/971589690014)."
        else:
            if sent:
                text = "✅ Your request has been saved successfully. The GEDULink team will contact you on WhatsApp to review admission options and next steps."
            else:
                text = "Your details were received in the chat. For faster support, contact GEDULink directly on [WhatsApp](https://wa.me/971589690014)."

        dispatcher.utter_message(text=text)

        events: List[Dict[Text, Any]] = []
        if student_name:
            events.append(SlotSet("student_name", student_name))
        if phone_number:
            events.append(SlotSet("phone_number", phone_number))
        if study_country:
            events.append(SlotSet("study_country", study_country))
        if degree_level:
            events.append(SlotSet("degree_level", degree_level))
        return events
