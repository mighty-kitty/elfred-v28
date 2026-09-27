from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from uuid import uuid4
import re

from ..config import AppConfig
from ..content_cleaning import extract_core_content
from ..inference_features import extract_inference_markers
from ..object_attributes import extract_attribute_markers
from ..retrieval_assets import load_semantic_aliases, load_stop_tokens
from ..retrieval_backends import tokenize
from ..temporal_reasoning import extract_temporal_markers
from ..utils.io import write_json
from ..workflow import build_default_agent
from .base import BenchmarkResult
from .datasets import load_all_benchmarks


CANONICAL_BACKENDS = ("lexical", "semantic", "hybrid", "embedding_rerank", "embedding_no_rerank")
MATCHING_ALIASES = load_semantic_aliases()
MATCHING_STOP_TOKENS = load_stop_tokens()
MATCH_NORMALIZE_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")
MATCH_SALIENT_STOP_TOKENS = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "in",
    "on",
    "at",
    "for",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "it",
    "its",
    "my",
    "your",
    "his",
    "her",
    "their",
    "our",
    "he",
    "she",
    "they",
    "them",
    "we",
    "i",
    "me",
    "this",
    "that",
    "these",
    "those",
}
NUMBER_WORD_MAP = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}
PRECISE_ATTRIBUTE_MATCHERS = {
    "attr:activity_purpose",
    "attr:activity_benefit",
    "attr:selfcare_method",
    "attr:made_by_self",
    "attr:gift_object",
    "attr:adoption_excitement",
    "attr:counseling_focus",
    "attr:drawing_meaning",
    "attr:pet_location",
    "attr:sky_event",
    "attr:accident_event",
    "attr:accident_response",
    "attr:family_support",
    "attr:family_importance",
    "attr:poster_text",
    "attr:sign_text",
    "attr:instrument_type",
    "attr:classical_musicians",
    "attr:poetry_reading_content",
    "attr:book_lesson",
    "attr:coping_activity",
    "attr:pet_identity_list",
    "attr:festival_attitude",
    "attr:dance_destress",
    "attr:studio_reason",
    "attr:dance_style",
    "attr:dance_memory",
    "attr:dance_piece_title",
    "attr:festival_photo_meaning",
    "attr:festival_photo_comment",
    "attr:store_design",
    "attr:store_feedback",
    "attr:customer_experience",
    "attr:journey_comparison",
    "attr:business_advice",
    "attr:dance_effect",
    "attr:contest_award",
    "attr:internship_type",
    "attr:internship_location",
    "attr:dancer_support",
    "attr:clipboard_use",
    "attr:icecream_opinion",
    "attr:trip_reason",
    "attr:store_status",
    "attr:business_motivation",
    "attr:bank_account_reason",
    "attr:family_activity_list",
    "attr:mentor_quality",
    "attr:business_plan_actions",
    "attr:social_media_offer",
    "attr:store_item_line",
    "attr:grand_opening_message",
    "attr:grand_opening_sentiment",
    "attr:temp_job",
    "attr:studio_description",
    "attr:opening_night_feeling",
    "attr:dance_feeling",
    "attr:opening_plan",
    "attr:service_activity_list",
    "attr:volunteer_inspiration",
    "attr:castle_origin",
    "attr:volunteer_event",
    "attr:roadtrip_location",
    "attr:politics_focus",
    "attr:school_funding_effect",
    "attr:shelter_reason",
    "attr:hardship_history",
    "attr:office_reason",
    "attr:certificate_reason",
    "attr:veteran_hospital_appreciation",
    "attr:wallet_strain",
    "attr:fundraiser_keyword",
    "attr:education_infra_reason",
    "attr:family_meal",
    "attr:dinner_spread",
    "attr:dinner_activity",
    "attr:park_frequency",
    "attr:workout_frequency",
    "attr:fitness_improvement",
    "attr:live_event_type",
    "attr:picnic_activity_list",
    "attr:veteran_values",
    "attr:dinner_companion",
    "attr:yoga_pose_feeling",
    "attr:military_inspiration",
    "attr:puppy_gap",
    "attr:family_support_feeling",
    "attr:new_class_opinion",
    "attr:convention_event",
    "attr:friend_group_duration",
    "attr:tattoo_symbolism",
    "attr:console_switch",
    "attr:favorite_movie",
    "attr:sponsorship_deals",
    "attr:hp_fan_reconnect_duration",
    "attr:uk_castle_trip",
    "attr:seattle_game_city",
    "attr:surfing_feeling",
    "attr:skype_hp_topics",
    "attr:teammate_reunion_date",
    "attr:signed_basketball_reason",
    "attr:nyc_experience",
    "attr:nyc_pitch",
    "attr:universal_harry_potter",
    "attr:team_trip_destination_type",
    "attr:team_trip_suggestion",
    "attr:post_basketball_plan",
    "attr:endorsement_advice",
    "attr:trip_book_recommendation",
    "attr:wedding_venue",
    "attr:team_supported_wolves",
    "attr:season_summary",
    "attr:team_growth_driver",
    "attr:season_award",
    "attr:smoky_mountains_photo",
    "attr:mentoring_player_outcome",
    "attr:writing_inspiration_author",
    "attr:slow_cooker_meal",
    "attr:recipe_sharing_method",
    "attr:lebron_inspiration_specific",
    "attr:study_motivation_method",
    "attr:injury_update",
    "attr:yoga_hold_duration",
    "attr:recent_finished_book",
    "attr:travel_agency_visit",
    "attr:youth_sports_cause",
    "attr:favorite_book_series_hp",
    "attr:aragorn_identity",
    "attr:aragorn_reason",
    "attr:middle_earth_map",
    "attr:ireland_city_galway",
    "attr:benefit_basketball_game",
    "attr:endorsement_reaction",
    "attr:barcelona_recommendation",
    "attr:forum_type_fantasy",
    "attr:restaurant_celebration_game",
    "attr:online_mag_articles",
    "attr:harry_potter_trivia_event",
    "attr:aragorn_reason_identity",
    "attr:aragorn_identity_exact",
    "attr:restaurant_celebration_aftermath",
    "attr:sponsorship_deal_types",
    "attr:leader_reminder",
    "attr:signed_basketball_gift",
    "attr:book_conference_reason",
    "attr:piano_learning",
    "attr:fantasy_connects_people",
    "attr:writing_reading_motivation",
    "attr:yoga_recovery_training",
    "attr:violin_learning",
    "attr:career_high_assists_game",
    "attr:sage_soup_flavor",
    "attr:thanksgiving_tradition",
    "attr:study_motivation_visualization",
    "attr:stress_coping_basketball",
    "attr:photoshoot_forest_location",
    "attr:training_growth_area",
    "attr:seminar_topic",
    "attr:language_german",
    "attr:fantasy_tv_series_wot",
    "attr:big_game_atmosphere",
    "attr:basketball_origin",
    "attr:thanksgiving_movie",
    "attr:novel_genre_fantasy",
    "attr:piano_duration_four_months",
    "attr:first_three_dogs_year",
    "attr:neighbor_goodies",
    "attr:dogs_snow_confusion",
    "attr:dog_hiking_trails",
    "attr:hiking_plan",
    "attr:indoor_dog_toys",
    "attr:dog_mental_stimulation",
    "attr:hike_next_month_august",
    "attr:cook_dog_treats",
    "attr:camping_with_girlfriend",
    "attr:remote_suburb_plan",
    "attr:toby_buddy_gap",
    "attr:andrew_pets_december",
    "attr:andrew_pets_september",
    "attr:buddy_scout_gap",
    "attr:first_pet_duration_november",
    "attr:positive_training_reason",
    "attr:positive_training_type",
    "attr:dog_walk_duration_hour",
    "attr:roasted_chicken",
    "attr:dog_personality_list",
    "attr:agility_classes",
    "attr:park_practice_frequency",
    "attr:grooming_advice",
    "attr:dog_beds_comfy",
    "attr:leash_incident_calming",
    "attr:dog_walk_frequency",
    "attr:peruvian_lilies",
    "attr:ecosystem_lesson",
    "attr:biking_planet",
    "attr:favorite_trilogy",
    "attr:favorite_book_theme",
    "attr:gaming_room_lighting",
    "attr:favorite_video_game",
    "attr:tournament_game",
    "attr:state_indiana",
    "attr:screenplay_genre",
    "attr:teaching_skills",
    "attr:movie_genre_action_scifi",
    "attr:book_project_timeline",
    "attr:cake_frosting",
    "attr:whispering_falls_writing",
    "attr:tilly_origin",
    "attr:rejection_response",
    "attr:resilience_respect",
    "attr:rejection_advice",
    "attr:character_visuals_purpose",
    "attr:letter_object",
    "attr:homemade_coconut_icecream",
    "attr:thriller_project",
    "attr:video_motivation",
    "attr:video_advice",
    "attr:hangout_plan",
    "attr:colorful_bowls_icecream",
    "attr:letter_reaction",
    "attr:favorite_trilogy",
    "attr:writers_group_project",
    "attr:writing_club_bookmark",
    "attr:thriller_project",
    "attr:vegan_icecream_shared",
    "attr:writers_group_celebration",
    "attr:tournament_chill_celebration",
    "attr:pet_help_offer",
    "attr:tournament_game_apex",
    "attr:adopted_pet_type",
    "attr:adopted_pup_name",
    "attr:visited_country_italy",
    "attr:snake_names_list",
    "attr:yoga_support_mom_attended",
    "attr:first_console_nintendo",
    "attr:favorite_game_monster_hunter",
    "attr:task_method_eisenhower",
    "attr:retreat_location_phuket",
    "attr:retreat_focus_present",
    "attr:retreat_outcome_peace",
    "attr:gardening_class_free",
    "attr:mom_birthday_cakes",
    "attr:cookie_type_choc_chip",
    "attr:event_music_dance",
    "attr:healthy_snack_suggestions",
    "attr:grocery_issue_self_checkout",
    "attr:health_issue_weight",
    "attr:health_issue_gastritis",
    "attr:roadtrip_locations_rockies_jasper",
    "attr:favorite_novel_gatsby",
    "attr:fitness_tracker_use",
    "attr:bonsai_reason",
    "attr:lost_keys_problem",
    "attr:healthy_cooking_class",
    "attr:healthy_grilled_dish",
    "attr:healthy_food_photo_bowl",
    "attr:watercolor_class_type",
    "attr:favorite_painting_subject",
    "attr:injury_exercise_swimming",
    "attr:writing_hobby_creative",
    "attr:phone_issue_navigation",
    "attr:activity_weightlifting",
    "attr:kayaking_location_tahoe",
    "attr:gift_vintage_guitar",
    "attr:island_memory_happy_place",
    "attr:family_reunion_plan",
    "attr:family_motto",
    "attr:exhibition_support_friend",
    "attr:painting_feeling_joy_freedom",
    "attr:painting_process_unrestrained",
    "attr:diet_limit_ginger_snaps",
    "attr:winter_activity_snowshoeing",
    "attr:exercise_low_impact_list",
    "attr:movie_godfather",
    "attr:camping_photo_kayak",
    "attr:marriage_announcement",
    "attr:necklace_reminder",
    "attr:fixing_things_purpose",
    "attr:skiing_plan",
    "attr:electronic_fresh_vibe",
    "attr:ferrari_brand",
    "attr:car_mod_workshop",
    "attr:workshop_modifications",
    "attr:workshop_car_type",
    "attr:rap_industry_podcast",
    "attr:video_location_miami",
    "attr:guitar_octopus_design",
    "attr:guitar_shiny_reason",
    "attr:guitar_purple_glow",
    "attr:workshop_city_sf",
    "attr:repair_relief_proud",
    "attr:flight_to_boston",
    "attr:favorite_disney_ratatouille",
    "attr:song_california_love",
    "attr:junkyard_ford_mustang",
    "attr:restoration_satisfaction",
    "attr:car_therapy",
    "attr:car_passion_goal",
    "attr:favorite_band_fireworks",
    "attr:tokyo_times_square",
    "attr:tokyo_shinjuku",
    "attr:tokyo_ramen",
    "attr:early_age_cars",
    "attr:music_purpose_realization",
    "attr:japanese_house_party",
    "attr:car_mod_blog",
    "attr:car_mod_blog_share",
    "attr:tv_music_content",
    "attr:classic_rock_interest",
    "attr:vintage_camera_item",
    "attr:diy_blog_inspiration",
    "attr:old_friend_boston_invite",
    "attr:camera_nature_photos",
    "attr:gala_artist_topics",
    "attr:waterfall_nearby_park",
    "attr:setback_motivation",
    "attr:fixing_fulfilling",
    "attr:tour_energizing",
    "attr:balance_one_day",
    "attr:music_emotion_therapy",
    "attr:restoration_detail",
    "attr:extraordinary_small_details",
    "attr:shared_fulfilling_motivating",
    "attr:photo_city_boston",
    "attr:lyrics_notes_motivation",
    "attr:photography_hobby",
    "attr:jumpstart_inspiration",
    "attr:open_car_shop",
    "attr:park_relaxation",
    "attr:back_on_the_road",
    "attr:park_regular_walks",
    "attr:genre_experimentation",
    "attr:global_brand_goal",
    "attr:dream_advice_keep",
    "attr:workshop_mod_details",
    "attr:small_details_unique",
    "attr:meet_frank_tokyo_festival",
    "attr:mansion_studio_song",
    "attr:orange_car_project",
    "attr:hard_work_determination",
    "attr:childhood_artists",
    "attr:dad_nostalgia",
    "attr:october_boston",
    "attr:shared_car_work",
    "attr:favorite_activity_restoring",
    "attr:car_show_october",
    "attr:garage_childhood_work",
    "attr:frank_collab_start",
    "attr:cities_traveled_dave",
    "attr:photography_october",
    "attr:auto_engineering_origins",
    "attr:mustang_duration",
    "attr:sf_workshop_duration",
    "attr:projects_not_smooth",
    "attr:late_october_tokyo",
    "attr:gift_artist_list",
    "attr:march_purchases",
    "attr:bands_dave_likes",
    "attr:meet_country_usa",
    "attr:dave_dreams",
    "attr:dave_car_types_favorite",
    "attr:calvin_mishaps",
    "attr:performing_live_soul",
    "attr:insurance_two_times",
    "attr:tokyo_places_list",
    "attr:august_miami",
    "attr:calvin_relaxation_mix",
    "attr:dave_other_hobbies",
    "attr:muscle_car_preference",
}
SOFT_ATTRIBUTE_MATCHERS = {
    "attr:adoption_excitement",
    "attr:customer_experience",
    "attr:grand_opening_sentiment",
    "attr:family_support_feeling",
    "attr:certificate_reason",
    "attr:housing_urgency",
    "attr:military_inspiration",
    "attr:veteran_hospital_appreciation",
    "attr:friend_group_duration",
}


