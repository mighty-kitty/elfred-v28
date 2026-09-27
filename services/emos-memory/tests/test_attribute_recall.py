from src.memory_system.workflow import build_default_agent
from src.memory_system.object_attributes import extract_attribute_markers, infer_query_attribute_targets
from src.memory_system.retrieval_backends import expand_query_text


def test_recall_supports_object_attribute_queries():
    agent = build_default_agent()
    user_id = "pytest-attribute-user"
    session_id = "pytest-attribute-session"

    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="This necklace is special to me because it stands for love, faith and strength from my grandma in Sweden.",
    )
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What does the necklace symbolize?",
    )

    assert result.recalled_memory is not None
    assert "love, faith and strength" in result.recalled_memory.text.lower()
    assert result.retrieval_candidates[0].attribute_hits


def test_attribute_markers_ignore_image_query_tail():
    text = (
        "[1:51 pm on 15 July, 2023] Melanie: Yeah, Caroline, my family's been great. "
        "We even went on another camping trip in the forest. "
        "image: a photo of a man and two children sitting around a campfire "
        "query: family camping trip roasting marshmallows campfire"
    )

    markers = extract_attribute_markers(text)

    assert "attr:detail_activity" not in markers


def test_adoption_query_infers_specific_targets():
    targets = infer_query_attribute_targets("Why did Caroline choose the adoption agency?")

    assert "attr:agency_reason" in targets
    assert "object:agency" in targets


def test_selfcare_realization_query_infers_insight_target():
    targets = infer_query_attribute_targets("What did Melanie realize after the charity race?")

    assert "attr:selfcare_insight" in targets
    assert "speaker:melanie" in targets


def test_query_expansion_adds_adoption_reason_hints():
    expanded = expand_query_text("Why did Caroline choose the adoption agency?")

    assert "inclusive adoption" in expanded
    assert "support really spoke to me" in expanded


def test_temporal_query_infers_event_specific_target():
    targets = infer_query_attribute_targets("When did Jon and Gina decide to collaborate?")

    assert "attr:collaboration_date" in targets


def test_query_expansion_adds_temporal_event_hints():
    expanded = expand_query_text("When did John get Max?")

    assert "got max in 2013" in expanded


def test_query_infers_summary_attribute_targets():
    targets = infer_query_attribute_targets("What kind of food did Maria have on her dinner spread with her mother?")

    assert "attr:dinner_spread" in targets


def test_query_infers_convention_event_target():
    targets = infer_query_attribute_targets("What did John attend with his colleagues in March 2023?")

    assert "attr:convention_event" in targets


def test_duration_query_infers_event_object_target():
    targets = infer_query_attribute_targets("How long have Mel and her husband been married?")

    assert "obj:marriage" in targets


def test_query_infers_creative_project_target():
    targets = infer_query_attribute_targets("What creative project do Mel and her kids do together besides pottery?")

    assert "attr:creative_project_painting" in targets


def test_query_infers_memorial_reaction_target():
    targets = infer_query_attribute_targets("How did John describe his kids' reaction at the military memorial?")

    assert "attr:memorial_reaction" in targets


def test_generic_bowl_yes_no_query_infers_made_by_self():
    targets = infer_query_attribute_targets("Did Caroline make the black and white bowl in the photo?")

    assert "attr:made_by_self" in targets
    assert "object:bowl" in targets


def test_generic_instrument_query_infers_instrument_type():
    targets = infer_query_attribute_targets("What type of instrument does Caroline play?")

    assert "attr:instrument_type" in targets


def test_generic_internship_location_query_infers_location_target():
    targets = infer_query_attribute_targets("Where is Jon's HR internship?")

    assert "attr:internship_location" in targets


def test_clipboard_usage_answer_extracts_clipboard_attribute():
    markers = extract_attribute_markers(
        "I'm using it to stay organized and motivated. It sets goals, tracks my achievements and helps me find areas to improve."
    )

    assert "attr:clipboard_use" in markers


def test_book_takeaway_query_infers_book_lesson_target():
    targets = infer_query_attribute_targets('What did Caroline take away from the book "Becoming Nicole"?')

    assert "attr:book_lesson" in targets


