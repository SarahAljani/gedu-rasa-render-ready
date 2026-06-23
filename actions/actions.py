# This files contains your custom actions which can be used to run
# custom Python code during conversations.

from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import os
import requests

# Fallback AI route powered by Google Gemini API
class ActionAskGemini(Action):

    def name(self) -> Text:
        return "action_ask_gemini"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_message = tracker.latest_message.get('text', '')
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "")

        if not gemini_api_key:
            dispatcher.utter_message(text="أعتذر، خط اتصال الذكاء الاصطناعي معطل حالياً لعدم وجود المفتاح البرمجي. يرجى التواصل مع مركز الاستشارات مباشرة.")
            return []

        # Connect to Google Gemini API
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key}"
            prompt_instr = (
                "You are an academic admissions consultant for GEDULink (Direct Admissions & Student Tutors Support). "
                "Based on the query, provide a professional helpful response in Arabic (or English if they queried in English).\n\n"
                "IMPORTANT GEDULINK DIRECTORY & REFERENCE DATA:\n"
                "- General support phone line / primary WhatsApp number: +971 58 969 0014 (managed by Entisar Jafar)\n"
                "- Official Team Advisors list:\n"
                "  1. انتصار جعفر (Entisar Jafar): Head of Academic Consultants (مسؤولة الاستشاريين الأكاديميين). Specializes in USA direct placements. Phone/WhatsApp: +971 58 969 0014 (https://wa.me/971589690014). Over 4 years of guidance experience.\n"
                "  2. نور الدنيا (Noor Al Dunya): Scholarship Requirements Coordinator (مسؤولة في شروط التقديم على المنح الجامعية). Specializes in university scholarships in Mexico and Africa destinations. Phone/WhatsApp: +971 55 866 0487 (https://wa.me/971558660487). Over 2 years of experience.\n"
                "  3. منال الدنيا (Manal Al Dunya): Academic Support & Assistance Expert (خبيرة المساعدات الأكاديمية). Specializes in math/physics/CS tutoring support (assignments, homework, exam prep) and legal academic offers in European colleges. Phone/WhatsApp: +971 55 403 5529 (https://wa.me/971554035529). Over 2 years of experience.\n\n"
                "Rules:\n"
                "- If the user asks for team member details, advisor roles, or contact links, always output the authentic names, titles, and WhatsApp numbers/links above formatted in a clean, highly structured, bulleted list or numbered list! For example, bold the name and follow with the role and a clickable markdown link like [عنوان واتساب](رابط واتساب). Example: \"**انتصار جعفر**: مسؤولة الاستشاريين الأكاديميين (تواصل عبر [الواتساب المباشر](https://wa.me/971589690014))\".\n"
                "- Ensure that ANY multiple items or lists of options are formatted clearly in bullet points or numbers instead of running text.\n"
                "- Keep the response concise, short, under 4 sentences within a beautiful listed/structured format with clickable markdown links.\n\n"
                f"Query: {user_message}"
            )
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt_instr
                    }]
                }]
            }
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                bot_text = data['candidates'][0]['content']['parts'][0]['text']
                dispatcher.utter_message(text=bot_text)
            else:
                dispatcher.utter_message(text="تلقيت استفسارك بنجاح! كوني بحالة تجريبية حالياً مع مفسّر Rasa الموضعي، سأقوم فوراً بربطك مع منسقي Admissions بالمكتب لمراجعة سؤالك تفصيلياً عبر الواتساب.")
        except Exception as e:
            dispatcher.utter_message(text="سأتواصل معك فوراً لتوضيح شروط القبول الدراسي والمساقات المطلوبة.")

        return []


class ActionSubmitLead(Action):

    def name(self) -> Text:
        return "action_submit_lead"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Extract values from slots
        student_name = tracker.get_slot("student_name")
        phone_number = tracker.get_slot("phone_number")
        study_country = tracker.get_slot("study_country")

        webhook_url = os.environ.get("VITE_LEAD_WEBHOOK_URL", "")

        # Send to Zapier/Make/Hubspot webhook if configured
        if webhook_url:
            try:
                payload = {
                    "name": student_name,
                    "phone": phone_number,
                    "country": study_country,
                    "source": "Rasa Chatbot Widget"
                }
                requests.post(webhook_url, json=payload, timeout=5)
            except Exception:
                pass

        # Respond to student in registration sequence
        dispatcher.utter_message(text=f"شكرًا لك أميرنا {student_name or ''}! لقد قمت بحفظ طلبك وتعيين رغبتك في الدراسة في {study_country or 'الخارج'}. سيتواصل معك فريق admissions عبر رقم الهاتف {phone_number or ''} قريباً جداً عبر واتساب لتسليمك القبول المبدئي.")
        
        return []