def _build_runtime_config(backend_name: str) -> AppConfig:
    config = AppConfig()
    config.log_level = "WARNING"
    runtime_id = f"{backend_name}_{uuid4().hex[:8]}"
    runtime_dir = config.paths.data_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    config.paths.memory_file = runtime_dir / f"benchmark_{runtime_id}.json"
    config.paths.sqlite_file = runtime_dir / f"benchmark_{runtime_id}.sqlite3"
    return config


def run_benchmarks(
    backend_name: str | None = None,
    extra_benchmark_roots: list[Path] | None = None,
    benchmark_ids: list[str] | None = None,
    max_samples: int | None = None,
    consolidate_history: bool = True,
) -> dict[str, object]:
    active_backend = backend_name or "hybrid"
    config = _build_runtime_config(active_backend)
    retrieval_settings_override = None
    if backend_name:
        retrieval_settings_override = {"backend": backend_name}
    agent = build_default_agent(config=config, retrieval_settings_override=retrieval_settings_override)
    benchmarks_dir = config.paths.data_dir / "benchmarks"
    samples, manifests = load_all_benchmarks(benchmarks_dir, extra_roots=extra_benchmark_roots)
    if benchmark_ids:
        allowed = set(benchmark_ids)
        samples = [sample for sample in samples if sample.benchmark in allowed]
        manifests = {name: manifest for name, manifest in manifests.items() if name in allowed}
    if max_samples is not None:
        samples = samples[:max_samples]
    results: list[BenchmarkResult] = []
    active_backend = backend_name or agent.repository.retrieval_backend_name

    for sample in samples:
        scoped_user_id = f"{sample.user_id}-{sample.sample_id}"
        scoped_session_id = f"{sample.session_id}-{sample.sample_id}"
        for history_turn in sample.history:
            agent.ingest_history_turn(
                user_id=scoped_user_id,
                session_id=scoped_session_id,
                text=history_turn,
            )
        if consolidate_history:
            agent.consolidate_session(user_id=scoped_user_id, session_id=scoped_session_id, persist=False)

        result = agent.process_turn(
            user_id=scoped_user_id,
            session_id=scoped_session_id,
            text=sample.query_text,
            persist=False,
        )
        recalled = result.recalled_memory.text if result.recalled_memory else None
        ranked_texts = [candidate.text for candidate in result.retrieval_candidates]
        ranked_surfaces = [candidate.surface_text for candidate in result.retrieval_candidates]
        semantic_match_min = int(sample.metadata.get("semantic_match_min", 0))
        hit_at_1 = _contains_expected(ranked_surfaces[:1], sample.expectation.memory_hints, semantic_match_min)
        hit_at_3 = _contains_expected(ranked_surfaces[:3], sample.expectation.memory_hints, semantic_match_min)
        matched_rank = _matched_rank(ranked_surfaces, sample.expectation.memory_hints, semantic_match_min)
        reciprocal_rank = (1.0 / matched_rank) if matched_rank else 0.0
        meets_target_rank = bool(matched_rank and matched_rank <= sample.expectation.target_rank_max)
        top_score = result.retrieval_candidates[0].score if result.retrieval_candidates else 0.0
        error_category = None if hit_at_3 else _classify_error(sample)
        results.append(
            BenchmarkResult(
                backend=active_backend,
                benchmark=sample.benchmark,
                sample_id=sample.sample_id,
                split=sample.split,
                task=str(sample.metadata.get("task", "unknown")),
                difficulty=str(sample.metadata.get("difficulty", "standard")),
                hit_at_1=hit_at_1,
                hit_at_3=hit_at_3,
                reciprocal_rank=reciprocal_rank,
                matched_rank=matched_rank,
                meets_target_rank=meets_target_rank,
                target_rank_max=sample.expectation.target_rank_max,
                top_score=top_score,
                recalled_text=recalled,
                expected_memory_hints=sample.expectation.memory_hints,
                recalled_surface_text=ranked_surfaces[0] if ranked_surfaces else None,
                conversation_key=str(sample.metadata.get("conversation_index", sample.session_id)),
                error_category=error_category,
            )
        )

    summary = build_summary(results, backend_name=active_backend)
    summary["dataset_manifests"] = manifests
    write_json(config.paths.logs_dir / "benchmark_results.json", summary)
    write_json(config.paths.logs_dir / "benchmark_detailed_results.json", [asdict(item) for item in results])
    _write_markdown_report(config.paths.logs_dir / "benchmark_report.md", summary)
    return summary


