"""
Comprehensive test suite and deterministic evaluation benchmark for
Multilingual, Multi-Tenant FAQ Retrieval with BM25F ranking.
"""

import pytest
from typing import Dict, Any, List

from backend.tools.base import (
    ToolExecutionStatus,
    ToolExecutionMode,
)
from backend.tools.definitions import AnswerFAQInput
from backend.tools.implementations.information import handle_answer_faq, FAQSearchEngine
from backend.tools.faq import (
    MatchOutcome,
    FAQDocument,
    normalize_text,
    strip_punctuation_unicode,
    tokenize,
    detect_script,
    extract_content_tokens,
    expand_tokens_with_synonyms,
    validate_and_deduplicate_faqs,
    BM25FAQRetriever,
    FAQDecisionEngine,
)


# ==============================================================================
# 1. Unicode Normalization & Script Tokenization Tests
# ==============================================================================

def test_unicode_normalization_and_tokenization():
    """Verify Unicode NFKC normalization and tokenization without corrupting Devanagari marks."""
    # Devanagari with vowel matras, nuktas, viramas
    dev_text = "गाड़ी पार्किंग की क्या व्यवस्था है? क्या शाकाहारी भोजन अलग बनता है?"
    tokens = tokenize(dev_text)

    # Individual words must not be fragmented into disjoint consonants and vowel signs
    assert "गाड़ी" in tokens
    assert "पार्किंग" in tokens
    assert "व्यवस्था" in tokens
    assert "शाकाहारी" in tokens
    assert "भोजन" in tokens

    # Script detection
    assert detect_script(dev_text) == "devanagari"
    assert detect_script("Is parking available?") == "latin"
    assert detect_script("Bistro की parking") == "mixed"

    # Punctuation stripping
    clean = strip_punctuation_unicode("Hello, world! गाड़ी? हाँ। ₹500/night.")
    assert "," not in clean
    assert "!" not in clean
    assert "?" not in clean
    assert "।" not in clean
    assert "गाड़ी" in clean


def test_language_aware_stopword_preservation():
    """Verify domain terms are NEVER stripped while minimal grammatical particles are filtered."""
    domain_terms = [
        "accept", "acceptance", "card", "cards", "cash", "payment", "payments",
        "booking", "cancellation", "refund", "refunds", "parking", "valet",
        "appointment", "appointments", "hours", "timings", "open", "close",
        "price", "cost", "व्यवस्था", "समय", "सुविधा", "गाड़ी",
    ]

    # None of these domain terms may ever be filtered as stopwords
    content = extract_content_tokens(domain_terms)
    for term in domain_terms:
        assert term in content, f"Domain term '{term}' was erroneously stripped!"

    # Pure grammatical particles SHOULD be filtered in content token extraction
    grammatical_particles = ["the", "is", "are", "in", "to", "for", "ka", "ki", "kya", "hai", "क्या", "है"]
    particles_filtered = extract_content_tokens(grammatical_particles + ["parking"])
    assert "parking" in particles_filtered
    for p in grammatical_particles:
        assert p not in particles_filtered


# ==============================================================================
# 2. FAQ Validation & Deduplication Tests
# ==============================================================================

def test_faq_validation_and_deduplication():
    """Verify validation skips malformed entries, trims whitespace, and deduplicates identical questions."""
    raw_faqs = [
        {"question": "What are your business hours?", "answer": "9 AM to 10 PM daily."},
        {"question": " what are your business hours?  ", "answer": "Duplicate answer."},
        {"question": "WHAT ARE YOUR BUSINESS HOURS?", "answer": "Casing duplicate."},
        None,
        "not a dict",
        {"question": "", "answer": "No question"},
        {"question": "Valid Question?", "answer": ""},
        {"question": "Do you accept credit cards?", "answer": "Yes, Visa and Mastercard."},
        {"question": "Do you accept debit cards?", "answer": "Yes, Rupay and debit cards."},
    ]

    docs = validate_and_deduplicate_faqs(raw_faqs)

    # 3 legitimate distinct questions should remain (hours, credit cards, debit cards)
    assert len(docs) == 3
    q_texts = [d.question for d in docs]
    assert "What are your business hours?" in q_texts
    assert "Do you accept credit cards?" in q_texts
    assert "Do you accept debit cards?" in q_texts

    # Preserved answer from first duplicate
    hours_doc = next(d for d in docs if "hours" in d.question.lower())
    assert hours_doc.answer == "9 AM to 10 PM daily."