def test_pottery_workshop_answer_extracts_artifact_type():
    markers = extract_attribute_markers("We all made our own pots, it was fun and therapeutic!")

    assert "attr:artifact_type" in markers


def test_generic_marriage_duration_query_infers_target():
    targets = infer_query_attribute_targets("How long have Mel and her husband been married?")

    assert "attr:marriage_duration" in targets


def test_generic_art_duration_query_infers_target():
    targets = infer_query_attribute_targets("How long has Melanie been creating art?")

    assert "attr:art_start_time" in targets


def test_pet_name_list_extracts_identity_list_attribute():
    markers = extract_attribute_markers("Luna and Oliver are my cats, and Bailey is my dog.")

    assert "attr:pet_identity_list" in markers


def test_recent_paint_query_infers_painting_sunset_target():
    targets = infer_query_attribute_targets("What did Melanie paint recently?")

    assert "attr:painting_sunset" in targets


def test_singular_pet_query_does_not_force_pet_list_target():
    targets = infer_query_attribute_targets("What pet does Caroline have?")

    assert "attr:pet_identity" in targets
    assert "attr:pet_identity_list" not in targets


def test_counseling_motivation_query_infers_specific_target():
    targets = infer_query_attribute_targets("What motivated Caroline to pursue counseling?")

    assert "attr:counseling_motivation" in targets


def test_road_trip_relax_query_infers_trip_relaxation_target():
    targets = infer_query_attribute_targets("What did Melanie do after the road trip to relax?")

    assert "attr:trip_relaxation" in targets


def test_education_field_query_infers_counseling_focus_target():
    targets = infer_query_attribute_targets("What fields would Caroline be likely to pursue in her educaton?")

    assert "attr:counseling_focus" in targets


def test_charity_race_awareness_query_infers_activity_benefit_target():
    targets = infer_query_attribute_targets("What did the charity race raise awareness for?")

    assert "attr:activity_benefit" in targets


def test_pride_festival_when_query_infers_specific_time_target():
    targets = infer_query_attribute_targets("When did Caroline and Melanie go to a pride fesetival together?")

    assert "attr:pride_festival_time" in targets


def test_seen_music_artist_query_infers_specific_target():
    targets = infer_query_attribute_targets("What musical artists/bands has Melanie seen?")

    assert "attr:seen_music_artist" in targets


def test_personality_traits_query_infers_summary_target():
    targets = infer_query_attribute_targets("What personality traits might Melanie say Caroline has?")

    assert "attr:personality_summary" in targets


def test_church_hiking_query_infers_specific_target():
    targets = infer_query_attribute_targets("In what activity did Maria and her church friends participate in July 2023?")

    assert "attr:church_hiking" in targets


def test_community_work_query_infers_specific_target():
    targets = infer_query_attribute_targets("What activity did Maria take up with her friends from church in August 2023?")

    assert "attr:community_work" in targets


def test_volunteer_role_school_query_infers_target():
    targets = infer_query_attribute_targets("What is John currently doing as a volunteer in August 2023?")

    assert "attr:volunteer_role_school" in targets


def test_library_frequency_query_infers_target():
    targets = infer_query_attribute_targets("How often does John take his kids to the library?")

    assert "attr:library_frequency" in targets


def test_run_cause_query_infers_target_even_with_maria_wording():
    targets = infer_query_attribute_targets("What cause did the 5K charity run organized by Maria support?")

    assert "attr:run_cause" in targets


def test_turtles_duration_query_infers_target():
    targets = infer_query_attribute_targets("How long has Nate had his first two turtles?")

    assert "attr:turtles_duration" in targets


def test_late_slice_completion_query_infers_screenplay_target():
    targets = infer_query_attribute_targets("What major achievement did Joanna accomplish in January 2022?")

    assert "attr:screenplay_completion" in targets


def test_late_slice_waterfall_query_infers_specific_location_target():
    targets = infer_query_attribute_targets("Which outdoor spot did Joanna visit in May?")

    assert "attr:waterfall_name" in targets