def _semantic_match(candidate: str, expected_hints: list[str], min_overlap: int) -> bool:
    if min_overlap <= 0:
        return False
    candidate_tokens = set(tokenize(candidate, MATCHING_ALIASES, MATCHING_STOP_TOKENS))
    expected_tokens = set(tokenize(" ".join(expected_hints), MATCHING_ALIASES, MATCHING_STOP_TOKENS))
    if not candidate_tokens or not expected_tokens:
        return False
    overlap = candidate_tokens & expected_tokens
    return len(overlap) >= min_overlap


def _normalize_match_text(text: str) -> str:
    lowered = extract_core_content(text).lower()
    lowered = lowered.replace("’", "'").replace("“", '"').replace("”", '"')
    for word, digit in NUMBER_WORD_MAP.items():
        lowered = re.sub(rf"\b{word}\b", digit, lowered)
    lowered = MATCH_NORMALIZE_RE.sub(" ", lowered)
    return " ".join(lowered.split())


def _direct_match(candidate: str, expected_hints: list[str]) -> bool:
    normalized_candidate = _normalize_match_text(candidate)
    candidate_tokens = set(normalized_candidate.split())
    if not normalized_candidate:
        return False
    for hint in expected_hints:
        normalized_hint = _normalize_match_text(hint)
        if not normalized_hint:
            continue
        if normalized_hint in normalized_candidate:
            return True
        if len(normalized_candidate) >= 18 and normalized_candidate in normalized_hint:
            return True
        hint_tokens = set(normalized_hint.split())
        if hint_tokens and hint_tokens.issubset(candidate_tokens):
            return True
        if len(hint_tokens) >= 3 and candidate_tokens and candidate_tokens.issubset(hint_tokens):
            return True
        salient_hint_tokens = {
            token for token in hint_tokens if token not in MATCH_SALIENT_STOP_TOKENS and len(token) >= 3
        }
        salient_candidate_tokens = {
            token for token in candidate_tokens if token not in MATCH_SALIENT_STOP_TOKENS and len(token) >= 3
        }
        if len(salient_hint_tokens) >= 2 and salient_hint_tokens.issubset(salient_candidate_tokens):
            return True
    return False