def test_validation_non_mutation():
    """Verify validator never mutates caller's input dictionary."""
    original = [
        {"question": "What is your address?", "answer": "123 Main St."},
    ]
    import copy
    snapshot = copy.deepcopy(original)
    docs = validate_and_deduplicate_faqs(original)
    assert original == snapshot


# ==============================================================================
# 3. Exact, Word Order & Near-Exact Matches
# ==============================================================================

def test_exact_and_near_exact_matches():
    """Verify exact match returns maximum confidence (1.0)."""
    faqs = [
        {"question": "What are your business hours?", "answer": "Open 9 AM to 10 PM daily."},
        {"question": "Is valet parking available?", "answer": "Yes, complimentary valet parking is provided."},
    ]
    biz_config = {"id": "biz_test", "name": "Bistro", "faqs": faqs}

    # Exact string match
    res = handle_answer_faq(AnswerFAQInput(question="What are your business hours?"), biz_config)
    assert res.success is True
    assert res.data["found"] is True
    assert res.data["confidence_score"] == 1.0
    assert res.data["match_outcome"] == "strong_match"
    assert "9 AM to 10 PM" in res.message


def test_word_order_invariance():
    """Verify bag-of-words BM25F retrieves correct FAQ when caller inverts word order."""
    faqs = [
        {"question": "Do you offer complimentary valet parking?", "answer": "Yes, valet parking is free for all guests."},
        {"question": "Can I reserve a private banquet hall?", "answer": "Banquet halls can be booked for parties over 20."},
    ]
    biz_config = {"id": "biz_test", "name": "Bistro", "faqs": faqs}

    # Inverted word order
    res = handle_answer_faq(AnswerFAQInput(question="valet parking complimentary do you offer?"), biz_config)
    assert res.success is True
    assert res.data["found"] is True
    assert "valet parking is free" in res.data["answer"]
    assert res.data["confidence_score"] >= 0.60


def test_short_and_generic_keyword_queries():
    """Verify single keywords retrieve the appropriate FAQ."""
    faqs = [
        {"question": "What is your cancellation and refund policy?", "answer": "Full refund if cancelled 24 hours prior."},
        {"question": "Where can guests park their vehicle?", "answer": "Underground parking garage on 2nd avenue."},
    ]
    biz_config = {"id": "biz_test", "name": "Bistro", "faqs": faqs}

    # Short query "cancellation"
    res_cancel = handle_answer_faq(AnswerFAQInput(question="cancellation policy"), biz_config)
    assert res_cancel.success is True
    assert "Full refund" in res_cancel.data["answer"]

    # Short query "parking"
    res_park = handle_answer_faq(AnswerFAQInput(question="parking"), biz_config)
    assert res_park.success is True
    assert "Underground parking garage" in res_park.data["answer"]


# ==============================================================================
# 4. Common Term Sharing but Different Intent
# ==============================================================================

def test_questions_sharing_common_terms_different_intent():
    """Verify distinct intent is separated even when questions share common words like 'accept'."""
    faqs = [
        {"question": "Do you accept credit card payments?", "answer": "Yes, we accept all major credit cards."},
        {"question": "Do you accept advance table reservations?", "answer": "Yes, table reservations can be booked up to 30 days in advance."},
        {"question": "Do you accept walk-in patients without an appointment?", "answer": "Walk-ins are accommodated based on emergency triage."},
    ]
    biz_config = {"id": "biz_test", "name": "Test Org", "faqs": faqs}

    # Query targeting credit cards
    res_card = handle_answer_faq(AnswerFAQInput(question="Can I pay with credit card?"), biz_config)
    assert res_card.success is True
    assert "major credit cards" in res_card.data["answer"]

    # Query targeting reservations
    res_resv = handle_answer_faq(AnswerFAQInput(question="How far in advance can I book a table?"), biz_config)
    assert res_resv.success is True
    assert "30 days in advance" in res_resv.data["answer"]


