from src.memory_system.temporal_reasoning import extract_temporal_features, extract_temporal_markers


def test_temporal_features_resolve_relative_dates_from_surface_anchor():
    text = "[4:33 pm on 12 July, 2023] Caroline: I went to an LGBTQ conference two days ago and it was really special."
    features = extract_temporal_features(text)

    assert "10 July 2023" in features.aliases
    assert "date:2023-07-10" in features.markers
    assert features.has_relative_signal is True


def test_temporal_features_capture_duration_and_anchor_year():
    text = "[9:55 am on 22 October, 2023] Caroline: A friend made it for my 18th birthday ten years ago."
    features = extract_temporal_features(text)

    assert "10 years ago" in features.aliases
    assert "2013" in features.aliases
    assert "duration:years_ago:10" in features.markers
    assert "year:2013" in features.markers


def test_temporal_markers_match_relative_answer_style():
    candidate = "[2:31 pm on 17 July, 2023] Melanie: I had a quiet weekend after we went camping with my fam two weekends ago."
    expected = "two weekends before 17 July 2023"

    candidate_markers = extract_temporal_markers(candidate)
    expected_markers = extract_temporal_markers(expected)

    assert candidate_markers & expected_markers