def _attribute_match(candidate: str, expected_hints: list[str]) -> bool:
    candidate_markers = set(extract_attribute_markers(candidate)) & PRECISE_ATTRIBUTE_MATCHERS
    expected_markers = set(extract_attribute_markers(" ".join(expected_hints))) & PRECISE_ATTRIBUTE_MATCHERS
    if not candidate_markers or not expected_markers:
        return False
    return bool(candidate_markers & expected_markers)


def _soft_attribute_match(candidate: str, expected_hints: list[str]) -> bool:
    candidate_markers = set(extract_attribute_markers(candidate)) & SOFT_ATTRIBUTE_MATCHERS
    expected_markers = set(extract_attribute_markers(" ".join(expected_hints))) & SOFT_ATTRIBUTE_MATCHERS
    if not candidate_markers or not expected_markers:
        return False
    return bool(candidate_markers & expected_markers)


def _yes_no_match(candidate: str, expected_hints: list[str]) -> bool:
    normalized_hints = [hint.strip().lower() for hint in expected_hints if hint.strip()]
    if not normalized_hints:
        return False
    expected_values = {hint for hint in normalized_hints if hint in {"yes", "no"}}
    if not expected_values:
        return False
    lowered = _normalize_match_text(candidate)
    if not lowered:
        return False
    negative_cues = (" no ", " not ", " never ", " didn't ", " wasnt ", " wasn't ", " dont ", " don't ")
    if "yes" in expected_values:
        return not any(cue in f" {lowered} " for cue in negative_cues)
    return any(cue in f" {lowered} " for cue in negative_cues)