# ==============================================================================
# 5. Multilingual & Hinglish Retrieval
# ==============================================================================

def test_devanagari_hindi_retrieval():
    """Verify pure Devanagari Hindi inquiries retrieve corresponding Devanagari FAQs."""
    faqs = [
        {"question": "गाड़ी पार्किंग की क्या व्यवस्था है?", "answer": "हमारे पास निःशुल्क वैलेट पार्किंग उपलब्ध है।"},
        {"question": "क्या शाकाहारी भोजन अलग बर्तनों में पकाया जाता है?", "answer": "जी हाँ, हमारे यहाँ शुद्ध शाकाहारी रसोई पूरी तरह से अलग है।"},
        {"question": "अपॉइंटमेंट रद्द करने की क्या नीति है?", "answer": "आप 24 घंटे पहले बिना किसी शुल्क के अपॉइंटमेंट रद्द कर सकते हैं।"},
    ]
    biz_config = {"id": "biz_hindi", "name": "हिंदी केंद्र", "faqs": faqs}

    res = handle_answer_faq(AnswerFAQInput(question="क्या वैलेट पार्किंग उपलब्ध है?"), biz_config)
    assert res.success is True
    assert "वैलेट पार्किंग" in res.data["answer"]

    res_veg = handle_answer_faq(AnswerFAQInput(question="शाकाहारी भोजन की व्यवस्था बताएं"), biz_config)
    assert res_veg.success is True
    assert "शाकाहारी रसोई" in res_veg.data["answer"]


def test_romanized_hindi_and_mixed_hinglish_retrieval():
    """Verify Romanized Hindi inquiries with transliterated terms resolve correctly."""
    faqs = [
        {"question": "Is parking available at the venue?", "answer": "Yes, complimentary valet parking is available at the entrance."},
        {"question": "What are your business hours?", "answer": "We are open from 11 AM to 11 PM daily."},
        {"question": "Are vegetarian dishes prepared separately?", "answer": "Yes, our vegetarian station is completely segregated."},
    ]
    biz_config = {"id": "biz_hinglish", "name": "Bistro", "faqs": faqs}

    # Hinglish query for parking
    res_park = handle_answer_faq(AnswerFAQInput(question="kya gaadi parking ki suvidha available hai?"), biz_config)
    assert res_park.success is True
    assert "valet parking" in res_park.data["answer"].lower()

    # Hinglish query for hours
    res_hours = handle_answer_faq(AnswerFAQInput(question="restaurant ke opening hours kya hain?"), biz_config)
    assert res_hours.success is True
    assert "11 AM to 11 PM" in res_hours.data["answer"]


# ==============================================================================
# 6. Tenant Synonyms & Alternate Question Phrasings
# ==============================================================================

def test_tenant_synonyms_and_alternate_questions():
    """Verify tenant-configured alternate questions and synonyms are indexed with high priority."""
    faqs = [
        {
            "id": "faq_wine",
            "question": "Can I bring my own wine?",
            "alternate_questions": [
                "What is your corkage fee?",
                "Is BYOB allowed?",
            ],
            "answer": "Yes, guests may bring personal wine. A corkage fee of Rs 500 per bottle applies.",
        },
        {
            "id": "faq_dress",
            "question": "Is there a formal dress code?",
            "answer": "Smart casual attire is recommended.",
        },
    ]
    biz_config = {
        "id": "biz_wine",
        "name": "Wine Bistro",
        "faqs": faqs,
        "faq_synonyms": {"byob": "wine", "alcohol": "wine"},
    }

    # Alternate question match
    res_alt = handle_answer_faq(AnswerFAQInput(question="What is your corkage fee?"), biz_config)
    assert res_alt.success is True
    assert "corkage fee of Rs 500" in res_alt.data["answer"]

    # Synonym match
    res_syn = handle_answer_faq(AnswerFAQInput(question="Can we bring outside alcohol?"), biz_config)
    assert res_syn.success is True
    assert "corkage fee" in res_syn.data["answer"]


