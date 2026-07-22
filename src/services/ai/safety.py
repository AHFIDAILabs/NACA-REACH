"""
Safety Classifier — Post-generation response validation.

Checks LLM output for harmful, stigmatising, or clinically unsafe content
before dispatching to the user. See: Section 3.1.2 (Response Validation)
"""

import re

import structlog

logger = structlog.get_logger()

# Patterns that indicate unsafe content
STIGMA_PATTERNS = [
    r"\bHIV victim\b",
    r"\bAIDS patient\b",
    r"\bsuffer(?:s|ing)? from (?:HIV|AIDS)\b",
    r"\bHIV infected\b",
    r"\bclean\b.*\btest",  # "clean test" is stigmatising
    r"\bdirty\b.*\bblood\b",
    r"\bplagued?\b",
    r"\bcontaminated\b",
]

# Content that should never appear in responses
BLOCKED_PATTERNS = [
    r"(?i)your (?:phone|name|address|email) (?:is|number)",  # PII solicitation
    r"(?i)(?:cure|cured) (?:for |of )?(?:HIV|AIDS)",  # False cure claims
    r"(?i)guaranteed? (?:to )?(?:work|cure|heal)",
    r"(?i)(?:don't|do not) (?:need|have to) (?:see|visit) (?:a )?doctor",
    r"(?i)stop (?:taking|your) (?:medication|ART|ARV|treatment)",
]

# Medical advice that requires human review
CLINICAL_ESCALATION_PATTERNS = [
    r"(?i)(?:take|start|switch|change|stop) (?:this |your )?(?:medication|drug|ART|ARV)",
    r"(?i)(?:dosage|dose) (?:should be|is) \d+",
    r"(?i)(?:you have|you are|diagnosed with) (?:HIV|AIDS|TB)",
]


class SafetyClassifier:
    """
    Validates LLM responses against safety rules before dispatch.

    Returns (is_safe, flags) where:
    - is_safe: True if the response can be sent to the user
    - flags: List of safety concerns found (empty if safe)
    """

    async def check_response(self, response_text: str) -> tuple[bool, list[str]]:
        """Run all safety checks on the generated response."""
        flags = []

        # Check for stigmatising language
        for pattern in STIGMA_PATTERNS:
            if re.search(pattern, response_text, re.IGNORECASE):
                flags.append(f"stigma_detected: {pattern}")

        # Check for blocked content
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, response_text):
                flags.append(f"blocked_content: {pattern}")

        # Check for unsupported clinical advice
        for pattern in CLINICAL_ESCALATION_PATTERNS:
            if re.search(pattern, response_text):
                flags.append(f"clinical_advice_detected: {pattern}")

        # Check response length (too short may indicate error)
        if len(response_text.strip()) < 10:
            flags.append("response_too_short")

        is_safe = len(flags) == 0

        if not is_safe:
            logger.warning(
                "safety_flags_detected",
                flag_count=len(flags),
                flags=flags[:3],  # Log first 3 flags
            )

        return is_safe, flags