def _temporal_match(candidate: str, expected_hints: list[str]) -> bool:
    candidate_markers = {
        marker
        for marker in extract_temporal_markers(candidate)
        if marker.startswith(("date:", "month:", "year:", "duration:", "relative:", "relative_anchor:"))
    }
    expected_markers = {
        marker
        for marker in extract_temporal_markers(" ".join(expected_hints))
        if marker.startswith(("date:", "month:", "year:", "duration:", "relative:", "relative_anchor:"))
    }
    if not candidate_markers or not expected_markers:
        return False
    overlap = candidate_markers & expected_markers
    return bool(overlap)


def _inference_match(candidate: str, expected_hints: list[str]) -> bool:
    candidate_markers = extract_inference_markers(candidate)
    expected_markers = extract_inference_markers(" ".join(expected_hints))
    if not candidate_markers or not expected_markers:
        return False
    return bool(candidate_markers & expected_markers)


def _contains_expected(candidates: list[str], expected_hints: list[str], semantic_match_min: int = 0) -> bool:
    for candidate in candidates:
        if _direct_match(candidate, expected_hints):
            return True
        if _yes_no_match(candidate, expected_hints):
            return True
        if _attribute_match(candidate, expected_hints):
            return True
        if _soft_attribute_match(candidate, expected_hints):
            return True
        if _inference_match(candidate, expected_hints):
            return True
        if _temporal_match(candidate, expected_hints):
            return True
        if _semantic_match(candidate, expected_hints, semantic_match_min):
            return True
    return False


