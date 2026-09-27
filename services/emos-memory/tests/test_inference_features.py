from src.memory_system.inference_features import (
    compute_inference_bonus,
    extract_inference_markers,
    extract_query_subject,
)


def test_inference_markers_capture_supportive_stance():
    text = "[7:55 pm on 9 June, 2023] Caroline: Thanks, Mel! Your backing really means a lot."
    markers = extract_inference_markers(text)

    assert "stance:ally_supportive" in markers


def test_inference_bonus_prefers_nonmember_signal_for_membership_question():
    query = "Would Melanie be considered a member of the LGBTQ community?"
    candidate = (
        "[1:33 pm on 25 August, 2023] Melanie: Thanks, Caroline! I really appreciate your help and motivation. "
        "What made you decide to transition and join the transgender community?"
    )

    assert compute_inference_bonus(query, candidate) > 0.8


def test_inference_bonus_prefers_supportive_memory_for_ally_question():
    query = "Would Melanie be considered an ally to the transgender community?"
    candidate = "[7:55 pm on 9 June, 2023] Caroline: Thanks, Mel! Your backing really means a lot."

    assert compute_inference_bonus(query, candidate) > 0.9


def test_extract_query_subject_handles_auxiliary_after_object_phrase():
    subject = extract_query_subject("What pet does Caroline have?")

    assert subject == "Caroline"


def test_inference_bonus_prefers_counseling_over_generic_exploration_for_writing_counterfactual():
    query = "Would Caroline pursue writing as a career option?"
    candidate = "[10:37 am on 27 June, 2023] Caroline: I'm looking into counseling and mental health as a career."

    assert compute_inference_bonus(query, candidate) > 0.9


def test_inference_markers_capture_personality_signals():
    markers = extract_inference_markers("[12:09 am on 13 September, 2023] Melanie: You're so thoughtful and your drive to help is awesome!")

    assert "personality:thoughtful" in markers
    assert "personality:driven" in markers


def test_inference_bonus_prefers_bad_roadtrip_memory_for_repeat_question():
    query = "Would Melanie go on another roadtrip soon?"
    candidate = "[6:55 pm on 20 October, 2023] Melanie: That roadtrip this past weekend was insane. Our trip got off to a bad start and it was a real scary experience. Thankfully it's over now."

    assert compute_inference_bonus(query, candidate) > 0.9