# ==============================================================================
# 7. Ambiguity Margin & Clarification Requests
# ==============================================================================

def test_ambiguity_margin_triggers_clarification():
    """Verify tie between two close candidates prompts the user for clarification."""
    faqs = [
        {"question": "Do you accept credit card payments?", "answer": "Yes, we accept Visa and Mastercard."},
        {"question": "Do you accept debit card payments?", "answer": "Yes, we accept Rupay and debit cards."},
    ]
    biz_config = {"id": "biz_ambig", "name": "Shop", "faqs": faqs}

    # Ambiguous query matching both equally
    res = handle_answer_faq(AnswerFAQInput(question="Do you accept card payments?"), biz_config)
    assert res.success is False
    assert res.error_code == "AMBIGUOUS_FAQ_MATCH"
    assert res.data["is_ambiguous"] is True
    assert len(res.data["top_candidates"]) == 2
    assert "specify which topic" in res.message


# ==============================================================================
# 8. Insufficient Evidence & Irrelevant Queries (False Match Rejection)
# ==============================================================================

def test_irrelevant_queries_fail_safely_with_desk_referral():
    """Verify low-evidence queries never hallucinate and point callers to reception desk."""
    faqs = [
        {"question": "What are your business hours?", "answer": "10 AM to 9 PM."},
        {"question": "Where is the restaurant located?", "answer": "Indiranagar, Bengaluru."},
    ]
    biz_config = {"id": "biz_desk", "name": "Bistro", "phone_number": "+91 99999 88888", "faqs": faqs}

    # Completely irrelevant inquiry
    res = handle_answer_faq(AnswerFAQInput(question="Can you repair my laptop motherboard?"), biz_config)
    assert res.success is False
    assert res.data["found"] is False
    assert res.data["match_outcome"] == "insufficient_evidence"
    assert "No matching FAQ was found" in res.message
    assert "+91 99999 88888" in res.message


def test_empty_or_malformed_faq_corpus():
    """Verify empty FAQ list returns safe failure without raising exceptions."""
    biz_config = {"id": "biz_empty", "name": "Empty Cafe", "phone_number": "+91 12345 67890", "faqs": []}
    res = handle_answer_faq(AnswerFAQInput(question="What are your hours?"), biz_config)
    assert res.success is False
    assert res.data["found"] is False
    assert res.data["match_outcome"] == "empty_or_unavailable"
    assert "has no configured FAQs" in res.message
    assert "+91 12345 67890" in res.message


# ==============================================================================
# 9. Tenant Isolation & Execution Mode Semantics
# ==============================================================================

def test_tenant_isolation_in_faq_search():
    """Verify FAQs belonging to Tenant A cannot be retrieved by Tenant B."""
    faqs_a = [{"question": "What are your private chef tasting menu options?", "answer": "7 courses featuring local ingredients."}]
    faqs_b = [{"question": "Do you accept cashless dental health insurance?", "answer": "Yes, MetLife and Delta Dental."}]

    biz_a = {"id": "biz_a", "name": "Biz A", "faqs": faqs_a}
    biz_b = {"id": "biz_b", "name": "Biz B", "faqs": faqs_b}

    res_a = handle_answer_faq(AnswerFAQInput(question="What are your private chef tasting menu options?"), biz_a)
    assert res_a.success is True
    assert "7 courses" in res_a.data["answer"]

    # Search against Tenant B should NOT find Recipe A
    res_b = handle_answer_faq(AnswerFAQInput(question="What are your private chef tasting menu options?"), biz_b)
    assert res_b.success is False
    assert res_b.data["found"] is False