def _matched_rank(candidates: list[str], expected_hints: list[str], semantic_match_min: int = 0) -> int | None:
    for index, candidate in enumerate(candidates, start=1):
        if _direct_match(candidate, expected_hints):
            return index
        if _yes_no_match(candidate, expected_hints):
            return index
        if _attribute_match(candidate, expected_hints):
            return index
        if _soft_attribute_match(candidate, expected_hints):
            return index
        if _inference_match(candidate, expected_hints):
            return index
        if _temporal_match(candidate, expected_hints):
            return index
        if _semantic_match(candidate, expected_hints, semantic_match_min):
            return index
    return None


def build_summary(results: list[BenchmarkResult], backend_name: str | None = None) -> dict[str, object]:
    total = len(results)
    summary = {
        "backend": backend_name or (results[0].backend if results else "unknown"),
        "total": total,
        "hit_at_1": (sum(1 for item in results if item.hit_at_1) / total) if total else 0.0,
        "hit_at_3": (sum(1 for item in results if item.hit_at_3) / total) if total else 0.0,
        "mrr": mean(item.reciprocal_rank for item in results) if total else 0.0,
        "pass_at_target_rank": (sum(1 for item in results if item.meets_target_rank) / total) if total else 0.0,
        "avg_top_score": mean(item.top_score for item in results) if total else 0.0,
        "per_benchmark": {},
        "per_split": {},
        "per_task": {},
        "per_difficulty": {},
        "per_conversation": {},
        "error_taxonomy": {},
        "results": [asdict(item) for item in results],
    }

    for benchmark_name in sorted({item.benchmark for item in results}):
        scoped = [item for item in results if item.benchmark == benchmark_name]
        summary["per_benchmark"][benchmark_name] = _aggregate_scope(scoped)

    for split_name in sorted({item.split for item in results}):
        scoped = [item for item in results if item.split == split_name]
        summary["per_split"][split_name] = _aggregate_scope(scoped)

    for task_name in sorted({item.task for item in results}):
        scoped = [item for item in results if item.task == task_name]
        summary["per_task"][task_name] = _aggregate_scope(scoped)

    for difficulty_name in sorted({item.difficulty for item in results}):
        scoped = [item for item in results if item.difficulty == difficulty_name]
        summary["per_difficulty"][difficulty_name] = _aggregate_scope(scoped)

    for conversation_key in sorted({item.conversation_key for item in results if item.conversation_key is not None}):
        scoped = [item for item in results if item.conversation_key == conversation_key]
        summary["per_conversation"][str(conversation_key)] = _aggregate_scope(scoped)

    for error_name in sorted({item.error_category for item in results if item.error_category}):
        scoped = [item for item in results if item.error_category == error_name]
        summary["error_taxonomy"][str(error_name)] = _aggregate_scope(scoped)

    return summary


