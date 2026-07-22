"""
NACA AI Chatbot — Conversation Flow Manager

Manages structured conversation flows: onboarding with personalised welcome,
service category menus, quick actions, language selection, and exposure checker.
"""

from src.schemas.messages import (
    BotResponse, QuickReplyOption, ResponseType, SupportedLanguage,
)
import structlog

logger = structlog.get_logger()


# ── Quick Action Buttons (reduce friction — shown on welcome) ────────────────

QUICK_ACTIONS = [
    QuickReplyOption(id="action_test", title="🔬 I want to test"),
    QuickReplyOption(id="action_exposed", title="⚠️ I may have been exposed"),
    QuickReplyOption(id="action_help_now", title="🆘 I need help now"),
    QuickReplyOption(id="action_positive", title="💊 I tested positive"),
]

# ── Service Category Menu ────────────────────────────────────────────────────

SERVICE_CATEGORIES = [
    QuickReplyOption(id="cat_testing", title="🔬 Testing & Diagnosis"),
    QuickReplyOption(id="cat_prevention", title="🛡️ Prevention & Risk"),
    QuickReplyOption(id="cat_treatment", title="💊 Treatment & Care"),
    QuickReplyOption(id="cat_myths", title="📚 Myths vs Facts"),
    QuickReplyOption(id="cat_support", title="💙 Emotional Support"),
    QuickReplyOption(id="cat_referral", title="📍 Find Care Near You"),
]

# ── Language Selection ───────────────────────────────────────────────────────

LANGUAGE_OPTIONS = [
    QuickReplyOption(id="lang_en", title="English"),
    QuickReplyOption(id="lang_ha", title="Hausa"),
    QuickReplyOption(id="lang_yo", title="Yorùbá"),
    QuickReplyOption(id="lang_ig", title="Igbo"),
    QuickReplyOption(id="lang_pcm", title="Pidgin"),
]


def build_welcome_response(
    session_id: str,
    language: SupportedLanguage,
    user_name: str | None = None,
) -> BotResponse:
    """Build personalised welcome message with quick actions."""

    # Personalise greeting
    if user_name:
        greeting = f"Hi {user_name}! 👋"
    else:
        greeting = "Hello! 👋"

    text = (
        f"{greeting} Welcome, I am your *NACA HIV Support & Referral Assistant*.\n\n"
        f"I'm here to help you with information and support about HIV — "
        f"whether you have questions about testing, prevention, treatment, "
        f"or just need someone to talk to.\n\n"
        f"🔹 *What I can help you with:*\n\n"
        f"🔬 *Testing & Diagnosis*\n"
        f"   HIV testing options, self-testing, window period, where to get tested\n\n"
        f"🛡️ *Prevention & Risk Reduction*\n"
        f"   Condoms, PrEP, PEP (emergency prevention), risk assessment\n\n"
        f"💊 *Treatment & Living with HIV*\n"
        f"   ART basics, adherence, viral suppression, long-term care\n\n"
        f"📚 *Myths vs Facts*\n"
        f"   Transmission myths, cultural misconceptions, scientific facts\n\n"
        f"💙 *Emotional Support & Counselling*\n"
        f"   Post-diagnosis support, stigma management, reassurance\n\n"
        f"📍 *Find Care Near You*\n"
        f"   Facility referrals based on your location and needs, emergency PEP routing\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Everything you share is *confidential* and *judgment-free*. 💙\n\n"
        f"👇 *Tap a quick action below or type your question:*"
    )

    return BotResponse(
        response_id="welcome",
        session_id=session_id,
        text=text,
        language=language,
        response_type=ResponseType.QUICK_REPLY,
        quick_replies=QUICK_ACTIONS,
    )


def build_category_menu(
    session_id: str,
    language: SupportedLanguage,
    user_name: str | None = None,
) -> BotResponse:
    """Show the service category menu."""
    name_part = f" {user_name}" if user_name else ""
    text = (
        f"What would you like to explore{name_part}? 👇\n\n"
        f"Tap a category below:"
    )
    return BotResponse(
        response_id="category_menu",
        session_id=session_id,
        text=text,
        language=language,
        response_type=ResponseType.QUICK_REPLY,
        quick_replies=SERVICE_CATEGORIES,
    )