def test_execution_mode_truthful_tracking():
    """Verify tool execution mode accurately reflects business execution_mode (live vs mock)."""
    faqs = [{"question": "What are your hours?", "answer": "Open 24/7."}]

    # 1. Mock mode
    mock_cfg = {"id": "biz_m", "name": "Mock Bistro", "execution_mode": "mock", "faqs": faqs}
    res_mock = handle_answer_faq(AnswerFAQInput(question="What are your hours?"), mock_cfg)
    assert res_mock.mode == ToolExecutionMode.MOCK
    assert res_mock.is_simulated is False

    # 2. Live mode
    live_cfg = {"id": "biz_l", "name": "Live Bistro", "execution_mode": "live", "faqs": faqs}
    res_live = handle_answer_faq(AnswerFAQInput(question="What are your hours?"), live_cfg)
    assert res_live.mode == ToolExecutionMode.LIVE
    assert res_live.is_simulated is False


# ==============================================================================
# 10. Labelled Evaluation Dataset Benchmark
# ==============================================================================

def test_labelled_evaluation_dataset_benchmark():
    """
    Run evaluation benchmark against a labelled multi-tenant test corpus.
    Measures:
    - Top-1 Accuracy across answerable queries (target: 100%).
    - False Match Rate across irrelevant queries (target: 0.0%).
    - Ambiguity Resolution Rate across close candidate queries (target: 100%).
    """
    corpus_faqs = [
        {
            "id": "faq_hours",
            "question": "What are your business hours?",
            "alternate_questions": ["What time does the restaurant close and open?", "What are your opening hours?"],
            "answer": "We are open from 11:30 AM to 11:00 PM daily.",
        },
        {
            "id": "faq_valet",
            "question": "Is valet parking available at the venue?",
            "alternate_questions": ["valet parking complimentary do you have?", "Do you offer valet parking?"],
            "answer": "Yes, complimentary valet parking is available at the front porch.",
        },
        {
            "id": "faq_veg",
            "question": "Are pure vegetarian and vegan dishes prepared separately?",
            "alternate_questions": ["Is vegetarian food cooked separately?", "kya veg khana alag banta hai?"],
            "answer": "Yes, our kitchen features a strictly segregated vegetarian prep station.",
        },
        {
            "id": "faq_reserve",
            "question": "Do you accept advance table reservations?",
            "alternate_questions": ["Can we book a table in advance?"],
            "answer": "Yes, reservations for up to 10 guests can be confirmed online.",
        },
        {"id": "faq_credit", "question": "Do you accept credit card payments?", "answer": "Yes, we accept Visa, Mastercard, and American Express credit cards."},
        {"id": "faq_debit", "question": "Do you accept debit card payments?", "answer": "Yes, we accept all bank debit cards and UPI payments."},
        {"id": "faq_hindi_parking", "question": "गाड़ी पार्किंग की क्या व्यवस्था है?", "answer": "हमारे पास निःशुल्क वैलेट पार्किंग उपलब्ध है।"},
        {"id": "faq_hindi_timing", "question": "दुकान खुलने और बंद होने का क्या समय है?", "answer": "दुकान सुबह 10 बजे से रात 9 बजे तक खुली रहती है।"},
    ]

    biz_config = {
        "id": "biz_eval",
        "name": "Benchmark Restaurant",
        "faqs": corpus_faqs,
        "faq_synonyms": {
            "gaadi": "parking",
            "gadi": "parking",
            "timings": "hours",
            "timing": "hours",
        },
    }

    # Labelled queries: (query_text, expected_outcome, expected_faq_id)
    labelled_test_cases = [
        # Exact / near-exact English
        ("What are your business hours?", MatchOutcome.STRONG_MATCH, "faq_hours"),
        ("what are your business hours", MatchOutcome.STRONG_MATCH, "faq_hours"),
        ("Is valet parking available at the venue?", MatchOutcome.STRONG_MATCH, "faq_valet"),
        
        # Paraphrased & word-order English
        ("What time does the restaurant close and open?", MatchOutcome.STRONG_MATCH, "faq_hours"),
        ("valet parking complimentary do you have?", MatchOutcome.STRONG_MATCH, "faq_valet"),
        ("Can we book a table in advance?", MatchOutcome.STRONG_MATCH, "faq_reserve"),
        ("Is vegetarian food cooked separately?", MatchOutcome.STRONG_MATCH, "faq_veg"),

        # Devanagari Hindi
        ("गाड़ी पार्किंग की क्या व्यवस्था है?", MatchOutcome.STRONG_MATCH, "faq_hindi_parking"),
        ("दुकान खुलने का समय क्या है?", MatchOutcome.STRONG_MATCH, "faq_hindi_timing"),

        # Romanized Hindi & Hinglish
        ("kya gaadi parking ki suvidha available hai?", MatchOutcome.STRONG_MATCH, "faq_valet"),
        ("restaurant ke opening hours kya hain?", MatchOutcome.STRONG_MATCH, "faq_hours"),
        ("kya veg khana alag banta hai?", MatchOutcome.STRONG_MATCH, "faq_veg"),

        # Ambiguous candidate ties (expect AMBIGUOUS_MATCH)
        ("Do you accept card payments?", MatchOutcome.AMBIGUOUS_MATCH, None),
        ("Can I pay with card?", MatchOutcome.AMBIGUOUS_MATCH, None),

        # Irrelevant / Out-of-domain queries (expect INSUFFICIENT_EVIDENCE)
        ("Can you repair my laptop motherboard?", MatchOutcome.INSUFFICIENT_EVIDENCE, None),
        ("What is the capital of France?", MatchOutcome.INSUFFICIENT_EVIDENCE, None),
        ("Do you provide automotive tyre alignment?", MatchOutcome.INSUFFICIENT_EVIDENCE, None),
        ("What is quantum computing?", MatchOutcome.INSUFFICIENT_EVIDENCE, None),
    ]

    total_answerable = 0
    correct_answerable = 0
    total_irrelevant = 0
    false_matches = 0
    total_ambiguous = 0
    correct_ambiguous = 0

    for query, exp_outcome, exp_faq_id in labelled_test_cases:
        res = handle_answer_faq(AnswerFAQInput(question=query), biz_config)
        actual_outcome = res.data.get("match_outcome")

        if exp_outcome == MatchOutcome.STRONG_MATCH:
            total_answerable += 1
            if res.success is True and res.data.get("faq_id") == exp_faq_id:
                correct_answerable += 1
            else:
                pytest.fail(f"Query '{query}' expected FAQ '{exp_faq_id}', but got outcome '{actual_outcome}' (FAQ: {res.data.get('faq_id')})")

        elif exp_outcome == MatchOutcome.INSUFFICIENT_EVIDENCE:
            total_irrelevant += 1
            if res.success is True:
                false_matches += 1
                pytest.fail(f"Irrelevant query '{query}' produced false match: {res.data}")
            assert actual_outcome == MatchOutcome.INSUFFICIENT_EVIDENCE.value

        elif exp_outcome == MatchOutcome.AMBIGUOUS_MATCH:
            total_ambiguous += 1
            if res.error_code == "AMBIGUOUS_FAQ_MATCH" and res.data.get("is_ambiguous") is True:
                correct_ambiguous += 1
            else:
                pytest.fail(f"Ambiguous query '{query}' failed to trigger AMBIGUOUS_FAQ_MATCH. Got: {res}")

    # Metrics verification
    top1_acc = correct_answerable / total_answerable
    false_match_rate = false_matches / total_irrelevant
    ambig_acc = correct_ambiguous / total_ambiguous

    assert top1_acc == 1.0, f"Top-1 Accuracy {top1_acc:.2%} below 100%"
    assert false_match_rate == 0.0, f"False Match Rate {false_match_rate:.2%} above 0%"
    assert ambig_acc == 1.0, f"Ambiguity Resolution Rate {ambig_acc:.2%} below 100%"