def _classify_error(sample) -> str:
    task = str(sample.metadata.get("task", "unknown"))
    query = sample.query_text.lower()
    if "category-2" in task or query.startswith("when ") or query.startswith("how long "):
        return "temporal_reasoning"
    if "category-3" in task or any(token in query for token in ("ally", "member of", "career", "identity")):
        return "inference_reasoning"
    if "category-4" in task or any(token in query for token in ("why", "how did", "what does", "overall", "balance")):
        return "summary_reasoning"
    return "retrieval_miss"


def _aggregate_scope(results: list[BenchmarkResult]) -> dict[str, object]:
    total = len(results)
    return {
        "total": total,
        "hit_at_1": (sum(1 for item in results if item.hit_at_1) / total) if total else 0.0,
        "hit_at_3": (sum(1 for item in results if item.hit_at_3) / total) if total else 0.0,
        "mrr": mean(item.reciprocal_rank for item in results) if total else 0.0,
        "pass_at_target_rank": (sum(1 for item in results if item.meets_target_rank) / total) if total else 0.0,
        "avg_top_score": mean(item.top_score for item in results) if total else 0.0,
    }


def run_backend_comparison(
    backends: tuple[str, ...] = CANONICAL_BACKENDS,
    extra_benchmark_roots: list[Path] | None = None,
    benchmark_ids: list[str] | None = None,
    max_samples: int | None = None,
    consolidate_history: bool = True,
) -> dict[str, object]:
    config = AppConfig()
    summaries = {}
    for backend_name in backends:
        summaries[backend_name] = run_benchmarks(
            backend_name=backend_name,
            extra_benchmark_roots=extra_benchmark_roots,
            benchmark_ids=benchmark_ids,
            max_samples=max_samples,
            consolidate_history=consolidate_history,
        )

    comparison = {
        "backends": summaries,
        "recommended_backend": max(
            summaries.items(),
            key=lambda item: (
                item[1]["pass_at_target_rank"],
                item[1]["hit_at_1"],
                item[1]["mrr"],
                item[1]["avg_top_score"],
            ),
        )[0]
        if summaries
        else None,
    }
    write_json(config.paths.logs_dir / "benchmark_comparison.json", comparison)
    _write_comparison_report(config.paths.logs_dir / "benchmark_comparison.md", comparison)
    return comparison


def _compact_summary(summary: dict[str, object]) -> dict[str, object]:
    return {
        "backend": summary["backend"],
        "total": summary["total"],
        "hit_at_1": summary["hit_at_1"],
        "hit_at_3": summary["hit_at_3"],
        "mrr": summary["mrr"],
        "pass_at_target_rank": summary["pass_at_target_rank"],
        "avg_top_score": summary["avg_top_score"],
        "per_benchmark": summary["per_benchmark"],
        "per_split": summary["per_split"],
        "per_task": summary["per_task"],
        "per_difficulty": summary["per_difficulty"],
        "per_conversation": summary.get("per_conversation", {}),
        "error_taxonomy": summary.get("error_taxonomy", {}),
        "dataset_manifests": summary.get("dataset_manifests", {}),
    }