def build_exposure_checker_response(session_id: str, language: SupportedLanguage) -> BotResponse:
    """Exposure checker triage — routes to testing, PEP, or reassurance."""
    text = (
        "⚠️ *Exposure Checker*\n\n"
        "Let me help you figure out the best next step.\n\n"
        "When did the possible exposure happen?\n\n"
        "👇 *Tap the option that applies:*"
    )
    return BotResponse(
        response_id="exposure_checker",
        session_id=session_id,
        text=text,
        language=language,
        response_type=ResponseType.QUICK_REPLY,
        quick_replies=[
            QuickReplyOption(id="exp_within_72h", title="⏰ Within last 72 hours"),
            QuickReplyOption(id="exp_past_week", title="📅 Past week"),
            QuickReplyOption(id="exp_over_week", title="📆 Over a week ago"),
            QuickReplyOption(id="exp_not_sure", title="❓ I'm not sure"),
        ],
    )


def build_language_selection(session_id: str) -> BotResponse:
    """Prompt the user to select their language."""
    text = (
        "🌍 *Select your preferred language:*\n"
        "Jọwọ yan ede rẹ | Da fatan za a zaɓi harshenku"
    )
    return BotResponse(
        response_id="lang_select",
        session_id=session_id,
        text=text,
        language=SupportedLanguage.ENGLISH,
        response_type=ResponseType.QUICK_REPLY,
        quick_replies=LANGUAGE_OPTIONS,
    )


# ── Quick Action Handlers ────────────────────────────────────────────────────

QUICK_ACTION_PROMPTS = {
    "action_test": "I want to get tested for HIV. What are my options?",
    "action_exposed": "I think I may have been exposed to HIV recently.",
    "action_help_now": "I need help urgently. Please connect me with someone.",
    "action_positive": "I just tested positive for HIV. What should I do next?",
    "cat_testing": "Tell me about HIV testing and diagnosis options.",
    "cat_prevention": "How can I prevent HIV? Tell me about PrEP and PEP.",
    "cat_treatment": "What is ART treatment and how does it work?",
    "cat_myths": "What are common myths about HIV?",
    "cat_support": "I need emotional support about HIV.",
    "cat_referral": "Help me find an HIV facility near me.",
    "exp_within_72h": "I was possibly exposed to HIV within the last 72 hours. I need PEP urgently.",
    "exp_past_week": "I was possibly exposed to HIV about a week ago. Should I get tested?",
    "exp_over_week": "I was possibly exposed to HIV over a week ago. What should I do?",
    "exp_not_sure": "I'm not sure when I was exposed to HIV. Can you help me figure out what to do?",
}


def resolve_quick_action(text: str) -> str | None:
    """If the message is a quick action ID, return the expanded prompt."""
    return QUICK_ACTION_PROMPTS.get(text.strip())


def is_greeting_or_start(text: str) -> bool:
    """Check if the message is a greeting or start command."""
    t = text.lower().strip()
    return t in (
        "/start", "start", "hi", "hello", "hey", "menu", "help",
        "/help", "/menu", "good morning", "good afternoon", "good evening",
    )


def parse_language_selection(text: str) -> SupportedLanguage | None:
    """Parse a language selection from button reply or text."""
    t = text.lower().strip()
    mapping = {
        "lang_en": SupportedLanguage.ENGLISH, "english": SupportedLanguage.ENGLISH,
        "lang_ha": SupportedLanguage.HAUSA, "hausa": SupportedLanguage.HAUSA,
        "lang_yo": SupportedLanguage.YORUBA, "yoruba": SupportedLanguage.YORUBA,
        "lang_ig": SupportedLanguage.IGBO, "igbo": SupportedLanguage.IGBO,
        "lang_pcm": SupportedLanguage.PIDGIN, "pidgin": SupportedLanguage.PIDGIN,
    }
    return mapping.get(t)
