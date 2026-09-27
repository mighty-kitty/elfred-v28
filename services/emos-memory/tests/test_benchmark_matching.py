from src.memory_system.benchmarks.runner import _contains_expected


def test_semantic_match_supports_official_free_form_qa():
    candidate = (
        "[4:33 pm on 12 July, 2023] Caroline: I started looking into counseling and "
        "mental health career options, so I could help other people on their journeys."
    )
    expected_hints = [
        "Psychology, counseling certification",
        "Gonna continue my edu and check out career options, which is pretty exciting!",
        "I'm keen on counseling or working in mental health - I'd love to support those with similar issues.",
    ]

    assert _contains_expected([candidate], expected_hints, semantic_match_min=2) is True


def test_temporal_match_supports_relative_time_answers():
    candidate = (
        "[2:31 pm on 17 July, 2023] Melanie: Hey Caroline, hope all's good! "
        "I had a quiet weekend after we went camping with my fam two weekends ago."
    )
    expected_hints = [
        "two weekends before 17 July 2023",
        "Hey Caroline, hope all's good! I had a quiet weekend after we went camping with my fam two weekends ago.",
    ]

    assert _contains_expected([candidate], expected_hints, semantic_match_min=0) is True


def test_inference_match_supports_supportive_and_membership_style_answers():
    candidate = "[7:55 pm on 9 June, 2023] Caroline: Thanks, Mel! Your backing really means a lot."
    supportive_expected = ["Yes, she is supportive"]
    membership_candidate = (
        "[1:33 pm on 25 August, 2023] Melanie: What made you decide to transition and join the transgender community?"
    )
    membership_expected = ["Likely no, she does not refer to herself as part of it"]

    assert _contains_expected([candidate], supportive_expected, semantic_match_min=0) is True
    assert _contains_expected([membership_candidate], membership_expected, semantic_match_min=0) is True


def test_direct_match_supports_number_word_equivalence():
    candidate = "[12:09 am on 13 September, 2023] Melanie: Seven years now, and I've finally found my real muses."
    expected_hints = ["7 years"]

    assert _contains_expected([candidate], expected_hints, semantic_match_min=0) is True