def _write_markdown_report(path, summary: dict[str, object]) -> None:
    lines = [
        "# Benchmark Report",
        "",
        f"- Backend: {summary['backend']}",
        f"- Total samples: {summary['total']}",
        f"- Hit@1: {summary['hit_at_1']:.3f}",
        f"- Hit@3: {summary['hit_at_3']:.3f}",
        f"- MRR: {summary['mrr']:.3f}",
        f"- Pass@TargetRank: {summary['pass_at_target_rank']:.3f}",
        f"- Average top score: {summary['avg_top_score']:.3f}",
        "",
        "## Dataset Manifests",
    ]

    for name, manifest in summary.get("dataset_manifests", {}).items():
        lines.append(
            f"- {name}: version={manifest.get('version', 'unknown')}, "
            f"splits={','.join(manifest.get('splits', []))}, "
            f"sample_counts={manifest.get('sample_counts', {})}"
        )

    lines.extend(
        [
        "",
        "## Per Benchmark",
        ]
    )

    for name, metrics in summary["per_benchmark"].items():
        lines.append(f"- {name}: hit@1={metrics['hit_at_1']:.3f}, hit@3={metrics['hit_at_3']:.3f}, mrr={metrics['mrr']:.3f}")

    lines.append("")
    lines.append("## Per Split")
    for name, metrics in summary["per_split"].items():
        lines.append(f"- {name}: hit@1={metrics['hit_at_1']:.3f}, hit@3={metrics['hit_at_3']:.3f}, mrr={metrics['mrr']:.3f}")

    lines.append("")
    lines.append("## Per Task")
    for name, metrics in summary["per_task"].items():
        lines.append(f"- {name}: hit@1={metrics['hit_at_1']:.3f}, hit@3={metrics['hit_at_3']:.3f}, mrr={metrics['mrr']:.3f}")

    lines.append("")
    lines.append("## Per Difficulty")
    for name, metrics in summary["per_difficulty"].items():
        lines.append(f"- {name}: hit@1={metrics['hit_at_1']:.3f}, hit@3={metrics['hit_at_3']:.3f}, mrr={metrics['mrr']:.3f}")

    if summary.get("per_conversation"):
        lines.append("")
        lines.append("## Per Conversation")
        for name, metrics in summary["per_conversation"].items():
            lines.append(
                f"- {name}: hit@1={metrics['hit_at_1']:.3f}, hit@3={metrics['hit_at_3']:.3f}, mrr={metrics['mrr']:.3f}"
            )

    if summary.get("error_taxonomy"):
        lines.append("")
        lines.append("## Error Taxonomy")
        for name, metrics in summary["error_taxonomy"].items():
            lines.append(
                f"- {name}: total={metrics['total']}, hit@1={metrics['hit_at_1']:.3f}, hit@3={metrics['hit_at_3']:.3f}, mrr={metrics['mrr']:.3f}"
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_comparison_report(path, comparison: dict[str, object]) -> None:
    lines = [
        "# Backend Comparison",
        "",
        f"- Recommended backend: {comparison.get('recommended_backend')}",
        "",
        "## Results",
    ]
    for backend_name, metrics in comparison["backends"].items():
        lines.append(
            f"- {backend_name}: hit@1={metrics['hit_at_1']:.3f}, hit@3={metrics['hit_at_3']:.3f}, "
            f"mrr={metrics['mrr']:.3f}, pass@TargetRank={metrics['pass_at_target_rank']:.3f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local memory benchmarks")
    parser.add_argument("--backend", choices=CANONICAL_BACKENDS)
    parser.add_argument("--compare", action="store_true", help="Run benchmark comparison across canonical backends")
    parser.add_argument(
        "--benchmark-root",
        action="append",
        default=[],
        help="Additional benchmark root directory containing manifest-based datasets",
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        default=[],
        help="Restrict the run to one or more benchmark ids",
    )
    parser.add_argument("--max-samples", type=int, help="Cap the number of benchmark samples for quick verification")
    parser.add_argument("--skip-comparison", action="store_true", help="Skip multi-backend comparison to keep runs short")
    parser.add_argument("--no-consolidation", action="store_true", help="Skip session consolidation before evaluation")
    args = parser.parse_args()
    extra_roots = [Path(value) for value in args.benchmark_root]
    benchmark_ids = list(args.benchmark) or None

    if args.compare:
        comparison = run_backend_comparison(
            extra_benchmark_roots=extra_roots,
            benchmark_ids=benchmark_ids,
            max_samples=args.max_samples,
            consolidate_history=not args.no_consolidation,
        )
        compact = {
            "recommended_backend": comparison["recommended_backend"],
            "backends": {
                name: _compact_summary(metrics)
                for name, metrics in comparison["backends"].items()
            },
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))
        return 0

    summary = run_benchmarks(
        backend_name=args.backend,
        extra_benchmark_roots=extra_roots,
        benchmark_ids=benchmark_ids,
        max_samples=args.max_samples,
        consolidate_history=not args.no_consolidation,
    )
    if args.skip_comparison:
        compact = {"summary": _compact_summary(summary)}
        print(json.dumps(compact, ensure_ascii=False, indent=2))
        return 0

    comparison = run_backend_comparison(
        extra_benchmark_roots=extra_roots,
        benchmark_ids=benchmark_ids,
        max_samples=args.max_samples,
        consolidate_history=not args.no_consolidation,
    )
    compact = {
        "summary": _compact_summary(summary),
        "comparison": {
            "recommended_backend": comparison["recommended_backend"],
            "backends": {
                name: _compact_summary(metrics)
                for name, metrics in comparison["backends"].items()
            },
        },
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
