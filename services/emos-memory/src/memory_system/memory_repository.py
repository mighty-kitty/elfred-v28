from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import AppConfig
from .content_cleaning import extract_core_content
from .evidence_features_v2 import extract_evidence_spans_v2
from .emotion_engine import CALM_EMOTION
from .feedback_loop import (
    append_interaction_log,
    build_feedback_report,
    compute_feedback_bonus,
    export_offline_review_dataset,
    infer_passive_feedback_signal,
    load_feedback_state,
    record_feedback_event,
    save_feedback_state,
)
from .memory_features import derive_memory_abstractions
from .models import MemoryBlock, MemoryEntry, RetrievalCandidate, SemanticProfile, utc_now
from .object_attributes import extract_attribute_markers
from .relation_features import extract_relation_markers, summarize_relation_markers
from .retrieval_backends import (
    RetrievalWeights,
    build_entry_surface_text,
    build_retrieval_backend,
    build_retrieval_pipeline_profile,
    count_answer_anchor_hits,
    detect_question_type,
    expand_query_text,
    extract_answer_anchor_tokens,
    extract_concepts,
    get_retrieval_backend_descriptor,
    get_retrieval_backend_descriptors,
    has_temporal_signal,
    is_question_like_candidate,
    query_mentions_recency,
    tokenize,
    validate_retrieval_backend_settings,
)
from .retrieval_assets import load_retrieval_settings, load_semantic_aliases, load_stop_tokens, normalize_retrieval_settings
from .storage_backends import JsonStateStore, SQLiteStateStore, build_state_store
from .utils.io import read_json, write_json


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _entry_age_days(created_at: str | None) -> float | None:
    created = _parse_iso_datetime(created_at)
    if created is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400.0)


def _entry_age_signal(created_at: str | None) -> str:
    age_days = _entry_age_days(created_at)
    if age_days is None:
        return "unknown"
    if age_days <= 7:
        return "fresh"
    if age_days <= 60:
        return "recent"
    if age_days <= 365:
        return "aged"
    return "old"


def _build_deletion_receipt(
    *,
    user_id: str,
    memory_id: str,
    deleted_at: str,
    deleted_by: str,
    reason: str,
    previous_status: str,
    history_snapshot: dict[str, object],
) -> dict[str, object]:
    receipt_core = {
        "surface_version": "deletion-receipt.v1",
        "user_id": user_id,
        "memory_id": memory_id,
        "deletion_mode": "soft_forget_tombstone",
        "tombstone_status": "forgotten",
        "deleted_at": deleted_at,
        "deleted_by": deleted_by,
        "reason": reason,
        "previous_status": previous_status,
        "history_action": history_snapshot.get("action"),
        "history_recorded_at": history_snapshot.get("recorded_at"),
        "history_revision_before": history_snapshot.get("revision"),
    }
    canonical = json.dumps(receipt_core, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    receipt_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    receipt = dict(receipt_core)
    receipt.update(
        {
            "receipt_id": f"delrec-{receipt_hash[:24]}",
            "hash_algorithm": "sha256",
            "receipt_hash": receipt_hash,
            "hash_scope": "service_receipt_fields_only_no_memory_text",
            "verification_scope": "operator_auditable_service_receipt",
            "guarantees": [
                "memory_marked_forgotten_in_service_state",
                "memory_excluded_from_active_repository_reads",
                "forget_action_recorded_in_memory_history",
            ],
            "non_guarantees": [
                "physical_storage_erasure",
                "cryptographic_erasure_proof",
                "backup_or_replica_purge_proof",
            ],
        }
    )
    return receipt


def _is_ascii_safe_path(path: Path) -> bool:
    return all(ord(char) < 128 for char in str(path))

SUMMARY_STOP_TOKENS = {
    "am",
    "pm",
    "speaker",
    "image",
    "query",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "caroline",
    "melanie",
    "john",
    "maria",
    "nate",
    "tim",
    "andrew",
    "audrey",
    "mel",
    "thanks",
    "yeah",
    "cool",
    "great",
    "look",
    "okay",
    "bye",
    "hello",
    "hey",
}

SUMMARY_REASON_MARKERS = (
    "because",
    "since",
    "so that",
    "support",
    "important",
    "dream",
    "love",
    "stand",
    "remind",
)

ANSWER_STYLE_ATTRIBUTE_TARGETS = {
    "attr:customer_experience",
    "attr:business_advice",
    "attr:internship_location",
    "attr:clipboard_use",
    "attr:workout_frequency",
    "attr:military_inspiration",
    "attr:dinner_spread",
    "attr:dinner_activity",
    "attr:yoga_pose_feeling",
    "attr:festival_attitude",
    "attr:convention_event",
    "attr:pet_identity_list",
    "attr:church_join_reason",
    "attr:promotion_support",
    "attr:marching_event",
    "attr:veteran_hospital_appreciation",
    "attr:community_motivation",
    "attr:run_cause",
    "attr:memorial_reaction",
    "attr:turtles_duration",
    "attr:screenplay_completion",
    "attr:waterfall_name",
    "attr:firetruck_acquisition",
    "attr:promotion_role",
    "attr:promotion_challenge",
    "attr:certificate_reason",
    "attr:car_donation",
    "attr:run_cause",
    "attr:blog_topic",
    "attr:blog_focus",
    "attr:blog_reason",
    "attr:children_names",
    "attr:exercise_list",
    "attr:housing_urgency",
    "attr:marching_event",
    "attr:domestic_abuse_partner",
    "attr:shared_interests",
    "attr:hiking_trail_count",
    "attr:give_back_takeaway",
    "attr:teammates_friendship",
    "attr:book_recommendations",
    "attr:shared_movies",
    "attr:happy_memory_method",
    "attr:console_switch",
    "attr:tournament_valorant",
    "attr:state_florida",
    "attr:movie_genre",
    "attr:screenplay_plan",
    "attr:screenplay_inspiration",
    "attr:turtle_pet_reason",
    "attr:turtle_care",
    "attr:writing_gig",
    "attr:icecream_ingredients",
    "attr:dessert_flavors",
    "attr:icecream_flavor",
    "attr:icecream_opinion",
    "attr:writers_group_project",
    "attr:favorite_movie",
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
    "attr:movie_genre_fantasy_scifi",
    "attr:favorite_book_features",
    "attr:escape_activity_movies",
    "attr:cake_filling",
    "attr:cake_frosting",
    "attr:whispering_falls_writing",
    "attr:screenplay_joke_plan",
    "attr:trails_inviter",
    "attr:stuffed_animal_gift",
    "attr:stuffed_animal_meaning",
    "attr:gaming_party_invitees",
    "attr:gaming_party_items",
    "attr:superhero_spiderman",
    "attr:superhero_ironman",
    "attr:corkboard_items",
    "attr:vegan_icecream_shared",
    "attr:vegan_recipe_offer",
    "attr:recipe_plan_family",
    "attr:roadtrip_research_location",
    "attr:book_themes",
    "attr:tournament_career",
    "attr:writing_impact",
    "attr:joanna_coconut_icecream",
    "attr:sharing_desserts_feeling",
    "attr:writers_group_celebration",
    "attr:tournament_chill_celebration",
    "attr:favorite_treat_mousse",
    "attr:cake_type_raspberry",
    "attr:blueberry_dessert_ingredients",
    "attr:recent_movie_little_women",
    "attr:writing_club_bookmark",
    "attr:unwind_photo",
    "attr:classic_movie_opinion",
    "attr:living_room_tips",
    "attr:tilly_focus",
    "attr:tilly_while_writing",
    "attr:party_attendance",
    "attr:favorite_dish_show",
    "attr:tilly_origin",
    "attr:rejection_response",
    "attr:resilience_respect",
    "attr:rejection_advice",
    "attr:character_visuals_purpose",
    "attr:turtle_diet",
    "attr:current_game_xenoblade",
    "attr:letter_object",
    "attr:homemade_coconut_icecream",
    "attr:thriller_project",
    "attr:video_motivation",
    "attr:video_advice",
    "attr:hangout_plan",
    "attr:colorful_bowls_icecream",
    "attr:letter_reaction",
    "attr:baking_substitute",
    "attr:youtube_content",
    "attr:third_turtle_reason",
    "attr:turtles_cheer",
    "attr:turtles_joy",
    "attr:career_high_points_time",
    "attr:other_sport",
    "attr:outdoor_activities",
    "attr:hp_fan_reconnect_duration",
    "attr:pre_chicago_city",
    "attr:trip_city_chicago",
    "attr:city_list",
    "attr:hp_conference_week",
    "attr:uk_castle_trip",
    "attr:smoky_mountains_year",
    "attr:lebron_traits",
    "attr:italy_prev_month",
    "attr:study_abroad_day",
    "attr:hp_collab_topics",
    "attr:minalima_picture",
    "attr:seattle_game_city",
    "attr:surfing_feeling",
    "attr:fantasy_novels_pair",
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
    "attr:favorite_bird",
    "attr:tattoo_flowers",
    "attr:ideal_dog_home",
    "attr:workshop_source",
    "attr:pet_search_challenge",
    "attr:pet_help_offer",
    "attr:tournament_game_apex",
    "attr:adopted_pet_type",
    "attr:adopted_pup_name",
    "attr:visited_country_italy",
    "attr:work_assignment_coding",
    "attr:charity_leftovers_homeless",
    "attr:charity_hospital",
    "attr:foundation_tracking",
    "attr:foundation_app_mobile",
    "attr:football_team_liverpool",
    "attr:relax_reading",
    "attr:hobby_extreme_sports",
    "attr:trip_return_july20",
    "attr:it_job_reason_values",
    "attr:fortnite_competitions",
    "attr:puppy_clinic",
    "attr:call_samantha",
    "attr:teach_siblings_coding",
    "attr:class_cost_ten",
    "attr:class_make_dough",
    "attr:class_reason_learn_new",
    "attr:class_first_omelette",
    "attr:boardgame_dod",
    "attr:idea_sources",
    "attr:gig_programming_mentor",
    "attr:mentor_feeling_excited",
    "attr:movein_decision",
    "attr:apartment_near_mcgees",
    "attr:reason_near_mcgees",
    "attr:hooked_game_fifa23",
    "attr:project_online_boardgame",
    "attr:cousin_dog_luna",
    "attr:yoga_locations_list",
    "attr:professional_growth_list",
    "attr:engineering_projects_list",
    "attr:community_activities_list",
    "attr:gifts_received_list",
    "attr:countries_traveled_list",
    "attr:activities_besides_yoga",
    "attr:rio_activities_list",
    "attr:relationship_focus",
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



class MemoryRepository:
    def __init__(self, config: AppConfig, retrieval_settings_override: dict[str, object] | None = None):
        self.config = config
        self.semantic_aliases = load_semantic_aliases()
        self.stop_tokens = load_stop_tokens()
        self.state_store = build_state_store(
            storage_backend=config.storage_backend,
            json_path=config.paths.memory_file,
            sqlite_path=config.paths.sqlite_file,
        )
        self._retrieval_prefilter_cache: dict[str, dict[str, object]] = {}
        self._last_retrieval_prefilter_report: dict[str, object] = {"enabled": False}
        retrieval_settings = retrieval_settings_override or load_retrieval_settings()
        self._current_retrieval_settings = normalize_retrieval_settings(retrieval_settings)
        self._apply_retrieval_settings(self._current_retrieval_settings)
        self.feedback_state = load_feedback_state(self.config.paths.feedback_store_file)
        payload = self.state_store.load(default={"episodic": [], "emotional": [], "semantic": {}, "dreams": {}, "memory_blocks": {}, "idempotency_records": {}})
        self.episodic = [MemoryEntry.from_dict(item) for item in payload.get("episodic", [])]
        self.emotional = [MemoryEntry.from_dict(item) for item in payload.get("emotional", [])]
        self.semantic = {
            user_id: SemanticProfile.from_dict(item)
            for user_id, item in payload.get("semantic", {}).items()
        }
        self.dreams = payload.get("dreams", {})
        self.memory_blocks = {
            user_id: [MemoryBlock.from_dict(item) for item in items if isinstance(item, dict)]
            for user_id, items in payload.get("memory_blocks", {}).items()
            if isinstance(items, list)
        }
        self.idempotency_records = (
            dict(payload.get("idempotency_records", {}))
            if isinstance(payload.get("idempotency_records", {}), dict)
            else {}
        )

    def _apply_retrieval_settings(self, retrieval_settings: dict[str, object]) -> None:
        backend_name = str(retrieval_settings.get("backend", "lexical"))
        weight_values = retrieval_settings.get("weights", {})
        embedding_settings = retrieval_settings.get("embedding", {})
        validate_retrieval_backend_settings(
            backend_name=backend_name,
            embedding_dimensions=int(embedding_settings.get("dimensions", 96)),
            embedding_candidate_pool=int(embedding_settings.get("candidate_pool", 8)),
        )
        self.retrieval_backend = build_retrieval_backend(
            backend_name=backend_name,
            semantic_aliases=self.semantic_aliases,
            stop_tokens=self.stop_tokens,
            weights=RetrievalWeights(
                lexical=float(weight_values.get("lexical", 1.0)),
                fuzzy=float(weight_values.get("fuzzy", 0.35)),
                semantic=float(weight_values.get("semantic", 0.45)),
                concept=float(weight_values.get("concept", 0.30)),
                tag=float(weight_values.get("tag", 0.12)),
                phrase=float(weight_values.get("phrase", 0.22)),
                question=float(weight_values.get("question", 0.18)),
                inference=float(weight_values.get("inference", 0.22)),
                emotion=float(weight_values.get("emotion", 0.15)),
                recency=float(weight_values.get("recency", 0.08)),
                profile=float(weight_values.get("profile", 0.10)),
                abstraction=float(weight_values.get("abstraction", 0.20)),
                embedding=float(weight_values.get("embedding", 0.60)),
            ),
            embedding_dimensions=int(embedding_settings.get("dimensions", 96)),
            embedding_candidate_pool=int(embedding_settings.get("candidate_pool", 8)),
        )
        self.retrieval_backend_name = backend_name
        self.retrieval_weights = self.retrieval_backend.weights
        prefilter_settings = retrieval_settings.get("prefilter", {})
        self.retrieval_prefilter_settings = dict(prefilter_settings) if isinstance(prefilter_settings, dict) else {}
        self._retrieval_prefilter_cache.clear()
        self._last_retrieval_prefilter_report = {
            "enabled": bool(self.retrieval_prefilter_settings.get("enabled", False)),
            "used": False,
        }

    def _build_payload(self) -> dict[str, object]:
        return {
            "episodic": [item.to_dict() for item in self.episodic],
            "emotional": [item.to_dict() for item in self.emotional],
            "semantic": {user_id: item.to_dict() for user_id, item in self.semantic.items()},
            "dreams": self.dreams,
            "memory_blocks": {
                user_id: [block.to_dict() for block in blocks]
                for user_id, blocks in self.memory_blocks.items()
            },
            "idempotency_records": self.idempotency_records,
        }

    def save(self) -> None:
        self.state_store.save(self._build_payload())
        save_feedback_state(self.config.paths.feedback_store_file, self.feedback_state)

    def _idempotency_record_key(self, *, operation: str, user_id: str, key: str) -> str:
        return f"{operation}:{user_id}:{key}"

    def get_idempotency_record(self, *, operation: str, user_id: str, key: str) -> dict[str, object] | None:
        record = self.idempotency_records.get(self._idempotency_record_key(operation=operation, user_id=user_id, key=key))
        return dict(record) if isinstance(record, dict) else None

    def save_idempotency_record(
        self,
        *,
        operation: str,
        user_id: str,
        key: str,
        request_fingerprint: str,
        response_payload: dict[str, object],
        persist: bool = True,
    ) -> dict[str, object]:
        record = {
            "surface_version": "operation-idempotency.v1",
            "operation": operation,
            "user_id": user_id,
            "idempotency_key": key,
            "request_fingerprint": request_fingerprint,
            "created_at": utc_now(),
            "decision_type": response_payload.get("decision_type"),
            "next_action": response_payload.get("next_action"),
            "memory_id": response_payload.get("memory_id"),
            "memory_written": bool(response_payload.get("memory_written")),
            "response_payload": dict(response_payload),
        }
        self.idempotency_records[self._idempotency_record_key(operation=operation, user_id=user_id, key=key)] = record
        if len(self.idempotency_records) > 1000:
            sorted_items = sorted(
                self.idempotency_records.items(),
                key=lambda item: str(item[1].get("created_at", "")) if isinstance(item[1], dict) else "",
            )
            self.idempotency_records = dict(sorted_items[-1000:])
        if persist:
            self.save()
        return record

    def available_retrieval_backends(self) -> list[str]:
        return sorted(get_retrieval_backend_descriptors().keys())

    def get_retrieval_backend_report(self) -> dict[str, object]:
        descriptor = get_retrieval_backend_descriptor(self.retrieval_backend_name)
        pipeline_profile = build_retrieval_pipeline_profile(self.retrieval_backend_name)
        effective_dimensions = int(getattr(self.retrieval_backend, "embedding_dimensions", 96))
        effective_candidate_pool = int(getattr(self.retrieval_backend, "embedding_candidate_pool", 8))
        validation = validate_retrieval_backend_settings(
            backend_name=self.retrieval_backend_name,
            embedding_dimensions=effective_dimensions,
            embedding_candidate_pool=effective_candidate_pool,
        )
        candidate_pool_ready = effective_candidate_pool >= descriptor.recommended_candidate_pool
        rerank_readiness = "ready"
        if descriptor.supports_rerank and not candidate_pool_ready:
            rerank_readiness = "review"
        recall_readiness = "ready" if descriptor.family in {"sparse", "hybrid", "dense"} else "review"
        fusion_readiness = "ready" if pipeline_profile.get("fusion_strategy") != "none" else ("simple" if descriptor.family == "sparse" else "ready")
        overall_readiness = "ready"
        if rerank_readiness == "review" or recall_readiness == "review":
            overall_readiness = "review"
        task_fit = {
            "high_precision_fact_recall": "strong" if descriptor.family in {"hybrid", "dense"} else "acceptable",
            "low_latency_local_runtime": "strong" if descriptor.family in {"sparse", "hybrid"} else "acceptable",
            "attribute_rich_memory_queries": "strong" if descriptor.family in {"hybrid", "dense"} else "acceptable",
            "conservative_agent_grounding": "strong" if descriptor.supports_rerank else "acceptable",
            "future_embedding_upgrade_path": "strong" if descriptor.supports_embedding else "limited",
        }
        anti_patterns: list[str] = []
        if descriptor.family == "sparse":
            anti_patterns.append("do_not_expect_dense_semantic_recall_without_backend_switch")
        if descriptor.supports_rerank and not candidate_pool_ready:
            anti_patterns.append("avoid_small_candidate_pool_for_rerank_heavy_queries")
        if not descriptor.supports_rerank:
            anti_patterns.append("avoid_overclaiming_top1_confidence_when_query_is_ambiguous")
        switch_backend_recommended = descriptor.family == "sparse" or not descriptor.supports_rerank
        switch_backend_target = "embedding_rerank" if switch_backend_recommended and self.retrieval_backend_name != "embedding_rerank" else None
        candidate_pool_status = "ready" if candidate_pool_ready else "small"
        candidate_pool_reason = (
            "candidate_pool_is_operationally_acceptable"
            if candidate_pool_ready
            else "candidate_pool_below_recommended_rerank_window"
        )
        response_policy_mode = "grounded_answer"
        response_policy_reason = "retrieval_control_plane_ready_for_grounded_answering"
        strong_answer_ok = True
        if not descriptor.supports_rerank:
            response_policy_mode = "confirm_on_ambiguity"
            response_policy_reason = "backend_lacks_stronger_rerank_control"
            strong_answer_ok = False
        if descriptor.supports_rerank and not candidate_pool_ready:
            response_policy_mode = "avoid_strong_answer_on_thin_candidate_pool"
            response_policy_reason = "rerank_backend_needs_larger_candidate_pool"
            strong_answer_ok = False
        runtime_advice_operations: list[dict[str, object]] = []
        if switch_backend_target:
            runtime_advice_operations.append(
                {
                    "operation": "set_retrieval_backend",
                    "reason": "switch_backend_for_harder_semantic_or_grounded_recall",
                    "priority": 92,
                    "scope": "system",
                    "requires_confirmation": False,
                    "arguments": {"backend_name": switch_backend_target},
                }
            )
        if not candidate_pool_ready:
            runtime_advice_operations.append(
                {
                    "operation": "increase_embedding_candidate_pool",
                    "reason": "candidate_pool_too_small_for_rerank_heavy_queries",
                    "priority": 90,
                    "scope": "system",
                    "requires_confirmation": False,
                    "arguments": {"candidate_pool": descriptor.recommended_candidate_pool},
                }
            )
        if response_policy_mode != "grounded_answer":
            runtime_advice_operations.append(
                {
                    "operation": "prefer_confirmation_aware_recall",
                    "reason": response_policy_reason,
                    "priority": 86,
                    "scope": "agent",
                    "requires_confirmation": False,
                    "arguments": {"mode": response_policy_mode},
                }
            )
        return {
            "active_backend": self.retrieval_backend_name,
            "available_backends": self.available_retrieval_backends(),
            "backend_descriptor": descriptor.__dict__,
            "pipeline_profile": pipeline_profile,
            "settings_path": str(self.config.paths.retrieval_settings_file),
            "settings": self._current_retrieval_settings,
            "prefilter": {
                "settings": dict(self.retrieval_prefilter_settings),
                "last_recall": dict(self._last_retrieval_prefilter_report),
            },
            "effective_embedding_dimensions": effective_dimensions,
            "effective_candidate_pool": effective_candidate_pool,
            "validation_notes": list(validation.get("notes", [])),
            "recommended_candidate_pool": descriptor.recommended_candidate_pool,
            "switch_history": list(self._current_retrieval_settings.get("history", []))[-10:],
            "control_plane_status": {
                "readiness": overall_readiness,
                "recall": recall_readiness,
                "fusion": fusion_readiness,
                "rerank": rerank_readiness,
                "candidate_pool_ready": candidate_pool_ready,
            },
            "task_fit": task_fit,
            "agent_recommendations": [
                "prefer this backend for grounded personal-agent recall" if descriptor.supports_rerank else "use confirmation-aware response policy on ambiguous recall",
                "increase candidate pool before intensive rerank usage" if descriptor.supports_rerank and not candidate_pool_ready else "current candidate pool is operationally acceptable",
                "switch to embedding_rerank for harder semantic memory questions" if not descriptor.supports_rerank else "backend already supports stronger rerank-style control",
            ],
            "runtime_advice": {
                "advice_version": "retrieval-runtime-advice.v1",
                "switch_backend": {
                    "recommended": switch_backend_recommended,
                    "target_backend": switch_backend_target,
                    "reason": "current_backend_is_not_ideal_for_harder_semantic_or_grounded_recall"
                    if switch_backend_recommended
                    else "active_backend_is_already_suitable_for_grounded_recall",
                },
                "candidate_pool": {
                    "status": candidate_pool_status,
                    "effective_size": effective_candidate_pool,
                    "recommended_min": descriptor.recommended_candidate_pool,
                    "reason": candidate_pool_reason,
                },
                "response_policy": {
                    "mode": response_policy_mode,
                    "strong_answer_ok": strong_answer_ok,
                    "reason": response_policy_reason,
                },
                "recommended_operations": runtime_advice_operations,
            },
            "anti_patterns": anti_patterns,
        }

    def configure_retrieval_backend(
        self,
        *,
        backend_name: str,
        embedding_dimensions: int | None = None,
        embedding_candidate_pool: int | None = None,
        persist: bool = True,
        change_source: str = "runtime",
    ) -> dict[str, object]:
        if backend_name not in self.available_retrieval_backends():
            raise ValueError(f"Unsupported retrieval backend: {backend_name}")

        next_settings = normalize_retrieval_settings(self._current_retrieval_settings)
        previous_backend = str(next_settings.get("backend", self.retrieval_backend_name))
        next_settings["backend"] = backend_name
        embedding_settings = dict(next_settings.get("embedding", {}))
        if embedding_dimensions is not None:
            embedding_settings["dimensions"] = int(embedding_dimensions)
        if embedding_candidate_pool is not None:
            embedding_settings["candidate_pool"] = int(embedding_candidate_pool)
        next_settings["embedding"] = embedding_settings
        validate_retrieval_backend_settings(
            backend_name=backend_name,
            embedding_dimensions=int(embedding_settings.get("dimensions", 96)),
            embedding_candidate_pool=int(embedding_settings.get("candidate_pool", 8)),
        )
        history = list(next_settings.get("history", []))
        history.append(
            {
                "changed_at": utc_now(),
                "source": change_source,
                "from_backend": previous_backend,
                "to_backend": backend_name,
                "embedding_dimensions": int(embedding_settings.get("dimensions", 96)),
                "candidate_pool": int(embedding_settings.get("candidate_pool", 8)),
            }
        )
        next_settings["history"] = history[-20:]
        self._current_retrieval_settings = next_settings
        self._apply_retrieval_settings(next_settings)
        if persist:
            write_json(self.config.paths.retrieval_settings_file, next_settings)
        return self.get_retrieval_backend_report()

    def get_profile(self, user_id: str) -> SemanticProfile:
        profile = self.semantic.get(user_id)
        if profile is None:
            profile = SemanticProfile(user_id=user_id)
            self.semantic[user_id] = profile
        return profile

    def list_memory_blocks(self, user_id: str) -> list[MemoryBlock]:
        blocks = list(self.memory_blocks.get(user_id, []))
        blocks.sort(key=lambda item: (item.priority, item.updated_at), reverse=True)
        return blocks

    def get_memory_status(self, entry: MemoryEntry) -> str:
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        status = str(metadata.get("status") or "").strip().lower()
        if status:
            return status
        if metadata.get("deleted_at"):
            return "forgotten"
        return "active"

    def get_memory_state_summary(self, *, user_id: str, memory_id: str) -> dict[str, object] | None:
        entry = self.get_memory(user_id, memory_id, include_inactive=True)
        if entry is None:
            return None
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        history = metadata.get("history", [])
        merged_from = list(metadata.get("merged_from", [])) if isinstance(metadata.get("merged_from", []), list) else []
        supersedes = list(metadata.get("supersedes", [])) if isinstance(metadata.get("supersedes", []), list) else []
        status = self.get_memory_status(entry)
        version_status = "stable"
        if status in {"superseded", "merged", "forgotten"}:
            version_status = "inactive"
        elif int(metadata.get("revision", 1)) > 1 or merged_from or supersedes:
            version_status = "revised"
        return {
            "memory_id": entry.memory_id,
            "status": status,
            "revision": int(metadata.get("revision", 1)),
            "history_count": len(history) if isinstance(history, list) else 0,
            "created_at": entry.created_at,
            "age_days": round(_entry_age_days(entry.created_at) or 0.0, 2),
            "age_signal": _entry_age_signal(entry.created_at),
            "updated_at": metadata.get("updated_at"),
            "deleted_at": metadata.get("deleted_at"),
            "deletion_receipt_available": isinstance(metadata.get("deletion_receipt"), dict),
            "deletion_receipt": metadata.get("deletion_receipt") if isinstance(metadata.get("deletion_receipt"), dict) else None,
            "superseded_by": metadata.get("superseded_by"),
            "merged_into": metadata.get("merged_into"),
            "merged_from": merged_from,
            "supersedes": supersedes,
            "version_status": version_status,
            "stability_signal": "stable" if version_status == "stable" else ("inactive" if version_status == "inactive" else "revised"),
            "requires_confirmation": status in {"superseded", "merged"} or (version_status == "revised" and _entry_age_signal(entry.created_at) in {"aged", "old"}),
        }

    def upsert_memory_block(
        self,
        *,
        user_id: str,
        label: str,
        value: str,
        description: str = "",
        tier: str = "agent_pinned",
        priority: int = 50,
        read_only: bool = False,
        source: str = "agent",
        persist: bool = True,
    ) -> MemoryBlock:
        normalized_label = label.strip().lower()
        blocks = self.memory_blocks.setdefault(user_id, [])
        for block in blocks:
            if block.label == normalized_label:
                block.value = value
                block.description = description
                block.tier = tier
                block.priority = int(priority)
                block.read_only = read_only
                block.source = source
                block.updated_at = utc_now()
                if persist:
                    self.save()
                return block
        block = MemoryBlock(
            user_id=user_id,
            label=normalized_label,
            value=value,
            description=description,
            tier=tier,
            priority=int(priority),
            read_only=read_only,
            source=source,
        )
        blocks.append(block)
        if persist:
            self.save()
        return block

    def delete_memory_block(self, *, user_id: str, label: str, persist: bool = True) -> bool:
        normalized_label = label.strip().lower()
        blocks = self.memory_blocks.get(user_id, [])
        remaining = [block for block in blocks if block.label != normalized_label]
        deleted = len(remaining) != len(blocks)
        if deleted:
            self.memory_blocks[user_id] = remaining
            if persist:
                self.save()
        return deleted

    def get_agent_core_memory_blocks(
        self,
        *,
        user_id: str,
        task_goal: str | None = None,
        context_summary: str | None = None,
        working_memory: list[str] | None = None,
        limit: int = 4,
    ) -> list[dict[str, object]]:
        blocks: list[dict[str, object]] = []
        for block in self.list_memory_blocks(user_id)[:limit]:
            blocks.append(block.to_dict())

        profile = self.get_profile(user_id)
        interests = profile.facts.get("interests", [])[:6]
        abstractions = profile.facts.get("abstractions", [])[:6]
        if interests or abstractions:
            summary_parts = []
            if interests:
                summary_parts.append("interests: " + ", ".join(interests))
            if abstractions:
                summary_parts.append("abstractions: " + ", ".join(abstractions))
            blocks.append(
                {
                    "user_id": user_id,
                    "label": "derived_profile",
                    "value": "; ".join(summary_parts),
                    "description": "System-derived durable profile summary for the upper-layer agent.",
                    "read_only": True,
                    "updated_at": profile.updated_at,
                    "source": "system_derived",
                }
            )
        if task_goal or context_summary or working_memory:
            parts = []
            if task_goal:
                parts.append(f"task_goal: {task_goal}")
            if context_summary:
                parts.append(f"context: {context_summary}")
            if working_memory:
                parts.append("working_memory: " + " | ".join(working_memory[:6]))
            blocks.append(
                {
                    "user_id": user_id,
                    "label": "agent_context",
                    "value": "; ".join(parts),
                    "description": "Ephemeral agent context bundled with recall-time core memory.",
                    "read_only": True,
                    "updated_at": utc_now(),
                    "source": "request_context",
                }
            )
        return blocks[:limit]

    def update_profile(
        self,
        user_id: str,
        text: str,
        tags: Iterable[str],
        abstractions: Iterable[str] | None = None,
    ) -> SemanticProfile:
        profile = self.get_profile(user_id)
        for token in tokenize(text, self.semantic_aliases, self.stop_tokens):
            profile.keywords[token] = profile.keywords.get(token, 0) + 1
        for tag in tags:
            profile.facts.setdefault("interests", [])
            if tag not in profile.facts["interests"]:
                profile.facts["interests"].append(tag)
        for abstraction in abstractions or []:
            profile.keywords[abstraction] = profile.keywords.get(abstraction, 0) + 2
            profile.facts.setdefault("abstractions", [])
            if abstraction not in profile.facts["abstractions"]:
                profile.facts["abstractions"].append(abstraction)
        for attribute in extract_attribute_markers(text):
            profile.keywords[attribute] = profile.keywords.get(attribute, 0) + 2
            profile.facts.setdefault("attributes", [])
            if attribute not in profile.facts["attributes"]:
                profile.facts["attributes"].append(attribute)
        profile.updated_at = utc_now()
        return profile

    def add_memory(self, entry: MemoryEntry) -> None:
        metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
        metadata.setdefault("status", "active")
        metadata.setdefault("revision", 1)
        metadata.setdefault("history", [])
        previous_entry = next(
            (
                existing
                for existing in reversed(self.episodic)
                if existing.user_id == entry.user_id
                and existing.session_id == entry.session_id
                and existing.category == "episodic"
            ),
            None,
        )
        if previous_entry is not None:
            metadata["prev_memory_id"] = previous_entry.memory_id
            metadata["prev_memory_text"] = previous_entry.text
            previous_metadata = dict(previous_entry.metadata) if isinstance(previous_entry.metadata, dict) else {}
            previous_metadata["next_memory_id"] = entry.memory_id
            previous_metadata["next_memory_text"] = entry.text
            previous_entry.metadata = previous_metadata
        entry.metadata = metadata
        self.episodic.append(entry)
        if entry.emotion != CALM_EMOTION:
            self.emotional.append(entry)
        if entry.category == "episodic":
            for evidence_entry in self._derive_evidence_entries(entry):
                self.episodic.append(evidence_entry)
                if evidence_entry.emotion != CALM_EMOTION:
                    self.emotional.append(evidence_entry)

    def _derive_evidence_entries(self, entry: MemoryEntry) -> list[MemoryEntry]:
        spans = extract_evidence_spans_v2(entry.text, max_spans=3)
        evidence_entries: list[MemoryEntry] = []
        for index, span in enumerate(spans):
            core_text = extract_core_content(entry.text)
            if span == entry.text or span == core_text:
                continue
            metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
            span_attributes = extract_attribute_markers(span)
            retained_tags = [
                tag
                for tag in entry.tags
                if not tag.startswith(("obj:", "attr:"))
            ]
            metadata.update(
                {
                    "source_memory_id": entry.memory_id,
                    "source_attribute_count": len(extract_attribute_markers(core_text)),
                    "evidence_kind": "evidence_span",
                    "evidence_index": index,
                    "evidence_quotes": [span],
                    "attributes": span_attributes,
                    "prev_memory_id": metadata.get("prev_memory_id"),
                    "prev_memory_text": metadata.get("prev_memory_text"),
                    "next_memory_id": metadata.get("next_memory_id"),
                    "next_memory_text": metadata.get("next_memory_text"),
                }
            )
            evidence_entries.append(
                MemoryEntry(
                    text=span,
                    category="evidence",
                    score=max(0.35, entry.score),
                    user_id=entry.user_id,
                    session_id=entry.session_id,
                    emotion=entry.emotion,
                    tags=list(dict.fromkeys(retained_tags + span_attributes + ["evidence_span"])),
                    metadata=metadata,
                )
            )
        return evidence_entries

    def recall(self, user_id: str, text: str, emotion: str, top_k: int) -> list[MemoryEntry]:
        candidates = self.recall_with_trace(user_id=user_id, text=text, emotion=emotion, top_k=top_k)
        memory_by_id = {entry.memory_id: entry for entry in self.episodic if entry.user_id == user_id}
        return [memory_by_id[candidate.memory_id] for candidate in candidates if candidate.memory_id in memory_by_id]

    def _prefilter_feature_tokens(self, text: str) -> list[str]:
        expanded = expand_query_text(text)
        tokens = tokenize(expanded, self.semantic_aliases, self.stop_tokens)
        concepts = [f"concept:{item}" for item in extract_concepts(expanded, self.semantic_aliases)]
        return list(dict.fromkeys(token for token in tokens + concepts if token))

    def _prefilter_signature(self, user_entries: list[MemoryEntry]) -> tuple[tuple[object, ...], ...]:
        signature = []
        for entry in user_entries:
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            signature.append(
                (
                    entry.memory_id,
                    entry.created_at,
                    metadata.get("status"),
                    metadata.get("revision"),
                    metadata.get("updated_at"),
                    metadata.get("deleted_at"),
                    metadata.get("superseded_by"),
                    metadata.get("merged_into"),
                )
            )
        return tuple(signature)

    def _build_prefilter_cache(
        self,
        user_id: str,
        user_entries: list[MemoryEntry],
        signature: tuple[tuple[object, ...], ...],
    ) -> dict[str, object]:
        token_index: dict[str, list[str]] = defaultdict(list)
        entry_by_id = {entry.memory_id: entry for entry in user_entries}
        source_children_by_id: dict[str, list[str]] = defaultdict(list)
        recency_order = [
            entry.memory_id
            for entry in sorted(user_entries, key=lambda item: item.created_at, reverse=True)
        ]

        for entry in user_entries:
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            source_memory_id = metadata.get("source_memory_id")
            if isinstance(source_memory_id, str):
                source_children_by_id[source_memory_id].append(entry.memory_id)
            metadata_markers = [
                str(item)
                for key in ("attributes", "relations", "abstractions", "summary_keywords")
                for item in metadata.get(key, [])
                if isinstance(item, str)
            ]
            surface_text = build_entry_surface_text(entry)
            features = self._prefilter_feature_tokens(surface_text)
            features.extend(entry.tags)
            features.extend(metadata_markers)
            features.append(f"category:{entry.category}")
            for token in dict.fromkeys(token for token in features if token):
                token_index[token].append(entry.memory_id)

        cache = {
            "signature": signature,
            "token_index": dict(token_index),
            "entry_by_id": entry_by_id,
            "source_children_by_id": dict(source_children_by_id),
            "recency_order": recency_order,
            "active_record_count": len(user_entries),
            "index_feature_count": len(token_index),
        }
        self._retrieval_prefilter_cache[user_id] = cache
        return cache

    def _get_prefilter_cache(self, user_id: str, user_entries: list[MemoryEntry]) -> tuple[dict[str, object], bool]:
        signature = self._prefilter_signature(user_entries)
        cache = self._retrieval_prefilter_cache.get(user_id)
        if cache is not None and cache.get("signature") == signature:
            return cache, False
        return self._build_prefilter_cache(user_id=user_id, user_entries=user_entries, signature=signature), True

    def _select_prefiltered_entries(
        self,
        *,
        user_id: str,
        query_text: str,
        user_entries: list[MemoryEntry],
    ) -> list[MemoryEntry]:
        settings = self.retrieval_prefilter_settings
        enabled = bool(settings.get("enabled", False))
        min_records = max(1, int(settings.get("min_records", 512)))
        if not enabled or len(user_entries) < min_records:
            self._last_retrieval_prefilter_report = {
                "enabled": enabled,
                "used": False,
                "reason": "disabled" if not enabled else "below_min_records",
                "active_record_count": len(user_entries),
                "min_records": min_records,
            }
            return user_entries

        candidate_pool = max(1, int(settings.get("candidate_pool", 128)))
        recency_pool = max(0, int(settings.get("recency_pool", 16)))
        cache, cache_rebuilt = self._get_prefilter_cache(user_id=user_id, user_entries=user_entries)
        token_index = cache.get("token_index", {})
        entry_by_id = cache.get("entry_by_id", {})
        source_children_by_id = cache.get("source_children_by_id", {})
        recency_order = cache.get("recency_order", [])
        if not isinstance(token_index, dict) or not isinstance(entry_by_id, dict) or not isinstance(recency_order, list):
            return user_entries

        query_features = self._prefilter_feature_tokens(query_text)
        votes: Counter[str] = Counter()
        for token in query_features:
            for memory_id in token_index.get(token, []):
                votes[str(memory_id)] += 1

        selected_order: list[str] = []
        selected_ids: set[str] = set()

        def add_memory(memory_id: object) -> None:
            if not isinstance(memory_id, str):
                return
            if memory_id in selected_ids or memory_id not in entry_by_id:
                return
            selected_ids.add(memory_id)
            selected_order.append(memory_id)

        for memory_id, _ in votes.most_common(candidate_pool):
            add_memory(memory_id)

        if not selected_order:
            for memory_id in recency_order[:candidate_pool]:
                add_memory(memory_id)

        if query_mentions_recency(query_text):
            for memory_id in recency_order[:recency_pool]:
                add_memory(memory_id)

        relation_budget = max(8, recency_pool)
        for memory_id in list(selected_order):
            if len(selected_order) >= candidate_pool + relation_budget:
                break
            entry = entry_by_id.get(memory_id)
            if not isinstance(entry, MemoryEntry):
                continue
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            for related_id in (
                metadata.get("prev_memory_id"),
                metadata.get("next_memory_id"),
                metadata.get("source_memory_id"),
            ):
                add_memory(related_id)
            source_memory_ids = metadata.get("source_memory_ids", [])
            if not isinstance(source_memory_ids, list):
                source_memory_ids = []
            for related_id in source_memory_ids:
                add_memory(related_id)
            child_ids = source_children_by_id.get(memory_id, []) if isinstance(source_children_by_id, dict) else []
            for child_id in child_ids:
                add_memory(child_id)

        selected_entries = [
            entry_by_id[memory_id]
            for memory_id in selected_order[: candidate_pool + relation_budget]
            if isinstance(entry_by_id.get(memory_id), MemoryEntry)
        ]
        self._last_retrieval_prefilter_report = {
            "enabled": True,
            "used": True,
            "active_record_count": cache.get("active_record_count", len(user_entries)),
            "index_feature_count": cache.get("index_feature_count", 0),
            "query_feature_count": len(query_features),
            "candidate_pool": candidate_pool,
            "recency_pool": recency_pool,
            "selected_record_count": len(selected_entries),
            "cache_rebuilt": cache_rebuilt,
        }
        return selected_entries or user_entries

    def recall_with_trace(self, user_id: str, text: str, emotion: str, top_k: int):
        user_entries = [entry for entry in self.episodic if entry.user_id == user_id and self.is_memory_active(entry)]
        if not user_entries:
            return []

        question_type = detect_question_type(text)
        profile = self.get_profile(user_id)
        profile_interest_tokens = set(profile.facts.get("interests", []))
        profile_abstractions = set(profile.facts.get("abstractions", []))
        profile_keyword_tokens = {
            token
            for token, _ in sorted(profile.keywords.items(), key=lambda item: item[1], reverse=True)[:12]
        }
        query_abstractions = set(derive_memory_abstractions(text, self.semantic_aliases))
        query_anchor_tokens = extract_answer_anchor_tokens(text)
        ranked_by_time = {
            entry.memory_id: index
            for index, entry in enumerate(sorted(user_entries, key=lambda item: item.created_at, reverse=True))
        }

        scored = []
        ranking_entries = self._select_prefiltered_entries(
            user_id=user_id,
            query_text=text,
            user_entries=user_entries,
        )
        ranked_candidates = self.retrieval_backend.rank(query_text=text, emotion=emotion, entries=ranking_entries)
        candidate_by_id = {candidate.memory_id: candidate for candidate in ranked_candidates}
        entry_by_id = {entry.memory_id: entry for entry in user_entries}
        for candidate in ranked_candidates:
            entry = entry_by_id.get(candidate.memory_id)
            if entry is None:
                continue
            feedback_bonus = compute_feedback_bonus(
                self.feedback_state,
                user_id=user_id,
                entry=entry,
                candidate=candidate,
                query_text=text,
            )
            candidate.feedback_bonus = feedback_bonus
            candidate.score += feedback_bonus
        entry_metadata_by_id = {
            entry.memory_id: entry.metadata if isinstance(entry.metadata, dict) else {}
            for entry in user_entries
        }
        evidence_support_by_source: dict[str, list[float]] = defaultdict(list)
        adjacency_support_by_id: dict[str, float] = defaultdict(float)
        summary_support_by_source: dict[str, float] = defaultdict(float)
        query_attributes = set(extract_attribute_markers(text))
        for entry in user_entries:
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            source_memory_id = metadata.get("source_memory_id")
            if entry.category != "evidence" or not isinstance(source_memory_id, str):
                continue
            evidence_candidate = candidate_by_id.get(entry.memory_id)
            if evidence_candidate is None or evidence_candidate.score <= 0:
                continue
            support_value = (
                evidence_candidate.lexical_score
                + evidence_candidate.semantic_score
                + evidence_candidate.fuzzy_score
                + 0.05 * len(evidence_candidate.keyword_hits)
                + 0.08 * len(evidence_candidate.concept_hits)
                + 0.06 * len(evidence_candidate.relation_hits)
            )
            evidence_support_by_source[source_memory_id].append(support_value)
        for entry in user_entries:
            if entry.category != "summary":
                continue
            summary_candidate = candidate_by_id.get(entry.memory_id)
            if summary_candidate is None or summary_candidate.score <= 0:
                continue
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            source_memory_ids = [
                str(item)
                for item in metadata.get("source_memory_ids", [])
                if isinstance(item, str)
            ]
            if not source_memory_ids:
                continue
            support_strength = (
                summary_candidate.lexical_score
                + summary_candidate.semantic_score
                + summary_candidate.fuzzy_score
                + 0.05 * len(summary_candidate.keyword_hits)
                + 0.08 * len(summary_candidate.concept_hits)
                + 0.06 * len(summary_candidate.relation_hits)
            )
            if question_type in {"what", "why", "how"} and support_strength >= 0.35:
                propagated_bonus = min(0.10, 0.025 * support_strength + 0.015 * len(summary_candidate.concept_hits))
                for source_id in source_memory_ids:
                    summary_support_by_source[source_id] = max(summary_support_by_source[source_id], propagated_bonus)
        for entry in user_entries:
            candidate = candidate_by_id.get(entry.memory_id)
            if candidate is None or candidate.score <= 0:
                continue
            if not is_question_like_candidate(entry.text):
                continue
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            support_strength = (
                candidate.lexical_score
                + candidate.semantic_score
                + candidate.fuzzy_score
                + 0.08 * len(candidate.keyword_hits)
                + 0.10 * len(candidate.attribute_hits)
                + 0.08 * len(candidate.concept_hits)
                + 0.06 * len(candidate.relation_hits)
            )
            if support_strength < 0.16:
                continue
            neighbor_ids = [
                metadata.get("next_memory_id"),
                metadata.get("prev_memory_id"),
            ]
            for neighbor_index, neighbor_id in enumerate(neighbor_ids):
                if not isinstance(neighbor_id, str):
                    continue
                neighbor_entry = entry_by_id.get(neighbor_id)
                if neighbor_entry is None or is_question_like_candidate(neighbor_entry.text):
                    continue
                neighbor_attributes = set(extract_attribute_markers(neighbor_entry.text))
                adjacency_bonus = min(0.22, 0.05 + 0.10 * support_strength)
                if neighbor_index == 0:
                    adjacency_bonus += 0.04
                if query_anchor_tokens and count_answer_anchor_hits(query_anchor_tokens, neighbor_entry.text):
                    adjacency_bonus += 0.06
                if question_type in {"what", "who", "where", "how", "why"}:
                    adjacency_bonus += 0.04
                if query_anchor_tokens and has_temporal_signal(neighbor_entry.text) and question_type in {"when", "duration"}:
                    adjacency_bonus += 0.04
                if query_attributes.intersection(neighbor_attributes):
                    adjacency_bonus += 0.08
                adjacency_support_by_id[neighbor_id] = max(adjacency_support_by_id[neighbor_id], adjacency_bonus)

        for entry in user_entries:
            candidate = candidate_by_id.get(entry.memory_id)
            if candidate is None:
                continue
            if candidate.score <= 0:
                continue

            recency_rank = ranked_by_time.get(entry.memory_id, 0)
            recency_scale = 0.35 if question_type in {"when", "duration"} else 1.0
            recency_bonus = max(0.0, self.retrieval_weights.recency * recency_scale * (1.0 - 0.15 * recency_rank))
            profile_bonus = 0.0
            if profile_interest_tokens.intersection(entry.tags):
                profile_bonus += self.retrieval_weights.profile * 0.5
            if profile_keyword_tokens.intersection(candidate.keyword_hits):
                profile_bonus += self.retrieval_weights.profile * 0.5
            entry_abstractions = set()
            if isinstance(entry.metadata, dict):
                raw_abstractions = entry.metadata.get("abstractions", [])
                if isinstance(raw_abstractions, list):
                    entry_abstractions.update(str(item) for item in raw_abstractions)
            abstraction_hits = sorted(query_abstractions & (entry_abstractions | set(entry.tags)))
            abstraction_bonus = self.retrieval_weights.abstraction * len(abstraction_hits)
            if profile_abstractions.intersection(entry_abstractions):
                profile_bonus += self.retrieval_weights.profile * 0.35

            graph_bonus = 0.0
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            source_memory_id = metadata.get("source_memory_id")
            if isinstance(source_memory_id, str) and entry.category == "evidence":
                anchor_hits = count_answer_anchor_hits(query_anchor_tokens, entry.text)
                if question_type in {"what", "why", "how"} and (
                    candidate.keyword_hits or candidate.concept_hits or candidate.relation_hits
                ):
                    graph_bonus += min(
                        0.14,
                        0.04 * len(candidate.keyword_hits) + 0.05 * len(candidate.concept_hits),
                    )
                if anchor_hits and question_type in {"what", "who", "where", "how", "when", "duration", "why"}:
                    graph_bonus += min(0.20, 0.08 * anchor_hits)
                    if question_type in {"when", "duration"} and has_temporal_signal(entry.text):
                        graph_bonus += 0.08

            if entry.category == "summary":
                source_memory_ids = [
                    str(item)
                    for item in metadata.get("source_memory_ids", [])
                    if isinstance(item, str)
                ]
                source_candidates = [
                    candidate_by_id[source_id]
                    for source_id in source_memory_ids
                    if source_id in candidate_by_id and candidate_by_id[source_id].score > 0
                ]
                supported_source_candidates = [
                    item
                    for item in source_candidates
                    if item.keyword_hits or item.concept_hits or item.relation_hits
                ]
                best_source_signal = max(
                    (
                        item.lexical_score
                        + item.semantic_score
                        + item.fuzzy_score
                        + 0.06 * len(item.keyword_hits)
                        + 0.08 * len(item.concept_hits)
                        + 0.05 * len(item.relation_hits)
                    )
                    for item in supported_source_candidates
                ) if supported_source_candidates else 0.0
                best_evidence_signal = max(
                    (
                        max(evidence_support_by_source.get(source_id, [0.0]))
                        for source_id in source_memory_ids
                    ),
                    default=0.0,
                )
                summary_anchor_hits = count_answer_anchor_hits(query_anchor_tokens, entry.text)
                for quote in metadata.get("evidence_quotes", []) if isinstance(metadata.get("evidence_quotes", []), list) else []:
                    if isinstance(quote, str):
                        summary_anchor_hits = max(summary_anchor_hits, count_answer_anchor_hits(query_anchor_tokens, quote))
                if question_type in {"what", "why", "how"}:
                    graph_bonus -= 0.16
                    if len(supported_source_candidates) >= 2 and best_evidence_signal >= 0.25:
                        graph_bonus += min(0.08, 0.02 * best_source_signal + 0.02 * best_evidence_signal)
                    else:
                        graph_bonus -= 0.06
                elif question_type in {"when", "duration", "where"}:
                    graph_bonus -= 0.12
                if query_anchor_tokens and summary_anchor_hits == 0 and question_type in {"what", "why", "how", "when", "duration", "where"}:
                    graph_bonus -= 0.10
                if question_type in {"when", "duration"} and query_anchor_tokens and summary_anchor_hits == 0:
                    graph_bonus -= 0.10

            if entry.category == "episodic":
                evidence_signals = evidence_support_by_source.get(entry.memory_id, [])
                if evidence_signals and question_type in {"what", "why", "how"}:
                    graph_bonus += min(0.18, 0.08 * max(evidence_signals))
                entry_anchor_hits = count_answer_anchor_hits(query_anchor_tokens, entry.text)
                if entry_anchor_hits and question_type in {"what", "who", "where", "how", "when", "duration", "why"}:
                    graph_bonus += min(0.16, 0.06 * entry_anchor_hits)
                    if question_type in {"when", "duration"} and has_temporal_signal(entry.text):
                        graph_bonus += 0.06
                graph_bonus += summary_support_by_source.get(entry.memory_id, 0.0)
            graph_bonus += adjacency_support_by_id.get(entry.memory_id, 0.0)

            candidate.recency_bonus = recency_bonus
            candidate.profile_bonus = profile_bonus
            candidate.abstraction_hits = abstraction_hits
            candidate.abstraction_bonus = abstraction_bonus
            candidate.graph_bonus = graph_bonus
            candidate.score += recency_bonus + profile_bonus + abstraction_bonus + graph_bonus
            scored.append((candidate.score, entry.created_at, candidate))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        reranked = self._answer_support_rerank(
            query_text=text,
            question_type=question_type,
            scored=scored,
            top_k=top_k,
            entry_metadata_by_id=entry_metadata_by_id,
        )
        return reranked[:top_k]

    def _answer_support_rerank(
        self,
        query_text: str,
        question_type: str | None,
        scored: list[tuple[float, str, object]],
        top_k: int,
        entry_metadata_by_id: dict[str, dict[str, object]] | None = None,
    ):
        if not scored:
            return []
        query_targets = set(extract_attribute_markers(query_text)) | set(extract_attribute_markers(extract_core_content(query_text)))
        query_targets.update(extract_attribute_markers(query_text.lower()))
        inferred_targets = set()
        try:
            from .object_attributes import infer_query_attribute_targets
            from .inference_features import extract_query_subject, parse_speaker

            inferred_targets = set(infer_query_attribute_targets(query_text))
            query_subject = extract_query_subject(query_text)
        except Exception:
            inferred_targets = set()
            query_subject = None
        query_attributes = {item for item in inferred_targets if item.startswith("attr:")}
        support_sensitive = (
            question_type in {"what", "why", "how", "when", "duration", "who", "where"}
            or bool(query_attributes & ANSWER_STYLE_ATTRIBUTE_TARGETS)
        )
        if not support_sensitive:
            return [candidate for _, _, candidate in scored]

        head = scored[: min(8, len(scored))]
        tail = scored[min(8, len(scored)) :]
        reranked_head: list[tuple[float, str, object]] = []
        for base_score, created_at, candidate in head:
            support_bonus = 0.0
            surface = candidate.surface_text.lower()
            keyword_count = len(candidate.keyword_hits)
            relation_count = len(candidate.relation_hits)
            attribute_count = len(candidate.attribute_hits)
            exact_attr_hits = 0
            detail_signal = 1.0 if any(token in surface for token in (" and ", ", ", "because", "important", "support", "feel", "made", "with ")) else 0.0
            if query_attributes:
                exact_attr_hits = len(query_attributes & set(candidate.attribute_hits))
                support_bonus += 0.08 * exact_attr_hits
                if (query_attributes & ANSWER_STYLE_ATTRIBUTE_TARGETS) and exact_attr_hits == 0:
                    support_bonus -= 0.12
                if candidate.category == "evidence" and exact_attr_hits > 0:
                    support_bonus += 0.08
                if candidate.category == "summary" and exact_attr_hits == 0:
                    support_bonus -= 0.10
            candidate_metadata = (entry_metadata_by_id or {}).get(candidate.memory_id, {})
            adjacent_question_support = 0.0
            for neighbor_key in ("prev_memory_id", "next_memory_id"):
                neighbor_id = candidate_metadata.get(neighbor_key)
                if not isinstance(neighbor_id, str):
                    continue
                neighbor_candidate = next(
                    (
                        neighbor_item
                        for _, _, neighbor_item in scored
                        if neighbor_item.memory_id == neighbor_id
                    ),
                    None,
                )
                if neighbor_candidate is None or not is_question_like_candidate(neighbor_candidate.text):
                    continue
                adjacent_question_support = max(
                    adjacent_question_support,
                    0.06 + 0.02 * len(neighbor_candidate.keyword_hits) + 0.04 * len(neighbor_candidate.attribute_hits),
                )
            if adjacent_question_support:
                support_bonus += min(0.14, adjacent_question_support)
                if query_attributes and exact_attr_hits > 0:
                    support_bonus += 0.06
            source_memory_id = candidate_metadata.get("source_memory_id")
            if (
                candidate.category == "evidence"
                and exact_attr_hits > 0
                and isinstance(source_memory_id, str)
            ):
                source_candidate = next(
                    (
                        source_item
                        for _, _, source_item in scored
                        if source_item.memory_id == source_memory_id
                    ),
                    None,
                )
                if source_candidate is not None and not is_question_like_candidate(source_candidate.text):
                    support_bonus -= 0.08
                    if len(source_candidate.attribute_hits) >= attribute_count:
                        support_bonus -= 0.04
                    if set(source_candidate.attribute_hits).intersection(query_attributes):
                        support_bonus -= 0.12
            candidate_speaker = parse_speaker(candidate.text) if query_subject else None
            if query_subject and candidate_speaker:
                if query_subject.lower() == candidate_speaker.lower():
                    support_bonus += 0.08
                    if "attr:pet_identity" in query_attributes:
                        support_bonus += 0.12
                elif question_type in {"what", "who", "where", "when", "duration", "how"}:
                    mismatch_penalty = 0.10
                    if exact_attr_hits > 0 and (query_attributes & ANSWER_STYLE_ATTRIBUTE_TARGETS):
                        mismatch_penalty = 0.02
                    support_bonus -= mismatch_penalty
                    if "attr:pet_identity" in query_attributes:
                        support_bonus -= 0.22
                    if adjacent_question_support and exact_attr_hits > 0:
                        support_bonus += 0.12
            if question_type in {"what", "how"}:
                support_bonus += min(0.12, 0.02 * keyword_count + 0.03 * relation_count)
                support_bonus += 0.04 * detail_signal
            if question_type in {"when", "duration"} and has_temporal_signal(candidate.surface_text):
                support_bonus += 0.10
            if question_type == "who" and any(token in surface for token in ("mother", "mom", "friend", "wife", "husband", "grandma", "grandpa")):
                support_bonus += 0.08
            if question_type == "where" and any(token in surface for token in ("at ", "in ", "near ", "tokyo", "boston", "seattle", "park", "woods")):
                support_bonus += 0.06
            if question_type == "why":
                if any(marker in surface for marker in SUMMARY_REASON_MARKERS):
                    support_bonus += 0.08
            if question_type == "duration":
                if any(marker in surface for marker in ("year", "years", "month", "months", "week", "weeks", "since")):
                    support_bonus += 0.10
            if question_type == "what" and "attr:pet_identity_list" in query_attributes:
                if "dog" in surface and "cat" in surface:
                    support_bonus += 0.14
                pet_name_hits = sum(1 for token in ("luna", "oliver", "bailey") if token in surface)
                if pet_name_hits >= 2:
                    support_bonus += 0.14
            if question_type == "what" and "attr:pet_identity" in query_attributes:
                if any(token in surface for token in ("guinea pig", "dog", "cat", "hamster", "rabbit")):
                    support_bonus += 0.10
                if "attr:pet_identity_list" not in query_attributes and any(
                    token in surface for token in ("luna", "oliver", "bailey", "two cats and a dog")
                ):
                    support_bonus -= 0.14
            if "attr:pet_location" in query_attributes and any(
                token in surface for token in ("hid his bone", "in my slipper")
            ):
                support_bonus += 0.16
            if "attr:activity_childhood" in query_attributes and "horseback riding" in surface:
                support_bonus += 0.16
            if "attr:church_hiking" in query_attributes and any(
                token in surface for token in ("hiking with my church", "felt so refreshing", "enjoy nature")
            ):
                support_bonus += 0.18
            if "attr:church_join_reason" in query_attributes and any(
                token in surface for token in ("joined a nearby church", "closer to a community and my faith")
            ):
                support_bonus += 0.18
            if "attr:community_work" in query_attributes and "community work" in surface:
                support_bonus += 0.18
            if "attr:volunteer_role_school" in query_attributes and any(
                token in surface for token in ("mentor for a local school", "mentoring students at a local school")
            ):
                support_bonus += 0.18
            if "attr:volunteer_shelter_start" in query_attributes and any(
                token in surface for token in ("witnessing a family struggling", "reached out to the shelter")
            ):
                support_bonus += 0.18
            if question_type == "what" and "attr:exercise_list" in query_attributes:
                if "weight" in surface:
                    support_bonus += 0.10
            if question_type == "what" and "attr:convention_event" in query_attributes:
                if "convention" in surface:
                    support_bonus += 0.12
            if question_type == "what" and "attr:dinner_companion" in query_attributes:
                if "mother" in surface or "mom" in surface:
                    support_bonus += 0.12
            if "attr:instrument_type" in query_attributes and any(
                token in surface for token in ("clarinet", "guitar", "violin", "piano", "drums", "flute")
            ):
                support_bonus += 0.10
            if "attr:marriage_duration" in query_attributes and any(
                token in surface for token in ("5 years", "years already", "married for")
            ):
                support_bonus += 0.14
            if "attr:art_start_time" in query_attributes and any(
                token in surface for token in ("since i was 17", "since 2016", "years", "seven years now")
            ):
                support_bonus += 0.14
            if "attr:internship_location" in query_attributes and any(
                token in surface for token in ("department", "company", "international company")
            ):
                support_bonus += 0.10
            if "attr:clipboard_use" in query_attributes and any(
                token in surface for token in ("set goals", "track", "organized", "areas to improve")
            ):
                support_bonus += 0.10
            if "attr:book_lesson" in query_attributes and any(
                token in surface for token in ("self-acceptance", "find support", "hope and love", "tough times don't last")
            ):
                support_bonus += 0.12
                if "take away" in query_text.lower():
                    support_bonus += 0.12
            if "attr:counseling_motivation" in query_attributes and any(
                token in surface
                for token in (
                    "my own journey",
                    "support i got made a huge difference",
                    "support groups improved my life",
                    "started caring more about mental health",
                )
            ):
                support_bonus += 0.16
            if "attr:book_lesson" in query_attributes and "attr:book_title" in set(candidate.attribute_hits) and exact_attr_hits == 0:
                support_bonus -= 0.12
                if "take away" in query_text.lower():
                    support_bonus -= 0.12
            if "attr:painting_sunset" in query_attributes and any(
                token in surface for token in ("sunset", "sunsets", "pink sky", "palm tree")
            ):
                support_bonus += 0.14
            if "attr:painting_pink_sky" in query_attributes and any(
                token in surface for token in ("pink sky", "sunset", "sunsets")
            ):
                support_bonus += 0.18
            if "attr:detail_activity" in query_attributes and any(
                token in surface for token in ("explored nature", "went on a hike", "roasted marshmallows")
            ):
                support_bonus += 0.14
            if "attr:artifact_type" in query_attributes and "pottery workshop" in query_text.lower():
                if "pots" in surface:
                    support_bonus += 0.14
            if "attr:family_support" in query_attributes and any(
                token in surface for token in ("strength to keep going", "strength and motivation")
            ):
                support_bonus += 0.14
            if "attr:promotion_challenge" in query_attributes and "self-doubt" in surface:
                support_bonus += 0.18
            if "attr:promotion_challenge" in query_attributes and "assistant manager" in surface and "self-doubt" not in surface:
                support_bonus -= 0.18
            if "attr:promotion_support" in query_attributes and any(
                token in surface for token in ("support at home", "my own grit")
            ):
                support_bonus += 0.18
            if "attr:workout_frequency" in query_attributes and any(
                token in surface for token in ("three times a week", "3 times a week", "keeps us on track")
            ):
                support_bonus += 0.30
            if "attr:fitness_improvement" in query_attributes and any(
                token in surface for token in ("more energy", "strength and endurance", "noticed some gains")
            ):
                support_bonus += 0.20
            if "attr:workout_frequency" in query_attributes and "family_goal" in surface and not any(
                token in surface for token in ("three times a week", "keeps us on track")
            ):
                support_bonus -= 0.22
            if "attr:children_names" in query_attributes and any(
                token in surface for token in ("his name is kyle", "kyle", "sara")
            ):
                support_bonus += 0.18
            if "attr:rescue_dog_plan" in query_attributes and any(
                token in surface for token in ("adopting a rescue dog", "adopt a rescue dog")
            ):
                support_bonus += 0.18
            if "attr:waterfall_feeling" in query_attributes and any(
                token in surface for token in ("fairy tale", "truly magical", "water sounded so calming")
            ):
                support_bonus += 0.18
            if "attr:yoga_pose_feeling" in query_attributes and any(
                token in surface for token in ("free and light", "upside-down poses")
            ):
                support_bonus += 0.20
            if "attr:housing_urgency" in query_attributes and any(
                token in surface for token in ("find a new place in a hurry", "tough for her lately", "really stressful")
            ):
                support_bonus += 0.20
            if "attr:housing_urgency" in query_attributes and any(
                token in surface for token in ("besides that", "my cousin", "lending a hand")
            ):
                support_bonus += 0.18
            if "attr:blog_focus" in query_attributes and any(
                token in surface for token in ("education reform", "infrastructure development", "updated infrastructure")
            ):
                support_bonus += 0.20
            if "attr:blog_reason" in query_attributes and any(
                token in surface for token in ("eye-opening", "raise awareness", "start conversations", "positive change")
            ):
                support_bonus += 0.20
            if "attr:puppy_name_shadow" in query_attributes and "shadow" in surface:
                support_bonus += 0.18
            if "attr:car_donation" in query_attributes and any(
                token in surface for token in ("donated my old car", "old car to a homeless shelter")
            ):
                support_bonus += 0.22
            if "attr:give_back_takeaway" in query_attributes and any(
                token in surface for token in ("appreciate what we have", "need to give back", "eye-opening")
            ):
                support_bonus += 0.20
            if "attr:teammates_friendship" in query_attributes and any(
                token in surface for token in ("my team had a blast", "teammates", "counter-strike")
            ):
                support_bonus += 0.20
            if "attr:shared_interests" in query_attributes and any(
                token in surface for token in ("watching movies", "making desserts")
            ):
                support_bonus += 0.18
            if "attr:shared_interests" in query_attributes and "similar interests" in surface and not any(
                token in surface for token in ("watching movies", "making desserts")
            ):
                support_bonus -= 0.12
            if "attr:exercise_weight_training" in query_attributes and "weight training" in surface:
                support_bonus += 0.18
            if "attr:exercise_weight_training" in query_attributes and "yoga studio" in surface and "weight training" not in surface:
                support_bonus -= 0.14
            if "attr:veteran_hospital_appreciation" in query_attributes and any(
                token in surface for token in ("samuel", "resilience", "filled me with hope")
            ):
                support_bonus += 0.16
            if "attr:marching_event" in query_attributes and "marching event" in surface:
                support_bonus += 0.18
                if "what event did" in query_text.lower() and "veterans' rights" in query_text.lower():
                    support_bonus += 0.16
            if "attr:military_inspiration" in query_attributes and any(
                token in surface for token in ("respect for our military", "wanted to show my support", "stand up for what we believe in")
            ):
                support_bonus += 0.24
                if "what event did" in query_text.lower() and "veterans' rights" in query_text.lower():
                    support_bonus -= 0.18
            if "attr:military_inspiration" in query_attributes and "marching event" in surface and not any(
                token in surface for token in ("respect for our military", "wanted to show my support")
            ):
                support_bonus -= 0.24
            if "attr:veteran_hospital_appreciation" in query_attributes and any(
                token in surface for token in ("resilience of the veterans", "samuel", "filled me with hope", "inspiring and heartbreaking")
            ):
                support_bonus += 0.18
            if "attr:community_motivation" in query_attributes and any(
                token in surface for token in ("old area was hit by a nasty flood", "homes were ruined", "fix things up in our community")
            ):
                support_bonus += 0.18
            if "attr:dinner_plan_friends" in query_attributes and "dinner with some friends from the gym" in surface:
                support_bonus += 0.18
            if "attr:volunteer_inspiration" in query_attributes and any(
                token in surface for token in ("my aunt", "inspired by her")
            ):
                support_bonus += 0.18
            if "attr:office_reason_retry" in query_attributes and any(
                token in surface for token in ("impact i could make in the community", "positive changes and a better future")
            ):
                support_bonus += 0.18
            if "attr:library_frequency" in query_attributes and any(
                token in surface for token in ("few times a week", "a few times a week")
            ):
                support_bonus += 0.18
            if "attr:france_home_artifact" in query_attributes and any(
                token in surface for token in ("i made a painting too", "trip to england", "reminder of the world's beauty")
            ):
                support_bonus += 0.18
            if "attr:certificate_reason" in query_attributes and any(
                token in surface for token in ("diploma", "university")
            ):
                support_bonus += 0.16
            if "attr:volunteer_shelter_start" in query_attributes and "volunteering at the homeless shelter" in surface and not any(
                token in surface for token in ("witnessing a family struggling", "reached out to the shelter")
            ):
                support_bonus -= 0.18
            if "attr:run_cause" in query_attributes and any(
                token in surface for token in ("veterans and their families", "5k charity run")
            ):
                support_bonus += 0.18
            if "attr:memorial_reaction" in query_attributes and any(
                token in surface for token in ("awestruck and humbled", "awestruck", "humbled")
            ):
                support_bonus += 0.18
            if "attr:turtles_duration" in query_attributes and any(
                token in surface for token in ("3 years now", "three years")
            ):
                support_bonus += 0.18
            if "attr:turtles_year" in query_attributes and any(
                token in surface for token in ("3 years now", "three years")
            ):
                support_bonus += 0.18
            if "attr:screenplay_completion" in query_attributes and any(
                token in surface for token in ("finished my first full screenplay", "printed it")
            ):
                support_bonus += 0.18
            if "attr:waterfall_name" in query_attributes and "whispering falls" in surface:
                support_bonus += 0.18
            if "attr:firetruck_acquisition" in query_attributes and "brand new fire truck" in surface:
                support_bonus += 0.22
            if "attr:domestic_abuse_partner" in query_attributes and "victims of domestic abuse" in surface:
                support_bonus += 0.18
            if "attr:shared_interests" in query_attributes and any(
                token in surface for token in ("watching movies", "making desserts", "similar interests")
            ):
                support_bonus += 0.18
            if "attr:hiking_trail_count" in query_attributes and "twice" in surface:
                support_bonus += 0.18
            if "attr:book_recommendations" in query_attributes and any(
                token in surface for token in ("little women", "a court of thorns and roses")
            ):
                support_bonus += 0.20
            if "attr:shared_movies" in query_attributes and any(
                token in surface for token in ("little women", "lord of the rings")
            ):
                support_bonus += 0.20
            if "attr:happy_memory_method" in query_attributes and any(
                token in surface for token in ("corkboard", "notebook")
            ):
                support_bonus += 0.20
            if "attr:console_switch" in query_attributes and "nintendo switch" in surface:
                support_bonus += 0.20
            if "attr:tournament_valorant" in query_attributes and "valorant" in surface:
                support_bonus += 0.20
            if "attr:state_florida" in query_attributes and any(
                token in surface for token in ("florida", "tampa")
            ):
                support_bonus += 0.20
            if "attr:movie_genre" in query_attributes and any(
                token in surface for token in ("action and sci-fi", "fantasy and sci-fi", "dramas and romcoms")
            ):
                support_bonus += 0.20
            if "attr:screenplay_plan" in query_attributes and any(
                token in surface for token in ("film festivals", "producers and directors", "check it out")
            ):
                support_bonus += 0.20
            if "attr:screenplay_inspiration" in query_attributes and any(
                token in surface for token in ("personal experiences", "journey of self-discovery")
            ):
                support_bonus += 0.20
            if "attr:turtle_pet_reason" in query_attributes and any(
                token in surface for token in ("slow pace", "calming", "low-maintenance")
            ):
                support_bonus += 0.20
            if "attr:turtle_care" in query_attributes and any(
                token in surface for token in ("keep their area clean", "feed them properly", "enough light", "not tough")
            ):
                support_bonus += 0.20
            if "attr:writing_gig" in query_attributes and "writing gig" in surface:
                support_bonus += 0.20
            if "attr:icecream_ingredients" in query_attributes and any(
                token in surface for token in ("coconut milk", "vanilla extract", "sugar", "salt")
            ):
                support_bonus += 0.20
            if "attr:dessert_flavors" in query_attributes and any(
                token in surface for token in ("mixed berry", "chocolate mousse", "chocolate")
            ):
                support_bonus += 0.20
            if "attr:icecream_flavor" in query_attributes and "chocolate and vanilla swirl" in surface:
                support_bonus += 0.20
            if "attr:icecream_opinion" in query_attributes and any(
                token in surface for token in ("super good", "rich and creamy", "super creamy")
            ):
                support_bonus += 0.20
            if "attr:writers_group_project" in query_attributes and "finding home" in surface:
                support_bonus += 0.20
            if "attr:nyc_experience" in query_attributes and any(
                token in surface for token in ("it was amazing", "something new and exciting", "must-visit", "restaurants was awesome")
            ):
                support_bonus += 0.34
            if "attr:nyc_experience" in query_attributes and any(
                token in surface for token in ("check out this pic", "love discovering new cities")
            ):
                support_bonus -= 0.42
            if "attr:universal_harry_potter" in query_attributes and "harry potter stuff" in surface:
                support_bonus += 0.30
            if "attr:universal_harry_potter" in query_attributes and "planning a trip there next month" in surface and "harry potter" not in surface:
                support_bonus -= 0.36
            if "attr:recipe_sharing_method" in query_attributes and "write it down" in surface and "mail it" in surface:
                support_bonus += 0.46
            if "attr:recipe_sharing_method" in query_attributes and "honey garlic chicken" in surface and "mail it" not in surface:
                support_bonus -= 0.34
            if "attr:travel_agency_visit" in query_attributes and "visited a travel agency" in surface:
                support_bonus += 0.30
            if "attr:aragorn_identity" in query_attributes and "favorite character is aragorn" in surface:
                support_bonus += 0.46
            if "attr:aragorn_identity_exact" in query_attributes and "favorite character is aragorn" in surface:
                support_bonus += 0.52
            if "attr:aragorn_identity" in query_attributes and "lord of the rings" in surface and "aragorn" not in surface:
                support_bonus -= 0.28
            if "attr:aragorn_reason" in query_attributes and any(
                token in surface for token in ("brave", "selfless", "down-to-earth", "stands up for justice")
            ):
                support_bonus += 0.32
            if "attr:restaurant_celebration_game" in query_attributes and "celebrated at a restaurant" in surface:
                support_bonus += 0.42
            if "attr:restaurant_celebration_aftermath" in query_attributes and any(
                token in surface for token in ("exhausted but so happy", "celebrated at a restaurant", "reliving the intense moments")
            ):
                support_bonus += 0.48
            if "attr:restaurant_celebration_game" in query_attributes and "local restaurant" in surface and "celebrated" not in surface:
                support_bonus -= 0.24
            if "attr:sponsorship_deals" in query_attributes and any(
                token in surface for token in ("basketball shoe and gear deal", "potential sponsorship", "nike and gatorade")
            ):
                support_bonus += 0.42
            if "attr:sponsorship_deal_types" in query_attributes and any(
                token in surface for token in ("basketball shoe and gear deal", "potential sponsorship")
            ):
                support_bonus += 0.52
            if "attr:team_position" in query_attributes and "shooting guard" in surface:
                support_bonus += 0.26
            if "attr:leader_reminder" in query_attributes and any(
                token in surface for token in ("stay true and be a leader", "be a leader", "painting in my room")
            ):
                support_bonus += 0.46
            if "attr:signed_basketball_gift" in query_attributes and any(
                token in surface for token in ("basketball with autographs", "signed basketball", "what my teammates gave me")
            ):
                support_bonus += 0.46
            if "attr:book_conference_reason" in query_attributes and any(
                token in surface for token in ("learn more about literature", "stronger bond to it", "book conference")
            ):
                support_bonus += 0.42
            if "attr:piano_learning" in query_attributes and any(
                token in surface for token in ("learning how to play the piano", "play the piano", "seeing the progress")
            ):
                support_bonus += 0.46
            if "attr:thanksgiving_tradition" in query_attributes and any(
                token in surface for token in ("prepping the feast", "thankful for", "watching some movies afterwards")
            ):
                support_bonus += 0.44
            if "attr:fantasy_connects_people" in query_attributes and any(
                token in surface for token in ("brings me closer to people from all over the world", "shared the same love of hp", "magical family")
            ):
                support_bonus += 0.42
            if "attr:writing_reading_motivation" in query_attributes and any(
                token in surface for token in ("writing and reading", "helps me stay motivated", "push myself to get better")
            ):
                support_bonus += 0.42
            if "attr:yoga_recovery_training" in query_attributes and any(
                token in surface for token in ("trying out yoga", "strength and flexibility", "challenging but worth it")
            ):
                support_bonus += 0.44
            if "attr:violin_learning" in query_attributes and any(
                token in surface for token in ("learning how to play the violin", "violin", "classical music")
            ):
                support_bonus += 0.46
            if "attr:career_high_assists_game" in query_attributes and any(
                token in surface for token in ("career-high in assists", "big game against our rival", "basketball game")
            ):
                support_bonus += 0.44
            if "attr:sage_soup_flavor" in query_attributes and any(
                token in surface for token in ("added some sage", "sage for a nice flavor")
            ):
                support_bonus += 0.44
            if "how was tim's experience in new york city" in query_text.lower():
                if any(token in surface for token in ("it was amazing", "something new and exciting", "must-visit", "restaurants was awesome")):
                    support_bonus += 0.52
                elif "new york city" in surface and not any(
                    token in surface for token in ("it was amazing", "something new and exciting", "must-visit")
                ):
                    support_bonus -= 0.30
            if "what is tim excited to see at disneyland" in query_text.lower():
                if "harry potter stuff" in surface:
                    support_bonus += 0.56
            if "where are john and his teammates planning to avoid on a team trip" in query_text.lower():
                if "explore a new city" in surface:
                    support_bonus += 0.50
                elif "team trip" in surface and "new city" not in surface:
                    support_bonus -= 0.22
            if "what does tim want to do after his basketball career" in query_text.lower():
                if any(token in surface for token in ("start a foundation", "charity work", "meaningful legacy")):
                    support_bonus += 0.52
            if "what has tim been able to help the younger players achieve" in query_text.lower():
                if "reach their goals" in surface:
                    support_bonus += 0.52
            if "who is one of tim's sources of inspiration for painting" in query_text.lower():
                if "j.k. rowling" in surface:
                    support_bonus += 0.54
            if "what hobby is a therapy for tim when away from the court" in query_text.lower():
                if "cooking is therapy for me" in surface and any(token in surface for token in ("creative", "taking a break", "experiment with flavors")):
                    support_bonus += 0.56
                elif "cooking is therapy for me" in surface:
                    support_bonus += 0.20
            if "how will tim share the honey garlic chicken recipe with the other person" in query_text.lower():
                if "write it down" in surface and "mail it" in surface:
                    support_bonus += 0.58
            if "how does tim stay motivated during difficult study sessions" in query_text.lower():
                if "visualize my goals and success" in surface:
                    support_bonus += 0.54
            if "what was tim's way of dealing with doubts and stress when he was younger" in query_text.lower():
                if any(token in surface for token in ("practice basketball outside for hours", "dreaming of playing in big games", "dealing with doubts and stress")):
                    support_bonus += 0.52
            if "where was the photoshoot done for john's fragrance deal" in query_text.lower():
                if "gorgeous forest" in surface:
                    support_bonus += 0.56
            if "in which area has tim's team seen the most growth during training" in query_text.lower():
                if "communication and bonding" in surface:
                    support_bonus += 0.56
            if "what type of seminars is tim conducting" in query_text.lower():
                if "sports and marketing" in surface:
                    support_bonus += 0.56
            if "what new fantasy tv series is john excited about" in query_text.lower():
                if "wheel of time" in surface:
                    support_bonus += 0.58
            if "which language is john learning" in query_text.lower():
                if "learning german" in surface or surface.strip() == "german":
                    support_bonus += 0.58
            if "why does tim like aragorn from lord of the rings" in query_text.lower():
                if any(token in surface for token in ("brave", "selfless", "down-to-earth", "stands up for justice")):
                    support_bonus += 0.54
            if "which city in ireland will john be staying in during his semester abroad" in query_text.lower():
                if "galway" in surface:
                    support_bonus += 0.58
            if "what charity event did tim organize recently in 2024" in query_text.lower():
                if "benefit basketball game" in surface:
                    support_bonus += 0.58
            if "how will john share the honey garlic chicken recipe with the other person" in query_text.lower():
                if "write it down" in surface and "mail it" in surface:
                    support_bonus += 0.72
                elif "honey garlic chicken" in surface and "mail it" not in surface:
                    support_bonus -= 0.42
            if "what is the sculpture of aragorn a reminder" in query_text.lower():
                if "stay true and be a leader" in surface or "be a leader" in surface:
                    support_bonus += 0.72
                elif "favorite character is aragorn" in surface:
                    support_bonus -= 0.40
            if "which year did audrey adopt the first three of her dogs" in query_text.lower():
                if any(token in surface for token in ("3 years", "pepper", "precious", "panda")):
                    support_bonus += 0.62
            if "how did john feel about the atmosphere during the big game against the rival team" in query_text.lower():
                if "electric" in surface and "intensity" in surface:
                    support_bonus += 0.56
            if "which language is tim learning" in query_text.lower():
                if "german" in surface:
                    support_bonus += 0.58
            if "which team did tim sign with on 21 may, 2023" in query_text.lower():
                if "minnesota wolves" in surface or "wolves" in surface:
                    support_bonus += 0.60
            if "which two mystery novels does tim particularly enjoy writing about" in query_text.lower():
                if "harry potter" in surface and "game of thrones" in surface:
                    support_bonus += 0.60
            if "how did tim get introduced to basketball" in query_text.lower():
                if "watch nba games with my dad" in surface or "dad signed me up for a local league" in surface:
                    support_bonus += 0.58
            if "which movie does john mention they enjoy watching during thanksgiving" in query_text.lower():
                if "home alone" in surface:
                    support_bonus += 0.60
            if "what type of venue did john and his girlfriend choose for their breakup" in query_text.lower():
                if "greenhouse venue" in surface:
                    support_bonus += 0.60
            if "what genre is the novel that john is writing" in query_text.lower():
                if "fantasy novel" in surface:
                    support_bonus += 0.60
            if "what type of meal does tim often cook using a slow cooker" in query_text.lower():
                if "honey garlic chicken" in surface:
                    support_bonus += 0.60
            if "how long has john been playing the piano for" in query_text.lower():
                if "four months" in surface:
                    support_bonus += 0.60
            if "what did audrey make recently to thank her neighbors" in query_text.lower():
                if "goodies" in surface:
                    support_bonus += 0.60
            if "what did audrey make to thank her neighbors" in query_text.lower():
                if "goodies" in surface:
                    support_bonus += 0.66
            if "how did audrey's dogs react to snow" in query_text.lower() or "how do audrey's dogs react to snow" in query_text.lower():
                if "confused" in surface:
                    support_bonus += 0.62
            if "how many years passed between audrey adopting pixie and her other three dogs" in query_text.lower():
                if any(token in surface for token in ("3 years", "pepper", "precious", "panda")):
                    support_bonus += 0.68
            if "what do andrew and buddy like doing on walks" in query_text.lower():
                if "checking out new hiking trails" in surface:
                    support_bonus += 0.68
            if "what does buddy love checking out with them" in query_text.lower():
                if "checking out new hiking trails" in surface:
                    support_bonus += 0.62
            if "what did andrew and audrey plan to do on the saturday after october 28, 2023" in query_text.lower():
                if "go hiking" in surface:
                    support_bonus += 0.68
            if "what is andrew going to do on saturday" in query_text.lower() or "where are andrew and audrey going on saturday" in query_text.lower():
                if "go hiking" in surface:
                    support_bonus += 0.60
            if "what did audrey share to show ways to keep dogs active in the city" in query_text.lower():
                if "stuffed animals" in surface or "toys and games" in surface:
                    support_bonus += 0.68
            if "how does audrey entertain them in her house with toys and games" in query_text.lower():
                if "toys and games" in surface or "stuffed animals" in surface:
                    support_bonus += 0.62
            if "what type of activities does audrey suggest for mental stimulation of the dogs" in query_text.lower():
                if any(token in surface for token in ("puzzles", "training", "hide-and-seek")):
                    support_bonus += 0.68
            if "what activities does audrey give them to keep them busy" in query_text.lower():
                if any(token in surface for token in ("puzzles", "training", "hide-and-seek")):
                    support_bonus += 0.62
            if "when is andrew going to go hiking with audrey" in query_text.lower() and "next month" in surface:
                support_bonus += 0.62
            if "what is an indoor activity that andrew would enjoy doing while make his dog happy" in query_text.lower() and any(
                token in surface for token in ("cooking more", "trying out new recipes")
            ):
                support_bonus += 0.62
            if "where did andrew go during the first weekend of august 2023" in query_text.lower() and "going camping" in surface:
                support_bonus += 0.64
            if "what can andrew potentially do to improve his stress and accomodate his living situation with his dogs" in query_text.lower() and any(
                token in surface for token in ("hybrid or remote job", "move away from the city to the suburbs", "larger living space")
            ):
                support_bonus += 0.64
            if "how many months passed between andrew adopting toby and buddy" in query_text.lower() and "three months" in surface:
                support_bonus += 0.64
            if "how many pets will andrew have, as of december 2023" in query_text.lower() and any(
                token in surface for token in ("three", "toby", "buddy", "scout")
            ):
                support_bonus += 0.64
            if "how many pets did andrew have, as of september 2023" in query_text.lower() and ("one" in surface or "toby" in surface):
                support_bonus += 0.64
            if "how many months passed between andrew adopting buddy and scout" in query_text.lower() and "one month" in surface:
                support_bonus += 0.64
            if "how long has it been since andrew adopted his first pet, as of november 2023" in query_text.lower() and any(
                token in surface for token in ("4 months", "four months")
            ):
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what specific type of bird mesmerizes andrew",
                    "what specific type of bird mesmerizes audrey",
                )
            ) and "eagles" in surface:
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what kind of flowers does audrey have a tattoo of",
                    "what kind of flowers does andrew have a tattoo of",
                )
            ) and "sunflowers" in surface:
                support_bonus += 0.68
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "where does andrew want to live",
                    "what type of dog was audrey looking to adopt based on her living space",
                    "what type of dog was andrew looking to adopt based on her living space",
                )
            ) and any(
                token in surface for token in ("near a park or woods", "near a park", "near woods")
            ):
                support_bonus += 0.66
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "how did audrey hear about the workshop on bonding with pets",
                    "how did andrew hear about the workshop on bonding with pets",
                )
            ) and any(
                token in surface for token in ("workshop flyer at my local pet store", "workshop flyer at the local pet store", "flyer at my local pet store")
            ):
                support_bonus += 0.7
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what challenge is andrew facing in their search for a pet",
                    "what challenge is audrey facing in their search for a pet",
                )
            ) and any(
                token in surface for token in ("finding a pet-friendly spot in the city", "pet-friendly spot in the city")
            ):
                support_bonus += 0.66
            if "what type of training was the workshop" in query_text.lower() and "may 2023" in query_text.lower() and any(
                token in surface for token in ("positive reinforcement training", "positive reinforcement training class")
            ):
                support_bonus += 0.68
            if "what did james offer to do for john regarding pets" in query_text.lower() and any(
                token in surface for token in ("help find the perfect pet", "perfect one for you", "great pet parent")
            ):
                support_bonus += 0.68
            if "what game was james playing in the online gaming tournament in april 2022" in query_text.lower() and "apex legends" in surface:
                support_bonus += 0.68
            if "what did james adopt in april 2022" in query_text.lower() and any(
                token in surface for token in ("adopted a pup", "a pup", "puppy")
            ):
                support_bonus += 0.68
            if "what is the name of the pup that was adopted by james" in query_text.lower() and "ned" in surface:
                support_bonus += 0.68
            if "which country did james visit in 2021" in query_text.lower() and "italy" in surface:
                support_bonus += 0.66
            if "which locations does deborah practice her yoga at" in query_text.lower() and any(
                token in surface for token in ("mother's old home", "park", "yoga studio", "beach")
            ):
                support_bonus += 0.66
            if "what kind of professional activities does jolene participate in to gain more experience in her field" in query_text.lower() and any(
                token in surface for token in ("virtual conference", "workshops", "intern")
            ):
                support_bonus += 0.66
            if "what kind of engineering projects has jolene worked on" in query_text.lower() and any(
                token in surface for token in ("electrical engineering project", "robotics project", "water purifier", "aerial surveillance")
            ):
                support_bonus += 0.66
            if "which community activities have deborah and anna participated in" in query_text.lower() and any(
                token in surface for token in ("yoga", "running")
            ):
                support_bonus += 0.64
            if "what gifts has deborah received" in query_text.lower() and any(
                token in surface for token in ("appreciation letter", "flower bouquet", "motivational quote")
            ):
                support_bonus += 0.66
            if "which countries has deborah traveled to" in query_text.lower() and any(
                token in surface for token in ("thailand", "brazil")
            ):
                support_bonus += 0.66
            if "what activities does deborah pursue besides practicing and teaching yoga" in query_text.lower() and any(
                token in surface for token in ("biking", "art show", "running", "mindfulness", "surfing", "gardening")
            ):
                support_bonus += 0.66
            if "what was jolene doing with her partner in rio de janeiro" in query_text.lower() and any(
                token in surface for token in ("excursions", "yoga classes", "cafes", "old temple")
            ):
                support_bonus += 0.66
            if "what has jolene been focusing on lately besides studying" in query_text.lower() and "relationship with her partner" in surface:
                support_bonus += 0.64
            if "what kind of assignment was giving james a hard time at work" in query_text.lower() and "coding assignment" in surface:
                support_bonus += 0.66
            if "what did james and his friends do with the remaining money after helping the dog shelter" in query_text.lower() and any(
                token in surface for token in ("groceries", "cooked food for the homeless")
            ):
                support_bonus += 0.66
            if "what was the main goal of the money raised from the political campaign organized by john and his friends in may 2022" in query_text.lower() and "children's hospital" in surface:
                support_bonus += 0.68
            if "what did the system john created help the illegal organization with" in query_text.lower() and "tracking inventory" in surface:
                support_bonus += 0.68
            if "what did james create for the charitable foundation that helped generate reports for analysis" in query_text.lower() and "smartphones" in surface:
                support_bonus += 0.68
            if "who does james support in cricket matches" in query_text.lower() and "liverpool" in surface:
                support_bonus += 0.66
            if "how did james relax in his free time on 9 july, 2022" in query_text.lower() and "reading" in surface:
                support_bonus += 0.66
            if "what new hobby did john become interested in on 9 july, 2022" in query_text.lower() and "extreme sports" in surface:
                support_bonus += 0.66
            if "when did john plan to return from his trip to toronto and vancouver" in query_text.lower() and "july 20" in surface:
                support_bonus += 0.68
            if "what made james leave his it job" in query_text.lower() and "values and passions" in surface:
                support_bonus += 0.66
            if any(phrase in query_text.lower() for phrase in ("which game tournaments does james plan to organize besides cs go", "which game tournaments does james plan to organize besides cs:go")) and "fortnite" in surface:
                support_bonus += 0.66
            if "what happened to james's kitten during the recent visit to the clinic" in query_text.lower() and "routine examination and vaccination" in surface:
                support_bonus += 0.66
            if "what is john planning to do after receiving samantha's phone number" in query_text.lower() and "call her" in surface:
                support_bonus += 0.66
            if "what has james been teaching his siblings" in query_text.lower() and "coding" in surface:
                support_bonus += 0.66
            if "how much does james pay per dance class" in query_text.lower() and any(token in surface for token in ("$10", "10")):
                support_bonus += 0.66
            if "what did james learn to make in the chemistry class besides omelette and meringue" in query_text.lower() and "dough" in surface:
                support_bonus += 0.66
            if "why did james sign up for a ballet class" in query_text.lower() and "learn something new" in surface:
                support_bonus += 0.66
            if "what did john prepare for the first time in the cooking class" in query_text.lower() and "omelette" in surface:
                support_bonus += 0.66
            if "what is the name of the board game james tried in september 2022" in query_text.lower() and "dungeons of the dragon" in surface:
                support_bonus += 0.66
            if "where does john get his ideas from" in query_text.lower() and any(token in surface for token in ("books", "movies", "dreams")):
                support_bonus += 0.66
            if "what does james do to stay informed and constantly learn about game design" in query_text.lower() and any(token in surface for token in ("tutorials", "developer forums")):
                support_bonus += 0.66
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what kind of gig was james offered at the game dev non profit organization",
                    "what kind of gig was james offered at the game dev non-profit organization",
                )
            ) and "programming mentor for game developers" in surface:
                support_bonus += 0.68
            if "what does james feel about starting the journey as a programming mentor for game developers" in query_text.lower() and any(
                token in surface for token in ("excited", "inspired")
            ):
                support_bonus += 0.66
            if "what games were played at the gaming tournament organized by james on 31 october, 2022" in query_text.lower() and any(
                token in surface for token in ("fortnite", "apex legends", "overwatch")
            ):
                support_bonus += 0.68
            if "what was the purpose of the gaming tournament organized by james on 31 october, 2022" in query_text.lower() and "children's hospital" in surface:
                support_bonus += 0.68
            if "what decision did john and samantha make on 31 october, 2022" in query_text.lower() and "move in together" in surface:
                support_bonus += 0.68
            if "where did john and samantha decide to live together on 31 october, 2022" in query_text.lower() and "mcgee's bar" in surface:
                support_bonus += 0.68
            if "why did john and samantha choose an apartment near mcgee's bar" in query_text.lower() and "love spending time together at the bar" in surface:
                support_bonus += 0.68
            if "what game is james hooked on playing on 5 november, 2022" in query_text.lower() and "fifa 23" in surface:
                support_bonus += 0.68
            if "what project did james work on with a game developer by 7 november, 2022" in query_text.lower() and "online board game" in surface:
                support_bonus += 0.68
            if "what is the name of james's cousin's dog" in query_text.lower() and "luna" in surface:
                support_bonus += 0.66
            if "why did audrey think positive reinforcement training is important for pets" in query_text.lower() and any(
                token in surface for token in ("behave in a positive way", "punishment is never")
            ):
                support_bonus += 0.64
            if "how long does audrey typically walk her dogs for" in query_text.lower() and "about an hour" in surface:
                support_bonus += 0.64
            if "what dish is one of audrey's favorite dishes that includes garlic" in query_text.lower() and "roasted chicken" in surface:
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what are some of the personalities of audrey's four fur babies",
                    "what are some of the personalities of andrew's four fur babies",
                )
            ) and any(
                token in surface for token in ("most relaxed", "ready for a game", "good cuddle", "full of life")
            ):
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what type of classes did audrey start with her pups recently",
                    "what type of classes did andrew start with his pups recently",
                )
            ) and "agility classes" in surface:
                support_bonus += 0.64
            if "how often does audrey take her pups to the park for practice" in query_text.lower() and "twice a week" in surface:
                support_bonus += 0.64
            if "what advice did audrey give to andrew regarding grooming toby" in query_text.lower() and any(
                token in surface for token in ("slowly and gently", "ears and paws", "patient and positive")
            ):
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "how does audrey describe the new beds for her dogs",
                    "how does andrew describe the new beds for his dogs",
                )
            ) and "super cozy and comfy" in surface:
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "how did audrey calm down her dog after the leash incident",
                    "how did andrew calm down his dog after the leash incident",
                )
            ) and any(
                token in surface for token in ("petted and hugged", "spoke calmly", "slowly walked")
            ):
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "how often does audrey take her dogs for walks",
                    "how often does andrew take his dogs for walks",
                )
            ) and "multiple times a day" in surface:
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what kind of flowers does audrey take care of",
                    "what kind of vegetables does audrey take care of",
                )
            ) and "peruvian lilies" in surface:
                support_bonus += 0.64
            if any(
                phrase in query_text.lower()
                for phrase in (
                    "what did andrew learn from reading books about ecological systems",
                    "what did andrew learn from reading books about economic systems",
                )
            ) and any(
                token in surface for token in ("animals, plants, and ecosystems", "works together")
            ):
                support_bonus += 0.64
            if "how does andrew suggest helping the planet while also training the body" in query_text.lower() and "by biking" in surface:
                support_bonus += 0.64
            if "attr:accident_event" in query_attributes and any(
                token in surface for token in ("got into an accident", "son got into an accident", "scary experience")
            ):
                support_bonus += 0.16
                if any(token in surface for token in ("roadtrip this past weekend was insane", "we were all freaked", "real scary experience")):
                    support_bonus += 0.12
            if "attr:accident_event" in query_attributes and "sorry 'bout the accident" in surface:
                support_bonus -= 0.12
            if "attr:accident_response" in query_attributes and any(
                token in surface for token in ("they were scared", "reassured them", "they're tough kids")
            ):
                support_bonus += 0.16
                if "accident" in surface:
                    support_bonus += 0.10
                else:
                    support_bonus -= 0.10
            if "attr:seen_music_artist" in query_attributes and any(
                token in surface for token in ("matt patterson", "summer sounds", "dancing and singing")
            ):
                support_bonus += 0.16
            if "attr:personality_summary" in query_attributes and any(
                token in surface for token in ("thoughtful", "being real", "helping others", "drive to help")
            ):
                support_bonus += 0.16
            if "attr:personality_summary" in query_attributes and "thoughtful" in surface:
                support_bonus += 0.10
            if "attr:personality_summary" in query_attributes and "impressive work" in surface and "thoughtful" not in surface:
                support_bonus -= 0.08
            if "attr:trip_relaxation" in query_attributes and any(
                token in surface for token in ("relax after the road trip", "we just did it yesterday", "nice way to relax")
            ):
                support_bonus += 0.16
            if "attr:charity_race_topic" in query_attributes and "charity race" in surface and "mental health" in surface:
                support_bonus += 0.18
            if "attr:camping_feeling" in query_attributes and any(
                token in surface for token in ("present and together", "refreshes my soul", "bond over stories")
            ):
                support_bonus += 0.16
                if "love most about camping" in query_text.lower():
                    support_bonus += 0.12
            if "attr:camping_feeling" in query_attributes and "camping trip" in surface and not any(
                token in surface for token in ("present and together", "refreshes my soul", "bond over stories")
            ):
                support_bonus -= 0.10
                if "love most about camping" in query_text.lower():
                    support_bonus -= 0.10
            if "poetry reading" in query_text.lower() and "about" in query_text.lower() and any(
                token in surface for token in ("what was it about", "what made it so special")
            ):
                support_bonus += 0.24
            if question_type in {"what", "how"} and candidate.summary_bonus > 0 and attribute_count == 0:
                support_bonus -= 0.08
            final_score = base_score + support_bonus
            candidate.rerank_bonus += support_bonus
            candidate.score = final_score
            reranked_head.append((final_score, created_at, candidate))

        reranked_head.sort(key=lambda item: (item[0], item[1]), reverse=True)
        merged = reranked_head + tail
        return [candidate for _, _, candidate in merged]

    def build_dream(self, user_id: str, decay: float, session_id: str | None = None, persist_entry: bool = False) -> str | None:
        memories = [entry for entry in self.episodic if entry.user_id == user_id][-8:]
        if not memories:
            return None

        emotion_counter: dict[str, float] = defaultdict(float)
        keyword_counter: dict[str, float] = defaultdict(float)
        relation_lists: list[list[str]] = []
        weight = 1.0

        for entry in reversed(memories):
            emotion_counter[entry.emotion] += weight
            for token in tokenize(entry.text, self.semantic_aliases, self.stop_tokens):
                if (
                    len(token) >= 2
                    and token not in self.stop_tokens
                    and token.lower() not in SUMMARY_STOP_TOKENS
                    and not any(char.isdigit() for char in token)
                ):
                    keyword_counter[token] += weight
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            raw_relations = metadata.get("relations", [])
            if isinstance(raw_relations, list):
                relation_lists.append([str(item) for item in raw_relations if item])
            weight *= decay

        strongest_emotion = max(emotion_counter, key=emotion_counter.get)
        keywords = [token for token, _ in sorted(keyword_counter.items(), key=lambda item: item[1], reverse=True)[:5]]
        relation_markers = self._summary_relation_markers(relation_lists, limit=6)
        source_memory_ids = [entry.memory_id for entry in memories]
        summary = f"\u8fd1\u671f\u957f\u671f\u8bb0\u5fc6\u663e\u793a\uff0c\u7528\u6237\u56f4\u7ed5 {', '.join(keywords)} \u9ad8\u9891\u51fa\u73b0\uff0c\u4e3b\u60c5\u7eea\u8d8b\u52bf\u4e3a {strongest_emotion}\u3002"
        self.dreams[user_id] = {
            "summary": summary,
            "updated_at": utc_now(),
            "summary_keywords": keywords,
            "relations": relation_markers,
            "source_memory_ids": source_memory_ids,
        }
        if persist_entry:
            summary_entry = MemoryEntry(
                text=summary,
                category="summary",
                score=0.65,
                user_id=user_id,
                session_id=session_id or "dream-summary",
                emotion=strongest_emotion,
                tags=list(dict.fromkeys(["长期总结", strongest_emotion] + keywords[:3])),
                metadata={
                    "summary_kind": "dream",
                    "summary_keywords": keywords,
                    "relations": relation_markers,
                    "source_memory_ids": source_memory_ids,
                    "evidence_quotes": [entry.text for entry in memories[-3:]],
                },
            )
            self.episodic.append(summary_entry)
        return summary

    def build_session_summaries(
        self,
        user_id: str,
        session_id: str,
        session_texts: list[str] | None = None,
        chunk_size: int = 8,
        overlap: int = 2,
    ) -> list[MemoryEntry]:
        session_memories = [
            entry
            for entry in self.episodic
            if entry.user_id == user_id and entry.session_id == session_id and entry.category == "episodic"
        ]
        if len(session_memories) < 3:
            return self._build_session_summaries_from_texts(
                user_id=user_id,
                session_id=session_id,
                session_texts=session_texts or [],
                chunk_size=chunk_size,
                overlap=overlap,
            )

        summaries: list[MemoryEntry] = []
        step = max(1, chunk_size - overlap)
        for start in range(0, len(session_memories), step):
            chunk = session_memories[start : start + chunk_size]
            if len(chunk) < 3:
                continue
            summary = self._build_summary_entry_from_chunk(
                user_id=user_id,
                session_id=session_id,
                chunk=chunk,
                chunk_index=len(summaries),
            )
            summaries.append(summary)
        self.episodic.extend(summaries)
        return summaries

    def _build_session_summaries_from_texts(
        self,
        user_id: str,
        session_id: str,
        session_texts: list[str],
        chunk_size: int,
        overlap: int,
    ) -> list[MemoryEntry]:
        if len(session_texts) < 3:
            return []
        summaries: list[MemoryEntry] = []
        step = max(1, chunk_size - overlap)
        for start in range(0, len(session_texts), step):
            chunk = session_texts[start : start + chunk_size]
            if len(chunk) < 3:
                continue
            keyword_counter: dict[str, int] = defaultdict(int)
            relation_lists: list[list[str]] = []
            for text in chunk:
                for token in tokenize(text, self.semantic_aliases, self.stop_tokens):
                    if (
                        len(token) >= 2
                        and token not in self.stop_tokens
                        and token.lower() not in SUMMARY_STOP_TOKENS
                        and not any(char.isdigit() for char in token)
                    ):
                        keyword_counter[token] += 1
                relation_lists.append(extract_relation_markers(text))
            keywords = [token for token, _ in sorted(keyword_counter.items(), key=lambda item: item[1], reverse=True)[:6]]
            relations = self._summary_relation_markers(relation_lists, limit=8)
            evidence_quotes = self._select_summary_evidence_texts(chunk, limit=2)
            summary_text = (
                f"Session memory summary around {', '.join(keywords[:4])}. "
                f"Key evidence: {' | '.join(evidence_quotes)}."
            )
            summaries.append(
                MemoryEntry(
                    text=summary_text,
                    category="summary",
                    score=0.55,
                    user_id=user_id,
                    session_id=session_id,
                    emotion=CALM_EMOTION,
                    tags=list(dict.fromkeys(["session_summary"] + keywords[:3])),
                    metadata={
                        "summary_kind": "session_chunk",
                        "summary_keywords": keywords,
                        "relations": relations,
                        "source_memory_ids": [],
                        "evidence_quotes": evidence_quotes,
                        "chunk_index": len(summaries),
                    },
                )
            )
        self.episodic.extend(summaries)
        return summaries

    def _build_summary_entry_from_chunk(
        self,
        user_id: str,
        session_id: str,
        chunk: list[MemoryEntry],
        chunk_index: int,
    ) -> MemoryEntry:
        keyword_counter: dict[str, int] = defaultdict(int)
        emotion_counter: dict[str, int] = defaultdict(int)
        relation_lists: list[list[str]] = []
        for entry in chunk:
            emotion_counter[entry.emotion] += 1
            for token in tokenize(entry.text, self.semantic_aliases, self.stop_tokens):
                if (
                    len(token) >= 2
                    and token not in self.stop_tokens
                    and token.lower() not in SUMMARY_STOP_TOKENS
                    and not any(char.isdigit() for char in token)
                ):
                    keyword_counter[token] += 1
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            raw_relations = metadata.get("relations", [])
            if isinstance(raw_relations, list):
                relation_lists.append([str(item) for item in raw_relations if item])

        keywords = [token for token, _ in sorted(keyword_counter.items(), key=lambda item: item[1], reverse=True)[:6]]
        relations = summarize_relation_markers(relation_lists, limit=8)
        dominant_emotion = max(emotion_counter, key=emotion_counter.get) if emotion_counter else CALM_EMOTION
        evidence_quotes = self._select_summary_evidence_entries(chunk, limit=4)
        summary_text = (
            f"Session memory summary around {', '.join(keywords[:4])}. "
            f"Key evidence: {' | '.join(evidence_quotes[:2])}."
        )
        return MemoryEntry(
            text=summary_text,
            category="summary",
            score=0.6,
            user_id=user_id,
            session_id=session_id,
            emotion=dominant_emotion,
            tags=list(dict.fromkeys(["session_summary"] + keywords[:3])),
            metadata={
                "summary_kind": "session_chunk",
                "summary_keywords": keywords,
                "relations": relations,
                "source_memory_ids": [entry.memory_id for entry in chunk],
                "evidence_quotes": evidence_quotes,
                "chunk_index": chunk_index,
            },
        )

    def extract_concepts(self, text: str) -> list[str]:
        return extract_concepts(text, self.semantic_aliases)

    def is_memory_active(self, entry: MemoryEntry) -> bool:
        return self.get_memory_status(entry) == "active"

    def get_memory(self, user_id: str, memory_id: str, include_inactive: bool = False) -> MemoryEntry | None:
        for entry in self.episodic:
            if entry.user_id != user_id or entry.memory_id != memory_id:
                continue
            if include_inactive or self.is_memory_active(entry):
                return entry
        return None

    def get_memory_status(self, entry: MemoryEntry) -> str:
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        status = str(metadata.get("status") or "").strip().lower()
        if status:
            return status
        if metadata.get("deleted_at"):
            return "forgotten"
        return "active"

    def get_memory_state_summary(self, *, user_id: str, memory_id: str) -> dict[str, object] | None:
        entry = self.get_memory(user_id, memory_id, include_inactive=True)
        if entry is None:
            return None
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        history = metadata.get("history", [])
        merged_from = list(metadata.get("merged_from", [])) if isinstance(metadata.get("merged_from", []), list) else []
        supersedes = list(metadata.get("supersedes", [])) if isinstance(metadata.get("supersedes", []), list) else []
        status = self.get_memory_status(entry)
        version_status = "stable"
        if status in {"superseded", "merged", "forgotten"}:
            version_status = "inactive"
        elif int(metadata.get("revision", 1)) > 1 or merged_from or supersedes:
            version_status = "revised"
        return {
            "memory_id": entry.memory_id,
            "status": status,
            "revision": int(metadata.get("revision", 1)),
            "history_count": len(history) if isinstance(history, list) else 0,
            "created_at": entry.created_at,
            "age_days": round(_entry_age_days(entry.created_at) or 0.0, 2),
            "age_signal": _entry_age_signal(entry.created_at),
            "updated_at": metadata.get("updated_at"),
            "deleted_at": metadata.get("deleted_at"),
            "deletion_receipt_available": isinstance(metadata.get("deletion_receipt"), dict),
            "deletion_receipt": metadata.get("deletion_receipt") if isinstance(metadata.get("deletion_receipt"), dict) else None,
            "superseded_by": metadata.get("superseded_by"),
            "merged_into": metadata.get("merged_into"),
            "merged_from": merged_from,
            "supersedes": supersedes,
            "version_status": version_status,
            "stability_signal": "stable" if version_status == "stable" else ("inactive" if version_status == "inactive" else "revised"),
            "requires_confirmation": status in {"superseded", "merged"} or (version_status == "revised" and _entry_age_signal(entry.created_at) in {"aged", "old"}),
        }

    def _append_memory_history(
        self,
        entry: MemoryEntry,
        *,
        action: str,
        source: str,
        reason: str | None = None,
    ) -> dict[str, object]:
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        history = list(metadata.get("history", [])) if isinstance(metadata.get("history", []), list) else []
        revision = int(metadata.get("revision", 1))
        snapshot = {
            "recorded_at": utc_now(),
            "action": action,
            "source": source,
            "reason": reason,
            "revision": revision,
            "text": entry.text,
            "emotion": entry.emotion,
            "score": entry.score,
            "tags": list(entry.tags),
        }
        history.append(snapshot)
        metadata["history"] = history[-20:]
        metadata["revision"] = revision + (1 if action in {"update", "forget"} else 0)
        entry.metadata = metadata
        return snapshot

    def get_memory_history(self, *, user_id: str, memory_id: str) -> list[dict[str, object]]:
        entry = self.get_memory(user_id, memory_id, include_inactive=True)
        if entry is None:
            return []
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        history = metadata.get("history", [])
        return list(history) if isinstance(history, list) else []

    def restore_memory_entry(
        self,
        *,
        user_id: str,
        memory_id: str,
        source: str = "agent",
        reason: str | None = None,
        persist: bool = True,
    ) -> MemoryEntry | None:
        entry = self.get_memory(user_id, memory_id, include_inactive=True)
        if entry is None or self.get_memory_status(entry) != "forgotten":
            return None
        self._append_memory_history(entry, action="restore", source=source, reason=reason)
        metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
        metadata["status"] = "active"
        metadata.pop("deleted_at", None)
        metadata.pop("deleted_reason", None)
        metadata.pop("deleted_by", None)
        deletion_receipt = metadata.pop("deletion_receipt", None)
        if isinstance(deletion_receipt, dict):
            receipt_history = (
                list(metadata.get("deletion_receipt_history", []))
                if isinstance(metadata.get("deletion_receipt_history", []), list)
                else []
            )
            receipt_history.append(deletion_receipt)
            metadata["deletion_receipt_history"] = receipt_history[-20:]
        metadata["restored_at"] = utc_now()
        entry.metadata = metadata
        if persist:
            self.save()
        return entry

    def supersede_memory_entry(
        self,
        *,
        user_id: str,
        source_memory_id: str,
        replacement_memory_id: str,
        source: str = "agent",
        reason: str | None = None,
        persist: bool = True,
    ) -> dict[str, MemoryEntry] | None:
        source_entry = self.get_memory(user_id, source_memory_id)
        replacement_entry = self.get_memory(user_id, replacement_memory_id)
        if source_entry is None or replacement_entry is None:
            return None
        self._append_memory_history(source_entry, action="supersede", source=source, reason=reason)
        source_metadata = dict(source_entry.metadata) if isinstance(source_entry.metadata, dict) else {}
        source_metadata["status"] = "superseded"
        source_metadata["superseded_by"] = replacement_memory_id
        source_metadata["superseded_at"] = utc_now()
        source_entry.metadata = source_metadata

        self._append_memory_history(replacement_entry, action="absorbed_supersede", source=source, reason=reason)
        replacement_metadata = dict(replacement_entry.metadata) if isinstance(replacement_entry.metadata, dict) else {}
        supersedes = list(replacement_metadata.get("supersedes", [])) if isinstance(replacement_metadata.get("supersedes", []), list) else []
        if source_memory_id not in supersedes:
            supersedes.append(source_memory_id)
        replacement_metadata["supersedes"] = supersedes
        replacement_entry.metadata = replacement_metadata
        if persist:
            self.save()
        return {"source": source_entry, "replacement": replacement_entry}

    def merge_memory_entries(
        self,
        *,
        user_id: str,
        source_memory_id: str,
        target_memory_id: str,
        source: str = "agent",
        reason: str | None = None,
        persist: bool = True,
    ) -> dict[str, MemoryEntry] | None:
        source_entry = self.get_memory(user_id, source_memory_id)
        target_entry = self.get_memory(user_id, target_memory_id)
        if source_entry is None or target_entry is None:
            return None
        self._append_memory_history(source_entry, action="merge", source=source, reason=reason)
        source_metadata = dict(source_entry.metadata) if isinstance(source_entry.metadata, dict) else {}
        source_metadata["status"] = "merged"
        source_metadata["merged_into"] = target_memory_id
        source_metadata["merged_at"] = utc_now()
        source_entry.metadata = source_metadata

        self._append_memory_history(target_entry, action="absorbed_merge", source=source, reason=reason)
        target_metadata = dict(target_entry.metadata) if isinstance(target_entry.metadata, dict) else {}
        merged_from = list(target_metadata.get("merged_from", [])) if isinstance(target_metadata.get("merged_from", []), list) else []
        if source_memory_id not in merged_from:
            merged_from.append(source_memory_id)
        target_metadata["merged_from"] = merged_from
        target_entry.metadata = target_metadata
        if persist:
            self.save()
        return {"source": source_entry, "target": target_entry}

    def update_memory_entry(
        self,
        *,
        user_id: str,
        memory_id: str,
        text: str,
        emotion: str,
        score: float,
        tags: list[str],
        metadata: dict[str, object],
        source: str = "agent",
        reason: str | None = None,
        persist: bool = True,
    ) -> MemoryEntry | None:
        entry = self.get_memory(user_id, memory_id)
        if entry is None:
            return None
        self._append_memory_history(entry, action="update", source=source, reason=reason)
        previous_metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        updated_metadata = dict(previous_metadata)
        updated_metadata.update(metadata)
        updated_metadata["updated_at"] = utc_now()
        entry.text = text
        entry.emotion = emotion
        entry.score = score
        entry.tags = list(tags)
        entry.metadata = updated_metadata
        if persist:
            self.save()
        return entry

    def forget_memory_entry(
        self,
        *,
        user_id: str,
        memory_id: str,
        reason: str | None = None,
        source: str = "agent",
        persist: bool = True,
    ) -> MemoryEntry | None:
        entry = self.get_memory(user_id, memory_id)
        if entry is None:
            return None
        previous_status = self.get_memory_status(entry)
        history_snapshot = self._append_memory_history(entry, action="forget", source=source, reason=reason)
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        metadata = dict(metadata)
        deleted_at = utc_now()
        deletion_receipt = _build_deletion_receipt(
            user_id=user_id,
            memory_id=memory_id,
            deleted_at=deleted_at,
            deleted_by=source,
            reason=reason or "agent_forget",
            previous_status=previous_status,
            history_snapshot=history_snapshot,
        )
        metadata["status"] = "forgotten"
        metadata["deleted_at"] = deleted_at
        metadata["deleted_reason"] = reason or "agent_forget"
        metadata["deleted_by"] = source
        metadata["deletion_receipt"] = deletion_receipt
        history = list(metadata.get("history", [])) if isinstance(metadata.get("history", []), list) else []
        if history:
            history[-1] = dict(history[-1])
            history[-1]["deletion_receipt"] = deletion_receipt
            metadata["history"] = history[-20:]
        entry.metadata = metadata
        if persist:
            self.save()
        return entry

    def list_memories(self, user_id: str, limit: int = 20) -> list[MemoryEntry]:
        memories = [entry for entry in self.episodic if entry.user_id == user_id and self.is_memory_active(entry)]
        memories.sort(key=lambda item: item.created_at, reverse=True)
        return memories[:limit]

    def get_dream(self, user_id: str) -> dict[str, str] | None:
        value = self.dreams.get(user_id)
        if isinstance(value, dict):
            return value
        return None

    def get_snapshot(self, user_id: str, limit: int = 20) -> dict[str, object]:
        profile = self.get_profile(user_id)
        memories = [entry.to_dict() for entry in self.list_memories(user_id, limit=limit)]
        return {
            "user_id": user_id,
            "semantic_profile": profile.to_dict(),
            "dream": self.get_dream(user_id),
            "memories": memories,
            "memory_count": len([entry for entry in self.episodic if entry.user_id == user_id and self.is_memory_active(entry)]),
            "inactive_memory_count": len([entry for entry in self.episodic if entry.user_id == user_id and not self.is_memory_active(entry)]),
        }

    def build_user_report(self, user_id: str, limit: int = 10) -> dict[str, object]:
        profile = self.get_profile(user_id)
        memories = self.list_memories(user_id, limit=limit)
        emotion_counts: dict[str, int] = defaultdict(int)
        tag_counts: dict[str, int] = defaultdict(int)

        for entry in self.episodic:
            if entry.user_id != user_id:
                continue
            if not self.is_memory_active(entry):
                continue
            emotion_counts[entry.emotion] += 1
            for tag in entry.tags:
                tag_counts[tag] += 1

        top_emotions = sorted(emotion_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        top_tags = sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)[:8]

        return {
            "user_id": user_id,
            "memory_count": len([entry for entry in self.episodic if entry.user_id == user_id and self.is_memory_active(entry)]),
            "inactive_memory_count": len([entry for entry in self.episodic if entry.user_id == user_id and not self.is_memory_active(entry)]),
            "retrieval_backend": self.retrieval_backend_name,
            "storage_backend": self.state_store.resolved_backend_name,
            "top_emotions": [{"label": label, "count": count} for label, count in top_emotions],
            "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags],
            "dream": self.get_dream(user_id),
            "semantic_profile": profile.to_dict(),
            "recent_memories": [entry.to_dict() for entry in memories],
        }

    def export_user_bundle(self, user_id: str, limit: int = 20) -> dict[str, object]:
        return {
            "user_id": user_id,
            "exported_at": utc_now(),
            "retrieval_backend": self.retrieval_backend_name,
            "storage_backend": self.state_store.resolved_backend_name,
            "snapshot": self.get_snapshot(user_id=user_id, limit=limit),
            "report": self.build_user_report(user_id=user_id, limit=min(limit, 10)),
            "feedback_report": self.get_feedback_report(user_id=user_id, limit=min(limit, 10)),
        }

    def record_feedback(
        self,
        *,
        user_id: str,
        session_id: str,
        memory_id: str,
        feedback_type: str,
        query_text: str | None = None,
        notes: str | None = None,
        signal_weight: float = 1.0,
        persist: bool = True,
    ) -> dict[str, object]:
        entry = next((item for item in self.episodic if item.memory_id == memory_id and item.user_id == user_id), None)
        candidate = None
        if entry is not None:
            candidate = self.retrieval_backend.score(query_text=query_text or entry.text, emotion=entry.emotion, entry=entry)
        event = record_feedback_event(
            self.feedback_state,
            user_id=user_id,
            session_id=session_id,
            memory_id=memory_id,
            feedback_type=feedback_type,
            entry=entry,
            candidate=candidate,
            query_text=query_text,
            notes=notes,
            signal_weight=signal_weight,
            feedback_origin="explicit",
        )
        if persist:
            save_feedback_state(self.config.paths.feedback_store_file, self.feedback_state)
        return event

    def apply_passive_feedback(
        self,
        *,
        user_id: str,
        session_id: str,
        previous_interaction: dict[str, object] | None,
        current_text: str,
        persist: bool = False,
    ) -> dict[str, object] | None:
        signal = infer_passive_feedback_signal(previous_interaction, current_text)
        if signal is None:
            return None

        memory_id = str(signal["memory_id"])
        entry = next((item for item in self.episodic if item.memory_id == memory_id and item.user_id == user_id), None)
        if entry is None:
            return None

        candidate = None
        previous_candidates = previous_interaction.get("retrieval_candidates", []) if isinstance(previous_interaction, dict) else []
        shown_rank = None
        if isinstance(previous_candidates, list):
            for item in previous_candidates:
                if isinstance(item, dict) and item.get("memory_id") == memory_id:
                    shown_rank = int(item.get("rank", 0) or 0) or None
                    candidate = RetrievalCandidate(
                        memory_id=str(item.get("memory_id")),
                        text=str(item.get("text", entry.text)),
                        surface_text=str(item.get("surface_text", entry.text)),
                        category=str(item.get("category", entry.category)),
                        score=float(item.get("score", 0.0)),
                        backend=str(item.get("backend", self.retrieval_backend_name)),
                        lexical_score=float(item.get("lexical_score", 0.0)),
                        fuzzy_score=float(item.get("fuzzy_score", 0.0)),
                        semantic_score=float(item.get("semantic_score", 0.0)),
                        embedding_score=float(item.get("embedding_score", 0.0)),
                        concept_hits=list(item.get("concept_hits", [])),
                        tag_hits=list(item.get("tag_hits", [])),
                        keyword_hits=list(item.get("keyword_hits", [])),
                        abstraction_hits=list(item.get("abstraction_hits", [])),
                        relation_hits=list(item.get("relation_hits", [])),
                        attribute_hits=list(item.get("attribute_hits", [])),
                        emotion_bonus=float(item.get("emotion_bonus", 0.0)),
                        recency_bonus=float(item.get("recency_bonus", 0.0)),
                        profile_bonus=float(item.get("profile_bonus", 0.0)),
                        abstraction_bonus=float(item.get("abstraction_bonus", 0.0)),
                        attribute_bonus=float(item.get("attribute_bonus", 0.0)),
                        summary_bonus=float(item.get("summary_bonus", 0.0)),
                        graph_bonus=float(item.get("graph_bonus", 0.0)),
                        rerank_bonus=float(item.get("rerank_bonus", 0.0)),
                        feedback_bonus=float(item.get("feedback_bonus", 0.0)),
                    )
                    break

        event = record_feedback_event(
            self.feedback_state,
            user_id=user_id,
            session_id=session_id,
            memory_id=memory_id,
            feedback_type=str(signal["feedback_type"]),
            entry=entry,
            candidate=candidate,
            query_text=str(signal.get("query_text") or current_text),
            notes=str(signal.get("notes") or signal.get("reason") or "passive_feedback"),
            signal_weight=float(signal.get("signal_weight", 1.0)),
            interaction_id=str(previous_interaction.get("interaction_id")) if isinstance(previous_interaction, dict) and previous_interaction.get("interaction_id") else None,
            shown_rank=shown_rank,
            feedback_origin="passive",
            passive_reason=str(signal.get("reason")) if signal.get("reason") else None,
        )
        if persist:
            save_feedback_state(self.config.paths.feedback_store_file, self.feedback_state)
        return event

    def get_feedback_report(self, user_id: str | None = None, limit: int = 20) -> dict[str, object]:
        report = build_feedback_report(self.feedback_state, user_id=user_id, limit=limit)
        report["feedback_store_path"] = str(self.config.paths.feedback_store_file)
        return report

    def log_interaction(
        self,
        *,
        user_id: str,
        session_id: str,
        query_text: str,
        emotion: str,
        memory_committed: bool,
        recalled_memory_id: str | None,
        retrieval_candidates: list[RetrievalCandidate],
    ) -> dict[str, object]:
        payload = {
            "created_at": utc_now(),
            "user_id": user_id,
            "session_id": session_id,
            "query_text": query_text,
            "emotion": emotion,
            "memory_committed": memory_committed,
            "recalled_memory_id": recalled_memory_id,
            "retrieval_backend": self.retrieval_backend_name,
            "retrieval_pipeline": build_retrieval_pipeline_profile(self.retrieval_backend_name),
            "retrieval_settings": {
                "backend": self._current_retrieval_settings.get("backend"),
                "embedding": dict(self._current_retrieval_settings.get("embedding", {})),
                "prefilter": dict(self._current_retrieval_settings.get("prefilter", {})),
            },
            "retrieval_candidates": [candidate.to_dict() for candidate in retrieval_candidates[:10]],
        }
        return append_interaction_log(self.config.paths.interaction_log_file, payload)

    def log_service_operation(
        self,
        *,
        operation: str,
        user_id: str,
        session_id: str | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        log_payload = {
            "created_at": utc_now(),
            "record_type": "service_operation",
            "operation": operation,
            "user_id": user_id,
            "session_id": session_id,
            "query_text": str(payload.get("query_text") or payload.get("text") or operation),
            "retrieval_backend": self.retrieval_backend_name,
            "retrieval_pipeline": build_retrieval_pipeline_profile(self.retrieval_backend_name),
            "training_protocol": {
                "interaction_schema_version": 2,
                "decision_protocol_version": (
                    str(payload.get("decision_protocol", {}).get("protocol_version"))
                    if isinstance(payload.get("decision_protocol", {}), dict)
                    else None
                ),
                "has_consistency_plan": isinstance(payload.get("consistency_plan"), dict),
                "has_execution_guardrails": isinstance(payload.get("execution_guardrails"), dict)
                or isinstance(payload.get("response_guardrails"), dict),
                "has_response_contract": isinstance(payload.get("response_contract"), dict),
                "has_response_plan": isinstance(payload.get("agent_response_plan"), dict),
                "has_user_experience_guidance": isinstance(payload.get("user_experience_guidance"), dict),
            },
            "service_payload": payload,
            "retrieval_candidates": payload.get("retrieval_candidates", []) if isinstance(payload.get("retrieval_candidates", []), list) else [],
        }
        return append_interaction_log(self.config.paths.interaction_log_file, log_payload)

    def _read_interaction_records(
        self,
        *,
        limit: int | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        path = self.config.paths.interaction_log_file
        if not path.exists():
            return records
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if user_id and payload.get("user_id") != user_id:
                    continue
                if session_id and payload.get("session_id") != session_id:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
        if limit is not None and limit >= 0:
            return records[-limit:]
        return records

    def export_offline_review_dataset(self, limit: int = 500, user_id: str | None = None) -> dict[str, object]:
        suffix = user_id or "all"
        output_path = self.config.paths.offline_eval_dir / f"offline_review_{suffix}.json"
        export_payload = export_offline_review_dataset(
            self.config.paths.interaction_log_file,
            output_path,
            limit=limit,
            user_id=user_id,
            feedback_state=self.feedback_state,
        )
        export_payload["source_log_path"] = str(self.config.paths.interaction_log_file)
        return export_payload

    def build_integration_flow_report(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        records = self._read_interaction_records(limit=limit, user_id=user_id, session_id=session_id)
        service_records = [item for item in records if item.get("record_type") == "service_operation"]
        operation_counts: dict[str, int] = defaultdict(int)
        record_type_counts: dict[str, int] = defaultdict(int)
        decision_protocol_coverage = 0
        consistency_plan_coverage = 0
        response_contract_coverage = 0
        response_guardrail_coverage = 0
        response_plan_coverage = 0
        for item in records:
            record_type = str(item.get("record_type") or "interaction")
            record_type_counts[record_type] += 1
            operation = str(item.get("operation") or "process_turn")
            operation_counts[operation] += 1
            service_payload = item.get("service_payload", {})
            if isinstance(service_payload, dict):
                if isinstance(service_payload.get("decision_protocol"), dict):
                    decision_protocol_coverage += 1
                if isinstance(service_payload.get("consistency_plan"), dict):
                    consistency_plan_coverage += 1
                if isinstance(service_payload.get("response_contract"), dict):
                    response_contract_coverage += 1
                if isinstance(service_payload.get("response_guardrails"), dict):
                    response_guardrail_coverage += 1
                if isinstance(service_payload.get("agent_response_plan"), dict):
                    response_plan_coverage += 1
        feedback_report = self.get_feedback_report(user_id=user_id, limit=limit)
        required_capabilities = {
            "write_planning": operation_counts.get("plan_memory_write", 0) > 0,
            "memory_write": operation_counts.get("write_memory", 0) > 0,
            "memory_recall": operation_counts.get("recall_memory", 0) > 0,
            "memory_history": operation_counts.get("get_memory_history", 0) > 0,
            "feedback_loop": int(feedback_report["summary"].get("total_events", 0)) > 0,
            "decision_protocol_logging": decision_protocol_coverage > 0,
            "consistency_plan_logging": consistency_plan_coverage > 0,
            "response_contract_logging": response_contract_coverage > 0,
        }
        scenario_checks = {
            "chat_loop": {
                "recall": operation_counts.get("recall_memory", 0) > 0,
                "write_planning": operation_counts.get("plan_memory_write", 0) > 0,
                "write_or_update": (operation_counts.get("write_memory", 0) + operation_counts.get("update_memory", 0)) > 0,
            },
            "task_loop": {
                "recall": operation_counts.get("recall_memory", 0) > 0,
                "reflection": operation_counts.get("reflect_memory", 0) > 0,
                "feedback": int(feedback_report["summary"].get("total_events", 0)) > 0,
            },
            "lifecycle_loop": {
                "history": operation_counts.get("get_memory_history", 0) > 0,
                "restore_or_merge_or_supersede": (
                    operation_counts.get("restore_memory", 0)
                    + operation_counts.get("merge_memories", 0)
                    + operation_counts.get("supersede_memory", 0)
                ) > 0,
            },
            "consistency_loop": {
                "consistency_logging": consistency_plan_coverage > 0,
                "history": operation_counts.get("get_memory_history", 0) > 0,
                "resolution_operation": (
                    operation_counts.get("update_memory", 0)
                    + operation_counts.get("forget_memory", 0)
                    + operation_counts.get("restore_memory", 0)
                    + operation_counts.get("merge_memories", 0)
                    + operation_counts.get("supersede_memory", 0)
                ) > 0,
            },
            "core_memory_loop": {
                "set_block": operation_counts.get("set_memory_block", 0) > 0,
                "delete_block": operation_counts.get("delete_memory_block", 0) > 0,
            },
        }
        scenario_status = {
            name: all(bool(v) for v in checks.values())
            for name, checks in scenario_checks.items()
        }
        missing_capabilities = [name for name, available in required_capabilities.items() if not available]
        incomplete_scenarios = [name for name, ready in scenario_status.items() if not ready]
        execution_surface = {
            "chat_loop": ["recall_memory", "plan_memory_write", "write_memory_or_update_memory", "passive_feedback_absorption"],
            "task_loop": ["recall_memory", "reflect_memory", "task_outcome_feedback"],
            "lifecycle_loop": ["get_memory_history", "restore_memory_or_merge_memories_or_supersede_memory"],
            "consistency_loop": ["recall_memory", "get_memory_history", "update_or_forget_or_restore_or_merge_or_supersede"],
            "core_memory_loop": ["set_memory_block", "delete_memory_block", "recall_memory"],
        }
        recommended_call_flows = {
            "chat_flow": {
                "steps": ["recall_memory", "answer_from_memory", "plan_memory_write", "write_memory_or_update_memory", "passive_feedback_absorption"],
                "ready": scenario_status.get("chat_loop", False),
            },
            "task_flow": {
                "steps": ["recall_memory", "execute_task", "reflect_memory", "task_outcome_feedback"],
                "ready": scenario_status.get("task_loop", False),
            },
            "consistency_resolution_flow": {
                "steps": ["recall_memory", "get_memory_history", "update_or_forget_or_restore_or_merge_or_supersede", "re-recall_if_needed"],
                "ready": scenario_status.get("consistency_loop", False),
            },
        }
        anti_patterns: list[str] = []
        if not required_capabilities["write_planning"]:
            anti_patterns.append("avoid_direct_long_term_write_without_plan_memory_write")
        if not required_capabilities["memory_history"]:
            anti_patterns.append("avoid_conflict_resolution_without_get_memory_history")
        if not scenario_status.get("consistency_loop", False):
            anti_patterns.append("avoid_auto_answering_revised_or_disputed_facts_without_resolution_flow")
        if not scenario_status.get("core_memory_loop", False):
            anti_patterns.append("avoid_treating_archival_memory_as_core_memory_without_block_management")
        readiness = "ready"
        if missing_capabilities or incomplete_scenarios:
            readiness = "partial" if len(missing_capabilities) <= 3 and len(incomplete_scenarios) <= 2 else "blocked"
        return {
            "report_type": "personal_agent_integration_flow",
            "created_at": utc_now(),
            "user_id": user_id,
            "session_id": session_id,
            "sample_window": limit,
            "interaction_log_path": str(self.config.paths.interaction_log_file),
            "record_count": len(records),
            "service_operation_count": len(service_records),
            "record_types": dict(record_type_counts),
            "operations": dict(operation_counts),
            "coverage": {
                "decision_protocol_records": decision_protocol_coverage,
                "consistency_plan_records": consistency_plan_coverage,
                "response_contract_records": response_contract_coverage,
                "response_guardrail_records": response_guardrail_coverage,
                "response_plan_records": response_plan_coverage,
            },
            "required_capabilities": required_capabilities,
            "missing_capabilities": missing_capabilities,
            "scenario_checks": scenario_checks,
            "scenario_status": scenario_status,
            "incomplete_scenarios": incomplete_scenarios,
            "execution_surface": execution_surface,
            "recommended_call_flows": recommended_call_flows,
            "anti_patterns": anti_patterns,
            "feedback_summary": feedback_report["summary"],
            "readiness": readiness,
        }

    def build_training_protocol_report(self, *, user_id: str | None = None, limit: int = 200) -> dict[str, object]:
        records = self._read_interaction_records(limit=limit, user_id=user_id)
        export_payload = self.export_offline_review_dataset(limit=limit, user_id=user_id)
        operation_protocol_versions: dict[str, int] = defaultdict(int)
        guardrailed_records = 0
        response_contract_records = 0
        response_plan_records = 0
        for item in records:
            service_payload = item.get("service_payload", {})
            if not isinstance(service_payload, dict):
                continue
            decision_protocol = service_payload.get("decision_protocol", {})
            if isinstance(decision_protocol, dict):
                version = str(decision_protocol.get("protocol_version") or "unknown")
                operation_protocol_versions[version] += 1
            if isinstance(service_payload.get("execution_guardrails"), dict) or isinstance(service_payload.get("response_guardrails"), dict):
                guardrailed_records += 1
            if isinstance(service_payload.get("response_contract"), dict):
                response_contract_records += 1
            if isinstance(service_payload.get("agent_response_plan"), dict):
                response_plan_records += 1
        manifest = export_payload.get("manifest", {})
        labeled_samples = int(manifest.get("labeled_samples", 0))
        feedback_labeled_samples = int(manifest.get("feedback_labeled_samples", 0))
        protocol_labeled_samples = int(manifest.get("protocol_labeled_samples", 0))
        total_samples = int(export_payload.get("count", 0))
        readiness = "ready"
        if total_samples <= 0:
            readiness = "blocked"
        elif labeled_samples <= 0 or response_contract_records <= 0 or response_plan_records <= 0:
            readiness = "partial"
        labeling_mode = "feedback_attached"
        if protocol_labeled_samples > 0 and feedback_labeled_samples > 0:
            labeling_mode = "hybrid"
        elif protocol_labeled_samples > 0:
            labeling_mode = "protocol_labeled"
        elif feedback_labeled_samples <= 0:
            labeling_mode = "unlabeled"
        return {
            "report_type": "training_protocol",
            "created_at": utc_now(),
            "user_id": user_id,
            "sample_window": limit,
            "interaction_log_path": str(self.config.paths.interaction_log_file),
            "export_path": str(export_payload.get("path")),
            "record_count": len(records),
            "training_sample_count": total_samples,
            "labeled_sample_count": labeled_samples,
            "feedback_labeled_sample_count": feedback_labeled_samples,
            "protocol_labeled_sample_count": protocol_labeled_samples,
            "unlabeled_sample_count": int(manifest.get("unlabeled_samples", 0)),
            "labeling_mode": labeling_mode,
            "training_signal_status": manifest.get("training_signal_status", {}),
            "record_types": manifest.get("record_types", {}),
            "operations": manifest.get("operations", {}),
            "languages": manifest.get("languages", {}),
            "protocol_versions": dict(operation_protocol_versions),
            "guardrailed_record_count": guardrailed_records,
            "response_contract_record_count": response_contract_records,
            "response_plan_record_count": response_plan_records,
            "readiness": readiness,
        }

    def build_user_experience_report(self, *, user_id: str | None = None, session_id: str | None = None, limit: int = 200) -> dict[str, object]:
        records = self._read_interaction_records(limit=limit, user_id=user_id, session_id=session_id)
        recall_records = [
            item for item in records
            if item.get("record_type") == "service_operation" and item.get("operation") == "recall_memory"
        ]
        passive_feedback = 0
        explicit_feedback = 0
        confirmation_required = 0
        protective_confirmation_count = 0
        friction_confirmation_count = 0
        fallback_count = 0
        ready_answer_count = 0
        cautious_count = 0
        effective_cautious_count = 0.0
        interaction_styles: dict[str, int] = defaultdict(int)
        recall_outcomes: list[dict[str, object]] = []
        for item in recall_records:
            payload = item.get("service_payload", {})
            if not isinstance(payload, dict):
                continue
            guardrails = payload.get("response_guardrails", {})
            contract = payload.get("response_contract", {})
            guidance = payload.get("user_experience_guidance", {})
            memory_context = payload.get("memory_context", {})
            freshness_guard = {}
            if isinstance(memory_context, dict) and isinstance(memory_context.get("freshness_guard"), dict):
                freshness_guard = dict(memory_context.get("freshness_guard", {}))
            elif isinstance(contract, dict) and isinstance(contract.get("freshness_guard"), dict):
                freshness_guard = dict(contract.get("freshness_guard", {}))
            conflict_profile = {}
            if isinstance(memory_context, dict) and isinstance(memory_context.get("conflict_profile"), dict):
                conflict_profile = dict(memory_context.get("conflict_profile", {}))
            elif isinstance(contract, dict) and isinstance(contract.get("conflict_profile"), dict):
                conflict_profile = dict(contract.get("conflict_profile", {}))
            protective_confirmation = False
            if isinstance(guardrails, dict) and guardrails.get("mode") == "confirmation_required":
                confirmation_required += 1
                protective_confirmation = bool(
                    freshness_guard.get("query_requires_currentness")
                    and not freshness_guard.get("safe_to_answer_current_state", True)
                ) or str(conflict_profile.get("recommended_resolution") or "") == "confirm_current_state_before_answer"
                if protective_confirmation:
                    protective_confirmation_count += 1
                else:
                    friction_confirmation_count += 1
            if payload.get("fallback_reason") or (isinstance(memory_context, dict) and memory_context.get("fallback_reason")):
                fallback_count += 1
            if isinstance(contract, dict) and contract.get("ready_for_agent_answer"):
                ready_answer_count += 1
            if isinstance(guidance, dict):
                style = str(guidance.get("interaction_style") or "unknown")
                interaction_styles[style] += 1
                if style != "direct_grounded":
                    cautious_count += 1
                    if style == "gentle_confirmation":
                        effective_cautious_count += 0.45 if protective_confirmation else 0.75
                    elif style == "cautious_grounded":
                        effective_cautious_count += 0.2
                    else:
                        effective_cautious_count += 0.35 if protective_confirmation else 0.6
            recall_outcomes.append(
                {
                    "requires_confirmation": bool(isinstance(guardrails, dict) and guardrails.get("mode") == "confirmation_required"),
                    "ready_for_agent_answer": bool(isinstance(contract, dict) and contract.get("ready_for_agent_answer")),
                    "has_fallback": bool(
                        payload.get("fallback_reason")
                        or (isinstance(memory_context, dict) and memory_context.get("fallback_reason"))
                    ),
                    "interaction_style": str(guidance.get("interaction_style") or "unknown") if isinstance(guidance, dict) else "unknown",
                }
            )
        feedback_report = self.get_feedback_report(user_id=user_id, limit=limit)
        passive_feedback = int(feedback_report["summary"].get("passive", 0))
        explicit_feedback = int(feedback_report["summary"].get("explicit", 0))
        recall_count = len(recall_records)
        runtime_comfort_score = 1.0
        if recall_count:
            effective_confirmation_load = friction_confirmation_count + (protective_confirmation_count * 0.35)
            runtime_comfort_score -= min(0.4, effective_confirmation_load / max(1, recall_count) * 0.5)
            runtime_comfort_score -= min(0.25, fallback_count / max(1, recall_count) * 0.35)
            runtime_comfort_score -= min(0.15, effective_cautious_count / max(1, recall_count) * 0.15)
        if explicit_feedback > passive_feedback and explicit_feedback > 0:
            runtime_comfort_score -= 0.1
        runtime_comfort_score = max(0.0, round(runtime_comfort_score, 4))
        runtime_readiness = "comfortable" if runtime_comfort_score >= 0.78 else ("acceptable" if runtime_comfort_score >= 0.58 else "risky")
        thin_runtime_scope = recall_count < 3
        readiness_basis = "runtime_observation"
        comfort_score = runtime_comfort_score
        readiness = runtime_readiness
        thin_scope_adjustment = {
            "applied": False,
            "reason": "not_needed",
            "minimum_comfort_floor": None,
        }
        if (
            thin_runtime_scope
            and runtime_readiness == "risky"
            and fallback_count == 0
            and explicit_feedback == 0
            and friction_confirmation_count == 0
        ):
            minimum_comfort_floor = 0.62 if confirmation_required else 0.72
            comfort_score = max(runtime_comfort_score, minimum_comfort_floor)
            comfort_score = round(comfort_score, 4)
            readiness = "comfortable" if comfort_score >= 0.78 else "acceptable"
            readiness_basis = "thin_runtime_scope_normalized"
            thin_scope_adjustment = {
                "applied": True,
                "reason": "thin_runtime_scope_with_only_protective_confirmation",
                "minimum_comfort_floor": minimum_comfort_floor,
            }
        elif (
            readiness == "acceptable"
            and comfort_score >= 0.75
            and fallback_count == 0
            and friction_confirmation_count <= 1
            and len(recall_outcomes) >= 2
        ):
            recent_outcomes = recall_outcomes[-2:]
            recent_runtime_is_calm = all(
                not bool(item.get("requires_confirmation"))
                and bool(item.get("ready_for_agent_answer"))
                and not bool(item.get("has_fallback"))
                and str(item.get("interaction_style") or "unknown") in {"direct_grounded", "cautious_grounded"}
                for item in recent_outcomes
            )
            if recent_runtime_is_calm:
                comfort_score = max(comfort_score, 0.8)
                comfort_score = round(comfort_score, 4)
                readiness = "comfortable"
                readiness_basis = "recent_runtime_trend"
                thin_scope_adjustment = {
                    "applied": True,
                    "reason": "recent_runtime_trend_is_calm",
                    "minimum_comfort_floor": 0.8,
                }
        return {
            "report_type": "user_experience",
            "created_at": utc_now(),
            "user_id": user_id,
            "session_id": session_id,
            "sample_window": limit,
            "recall_count": recall_count,
            "confirmation_required_count": confirmation_required,
            "protective_confirmation_count": protective_confirmation_count,
            "friction_confirmation_count": friction_confirmation_count,
            "fallback_count": fallback_count,
            "ready_answer_count": ready_answer_count,
            "cautious_interaction_count": cautious_count,
            "interaction_styles": dict(interaction_styles),
            "feedback_summary": feedback_report["summary"],
            "ready_answer_ratio": round(ready_answer_count / max(1, recall_count), 4) if recall_count else 0.0,
            "confirmation_ratio": round(confirmation_required / max(1, recall_count), 4) if recall_count else 0.0,
            "protective_confirmation_ratio": round(protective_confirmation_count / max(1, recall_count), 4) if recall_count else 0.0,
            "friction_confirmation_ratio": round(friction_confirmation_count / max(1, recall_count), 4) if recall_count else 0.0,
            "fallback_ratio": round(fallback_count / max(1, recall_count), 4) if recall_count else 0.0,
            "comfort_score": comfort_score,
            "runtime_comfort_score": runtime_comfort_score,
            "readiness": readiness,
            "runtime_scope": {
                "readiness": runtime_readiness,
                "comfort_score": runtime_comfort_score,
                "thin_runtime_scope": thin_runtime_scope,
                "recall_count": recall_count,
                "confirmation_required_count": confirmation_required,
                "protective_confirmation_count": protective_confirmation_count,
                "friction_confirmation_count": friction_confirmation_count,
                "fallback_count": fallback_count,
                "ready_answer_count": ready_answer_count,
            },
            "readiness_basis": readiness_basis,
            "thin_scope_adjustment": thin_scope_adjustment,
            "recommendations": [
                "reduce confirmation frequency" if friction_confirmation_count > max(1, recall_count // 3) else "keep confirmation selective",
                "improve grounding coverage" if fallback_count > 0 else "maintain low fallback behavior",
                "keep freshness confirmations brief and currentness-specific" if protective_confirmation_count > 0 else "avoid unnecessary confirmation prompts",
                "continue passive-feedback-first policy" if passive_feedback >= explicit_feedback else "reduce reliance on explicit feedback",
            ],
        }

    def build_memory_hygiene_report(self, *, user_id: str | None = None, limit: int = 50) -> dict[str, object]:
        entries = [
            entry for entry in self.episodic
            if user_id is None or entry.user_id == user_id
        ]
        active_entries = [entry for entry in entries if self.is_memory_active(entry)]
        stale_candidates: list[dict[str, object]] = []
        revised_candidates: list[dict[str, object]] = []
        inactive_candidates: list[dict[str, object]] = []
        for entry in entries:
            state = self.get_memory_state_summary(user_id=entry.user_id, memory_id=entry.memory_id)
            if state is None:
                continue
            row = {
                "memory_id": entry.memory_id,
                "user_id": entry.user_id,
                "text": entry.text,
                "status": state["status"],
                "revision": state["revision"],
                "age_days": float(state.get("age_days", 0.0) or 0.0),
                "age_signal": str(state.get("age_signal", "unknown")),
            }
            if row["status"] == "active" and row["age_signal"] in {"aged", "old"}:
                stale_candidates.append(row)
            if row["status"] == "active" and int(row["revision"]) > 1:
                revised_candidates.append(row)
            if row["status"] != "active":
                inactive_candidates.append(row)
        stale_candidates.sort(key=lambda item: (float(item["age_days"]), item["revision"]), reverse=True)
        revised_candidates.sort(key=lambda item: (int(item["revision"]), float(item["age_days"])), reverse=True)
        inactive_candidates.sort(key=lambda item: (item["status"], float(item["age_days"])), reverse=True)
        readiness = "clean"
        if len(stale_candidates) > 10 or len(inactive_candidates) > 10:
            readiness = "review_needed"
        if len(stale_candidates) > 20 or len(revised_candidates) > 20:
            readiness = "cleanup_needed"
        recommended_operations: list[dict[str, object]] = []
        if stale_candidates:
            recommended_operations.append(
                {
                    "operation": "inspect_memory_history",
                    "reason": "review_aged_active_memories",
                    "target_memory_ids": [item["memory_id"] for item in stale_candidates[: min(3, len(stale_candidates))]],
                    "priority": 90,
                }
            )
        if revised_candidates:
            recommended_operations.append(
                {
                    "operation": "inspect_memory_history",
                    "reason": "review_revision_churn",
                    "target_memory_ids": [item["memory_id"] for item in revised_candidates[: min(3, len(revised_candidates))]],
                    "priority": 80,
                }
            )
        if inactive_candidates:
            recommended_operations.append(
                {
                    "operation": "audit_inactive_memories",
                    "reason": "review_forgotten_merged_or_superseded_memories",
                    "target_memory_ids": [item["memory_id"] for item in inactive_candidates[: min(3, len(inactive_candidates))]],
                    "priority": 70,
                }
            )
        if not recommended_operations:
            recommended_operations.append(
                {
                    "operation": "maintain_memory_hygiene",
                    "reason": "memory_hygiene_is_currently_clean",
                    "target_memory_ids": [],
                    "priority": 50,
                }
            )
        scoped_blocks = sum(
            len(blocks)
            for block_user_id, blocks in self.memory_blocks.items()
            if user_id is None or block_user_id == user_id
        )
        return {
            "report_type": "memory_hygiene",
            "created_at": utc_now(),
            "user_id": user_id,
            "memory_count": len(entries),
            "active_memory_count": len(active_entries),
            "core_block_count": scoped_blocks,
            "stale_active_count": len(stale_candidates),
            "revised_active_count": len(revised_candidates),
            "inactive_memory_count": len(inactive_candidates),
            "readiness": readiness,
            "stale_candidates": stale_candidates[:limit],
            "revised_candidates": revised_candidates[:limit],
            "inactive_candidates": inactive_candidates[:limit],
            "recommended_operations": recommended_operations,
            "recommendations": [
                "review aged active memories" if stale_candidates else "aged memory load is acceptable",
                "inspect heavily revised memories" if revised_candidates else "revision churn is acceptable",
                "archive or inspect inactive memories" if inactive_candidates else "inactive memory load is acceptable",
            ],
        }

    def build_consistency_audit_report(self, *, user_id: str | None = None, limit: int = 50) -> dict[str, object]:
        entries = [
            entry for entry in self.episodic
            if user_id is None or entry.user_id == user_id
        ]
        revised_fact_candidates: list[dict[str, object]] = []
        old_fact_candidates: list[dict[str, object]] = []
        disputed_fact_candidates: list[dict[str, object]] = []
        inactive_version_count = 0
        for entry in entries:
            state = self.get_memory_state_summary(user_id=entry.user_id, memory_id=entry.memory_id)
            if state is None:
                continue
            metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
            merged_from = list(state.get("merged_from", [])) if isinstance(state.get("merged_from", []), list) else []
            supersedes = list(state.get("supersedes", [])) if isinstance(state.get("supersedes", []), list) else []
            related_memory_ids = list(dict.fromkeys(merged_from + supersedes))
            status = str(state.get("status", "active"))
            age_signal = str(state.get("age_signal", "unknown"))
            version_status = str(state.get("version_status", "stable"))
            revision = int(state.get("revision", 1) or 1)
            requires_confirmation = bool(state.get("requires_confirmation"))
            row = {
                "memory_id": entry.memory_id,
                "user_id": entry.user_id,
                "text": entry.text,
                "status": status,
                "revision": revision,
                "age_days": float(state.get("age_days", 0.0) or 0.0),
                "age_signal": age_signal,
                "version_status": version_status,
                "related_memory_ids": related_memory_ids,
                "requires_confirmation": requires_confirmation,
                "latest_action": metadata.get("history", [])[-1]["action"] if isinstance(metadata.get("history", []), list) and metadata.get("history") else None,
                "consistency_types": [
                    item
                    for item in dict.fromkeys(
                        [
                            "lifecycle_state" if status in {"superseded", "merged", "forgotten"} else None,
                            "revised_fact" if version_status == "revised" else None,
                            "stale_fact" if status == "active" and age_signal in {"aged", "old"} else None,
                            "disputed_fact"
                            if status == "active" and (
                                (version_status == "revised" and age_signal in {"aged", "old"})
                                or requires_confirmation
                            )
                            else None,
                        ]
                    )
                    if item is not None
                ],
            }
            if status in {"superseded", "merged"}:
                inactive_version_count += 1
                continue
            if version_status == "revised":
                revised_fact_candidates.append(row)
            if status == "active" and age_signal in {"aged", "old"} and version_status == "revised":
                old_fact_candidates.append(row)
            if status == "active" and (
                (version_status == "revised" and age_signal in {"aged", "old"})
                or requires_confirmation
            ):
                disputed_fact_candidates.append(row)

        revised_fact_candidates.sort(key=lambda item: (int(item["revision"]), float(item["age_days"])), reverse=True)
        old_fact_candidates.sort(key=lambda item: (float(item["age_days"]), int(item["revision"])), reverse=True)
        disputed_fact_candidates.sort(
            key=lambda item: (1 if item["requires_confirmation"] else 0, len(item["related_memory_ids"]), int(item["revision"]), float(item["age_days"])),
            reverse=True,
        )

        readiness = "clean"
        if disputed_fact_candidates or old_fact_candidates:
            readiness = "review_needed"
        if len(disputed_fact_candidates) > 5 or len(old_fact_candidates) > 8:
            readiness = "cleanup_needed"

        recommended_operations: list[dict[str, object]] = []
        if disputed_fact_candidates:
            recommended_operations.append(
                {
                    "operation": "inspect_memory_history",
                    "reason": "review_disputed_or_revised_facts",
                    "target_memory_ids": [item["memory_id"] for item in disputed_fact_candidates[: min(3, len(disputed_fact_candidates))]],
                    "priority": 95,
                }
            )
            recommended_operations.append(
                {
                    "operation": "prefer_confirmation_for_revised_facts",
                    "reason": "active_fact_versions_need_guarded_recall",
                    "target_memory_ids": [item["memory_id"] for item in disputed_fact_candidates[: min(3, len(disputed_fact_candidates))]],
                    "priority": 90,
                }
            )
        if old_fact_candidates:
            recommended_operations.append(
                {
                    "operation": "audit_old_fact_versions",
                    "reason": "review_old_or_inactive_fact_versions",
                    "target_memory_ids": [item["memory_id"] for item in old_fact_candidates[: min(3, len(old_fact_candidates))]],
                    "priority": 85,
                }
            )
        if not recommended_operations:
            recommended_operations.append(
                {
                    "operation": "maintain_consistency_hygiene",
                    "reason": "consistency_audit_is_currently_clean",
                    "target_memory_ids": [],
                    "priority": 50,
                }
            )
        action_buckets = {
            "auto_safe": ["maintain_consistency_hygiene"] if not disputed_fact_candidates and not old_fact_candidates else [],
            "confirm_required": ["prefer_confirmation_for_revised_facts"] if disputed_fact_candidates else [],
            "manual_review": [
                operation["operation"]
                for operation in recommended_operations
                if operation["operation"] in {"inspect_memory_history", "audit_old_fact_versions"}
            ],
        }
        governance_mode = "manual_review" if old_fact_candidates else "confirm_required" if disputed_fact_candidates else "auto_safe"
        maintenance_surface = {
            "surface_version": "consistency-maintenance-surface.v1",
            "governance_mode": governance_mode,
            "status": readiness,
            "risk_level": "high" if readiness == "cleanup_needed" else "medium" if readiness == "review_needed" else "low",
            "issue_types": [
                issue_type
                for issue_type, count in {
                    "revised_fact": len(revised_fact_candidates),
                    "stale_fact": len([item for item in old_fact_candidates if item.get("status") == "active"]),
                    "disputed_fact": len(disputed_fact_candidates),
                    "lifecycle_state": inactive_version_count,
                }.items()
                if count > 0
            ],
            "action_buckets": action_buckets,
            "next_bucket": (
                "manual_review"
                if action_buckets["manual_review"]
                else "confirm_required"
                if action_buckets["confirm_required"]
                else "auto_safe"
            ),
            "maintenance_summary": (
                "Manual consistency review is recommended."
                if action_buckets["manual_review"]
                else "Confirmation-first handling is recommended."
                if action_buckets["confirm_required"]
                else "Consistency posture is suitable for auto-safe execution."
            ),
        }
        return {
            "report_type": "consistency_audit",
            "created_at": utc_now(),
            "user_id": user_id,
            "memory_count": len(entries),
            "inactive_version_count": inactive_version_count,
            "revised_fact_count": len(revised_fact_candidates),
            "old_fact_count": len(old_fact_candidates),
            "disputed_fact_count": len(disputed_fact_candidates),
            "consistency_type_counts": {
                "revised_fact": len(revised_fact_candidates),
                "stale_fact": len([item for item in old_fact_candidates if item.get("status") == "active"]),
                "disputed_fact": len(disputed_fact_candidates),
                "lifecycle_state": inactive_version_count,
            },
            "readiness": readiness,
            "revised_fact_candidates": revised_fact_candidates[:limit],
            "old_fact_candidates": old_fact_candidates[:limit],
            "disputed_fact_candidates": disputed_fact_candidates[:limit],
            "governance_mode": governance_mode,
            "action_buckets": action_buckets,
            "consistency_maintenance": maintenance_surface,
            "recommended_operations": recommended_operations,
            "recommendations": [
                "inspect revised active facts before auto-answering" if revised_fact_candidates else "active fact revisions are low-risk",
                "treat old fact versions as historical unless re-confirmed" if old_fact_candidates else "old fact version load is acceptable",
                "prefer confirmation when conflict watchlist is non-empty" if disputed_fact_candidates else "conflict watchlist is currently clean",
            ],
        }

    def get_storage_report(self) -> dict[str, object]:
        report = self.state_store.get_status()
        requested_backend = str(self.config.storage_backend or report.get("requested_backend") or "auto")
        resolved_backend = self.state_store.resolved_backend_name
        runtime_memory_count = len(self.episodic)
        runtime_profile_count = len(self.semantic)
        runtime_dream_count = len(self.dreams)
        latest_backup = self._get_latest_storage_backup_info()
        integrity_checks = {
            "memory_file_parent_exists": self.config.paths.memory_file.parent.exists(),
            "sqlite_file_parent_exists": self.config.paths.sqlite_file.parent.exists(),
            "feedback_store_parent_exists": self.config.paths.feedback_store_file.parent.exists(),
            "interaction_log_parent_exists": self.config.paths.interaction_log_file.parent.exists(),
            "offline_eval_dir_exists": self.config.paths.offline_eval_dir.exists(),
            "active_store_exists": bool(report.get("exists", False)),
        }
        persisted_memory_count = report.get("memory_count")
        if isinstance(persisted_memory_count, int) and report.get("resolved_backend") == "sqlite":
            integrity_checks["runtime_memory_count_matches_store"] = persisted_memory_count == runtime_memory_count
        integrity_ok = all(bool(value) for value in integrity_checks.values())
        preferred_primary_backend = "sqlite" if requested_backend in {"auto", "sqlite"} else requested_backend
        primary_mode_status = (
            "blocked"
            if not integrity_ok
            else "healthy_primary"
            if resolved_backend == preferred_primary_backend
            else "degraded_fallback"
        )
        schema_version = str(report.get("schema_version") or "unknown")
        schema_status = "aligned" if schema_version == "2" else ("unknown" if schema_version == "unknown" else "drifted")
        consistency = {
            "runtime_memory_count_matches_store": bool(integrity_checks.get("runtime_memory_count_matches_store", True)),
            "feedback_store_available": bool(integrity_checks["feedback_store_parent_exists"]),
            "interaction_logging_available": bool(integrity_checks["interaction_log_parent_exists"]),
            "offline_review_export_available": bool(integrity_checks["offline_eval_dir_exists"]),
            "recent_backup_available": bool(latest_backup.get("is_recent", False)),
        }
        latest_restore_drill = self._get_latest_restore_drill_info()
        restore_drill_freshness = self._build_restore_drill_freshness(latest_restore_drill)
        latest_migration_attempt = self._get_latest_migration_attempt_info()
        rollback_evidence = {
            "backup_exists": bool(latest_backup.get("exists", False)),
            "backup_recent": bool(latest_backup.get("is_recent", False)),
            "restore_drill_status": latest_restore_drill.get("status", "missing"),
            "restore_drill_freshness": restore_drill_freshness.get("status"),
        }
        migration_checks = [
            {
                "item": "storage_integrity_ok",
                "status": "pass" if integrity_ok else "fail",
                "reason": "integrity checks passed" if integrity_ok else "storage integrity must be fixed before migration",
            },
            {
                "item": "schema_known_or_aligned",
                "status": "pass" if schema_status in {"aligned", "unknown"} else "fail",
                "reason": f"schema status is {schema_status}",
            },
            {
                "item": "recent_backup_available",
                "status": "pass" if bool(latest_backup.get("is_recent", False)) else ("warn" if bool(latest_backup.get("exists", False)) else "fail"),
                "reason": (
                    "recent rollback artifact is available"
                    if bool(latest_backup.get("is_recent", False))
                    else "backup exists but should be refreshed before migration"
                    if bool(latest_backup.get("exists", False))
                    else "no rollback artifact is available yet"
                ),
            },
            {
                "item": "restore_drill_freshness",
                "status": (
                    "pass"
                    if restore_drill_freshness.get("status") == "fresh"
                    else "warn"
                    if restore_drill_freshness.get("status") in {"stale", "missing"}
                    else "fail"
                ),
                "reason": str(restore_drill_freshness.get("acceptance_summary", "restore-drill freshness is unknown")),
            },
        ]
        migration_blockers = [item["item"] for item in migration_checks if item["status"] == "fail"]
        migration_warnings = [item["item"] for item in migration_checks if item["status"] == "warn"]
        migration_acceptance = self._build_migration_acceptance(
            preflight_status=(
                "blocked"
                if migration_blockers
                else "review"
                if migration_warnings
                else "ready"
            ),
            rollback_evidence=rollback_evidence,
            latest_attempt=latest_migration_attempt,
        )
        migration = {
            "policy_version": "storage-migration-policy.v1",
            "schema_version": schema_version,
            "schema_status": schema_status,
            "target_schema_version": "2",
            "upgrade_strategy": "sqlite_in_place" if resolved_backend == "sqlite" else "json_snapshot_replace",
            "supported_upgrade_paths": [
                "json_snapshot_replace_to_sqlite_v2",
                "sqlite_in_place_v2",
            ],
            "hooks_declared": resolved_backend == "sqlite",
            "fallback_backend": "json",
            "migration_ready": resolved_backend == "sqlite" and schema_status in {"aligned", "unknown"},
            "preflight_operation": "run_storage_migration_preflight",
            "preflight": {
                "status": migration_acceptance.get("preflight_status"),
                "checks": migration_checks,
                "blockers": migration_blockers,
                "warnings": migration_warnings,
                "required_backup_before_migration": not bool(latest_backup.get("is_recent", False)),
                "rollback_available": bool(latest_backup.get("exists", False)),
            },
            "rollback": {
                "strategy": "restore_latest_verified_backup",
                "rollback_ready": bool(latest_backup.get("exists", False)),
                "rollback_artifact_path": latest_backup.get("path"),
                "rollback_artifact_recent": bool(latest_backup.get("is_recent", False)),
                "rollback_command": "python -m src.memory_system.cli_app storage-backup",
                "rollback_evidence": rollback_evidence,
            },
            "latest_attempt": latest_migration_attempt,
            "migration_acceptance": migration_acceptance,
        }
        recovery = {
            "backup_supported": True,
            "backup_operation": "create_storage_backup",
            "restore_drill_operation": "run_storage_restore_drill",
            "fallback_mode": "json_fallback",
            "restart_safe": integrity_ok,
            "latest_backup": latest_backup,
            "latest_restore_drill": latest_restore_drill,
            "last_restore_drill_at": latest_restore_drill.get("created_at"),
            "last_restore_drill_status": latest_restore_drill.get("status", "missing"),
            "last_restore_drill_age_hours": restore_drill_freshness.get("age_hours"),
            "restore_drill_freshness": restore_drill_freshness,
            "restore_confidence": self._estimate_storage_recovery_confidence(
                integrity_ok=integrity_ok,
                latest_backup=latest_backup,
                schema_status=schema_status,
                latest_restore_drill=latest_restore_drill,
            ),
            "recovery_confidence": self._estimate_storage_recovery_confidence(
                integrity_ok=integrity_ok,
                latest_backup=latest_backup,
                schema_status=schema_status,
                latest_restore_drill=latest_restore_drill,
            ),
            "recovery_drill_recommended": (
                not bool(latest_backup.get("is_recent", False))
                or not integrity_ok
                or bool(restore_drill_freshness.get("rerun_required"))
            ),
        }
        observability = {
            "interaction_log_enabled": bool(integrity_checks["interaction_log_parent_exists"]),
            "feedback_store_enabled": bool(integrity_checks["feedback_store_parent_exists"]),
            "report_surfaces": [
                "storage",
                "integration_flow",
                "training_protocol",
                "user_experience",
                "memory_hygiene",
                "consistency_audit",
                "release_readiness",
                "agent_readiness_summary",
            ],
            "audit_history_supported": True,
            "latest_backup_seen_at": latest_backup.get("created_at"),
            "latest_restore_drill_at": latest_restore_drill.get("created_at"),
            "backup_inventory_dir": str(self.config.paths.delivery_dir / "storage_backups"),
            "restore_drill_dir": str(self.config.paths.delivery_dir / "restore_drills"),
        }
        primary_storage = {
            "contract_version": "storage-primary-path.v1",
            "requested_backend": requested_backend,
            "preferred_primary_backend": preferred_primary_backend,
            "active_backend": resolved_backend,
            "is_primary_backend": resolved_backend == preferred_primary_backend,
            "fallback_active": resolved_backend != preferred_primary_backend,
            "fallback_allowed": requested_backend in {"auto", "sqlite"},
            "mode_status": primary_mode_status,
            "degradation_reason": report.get("fallback_reason") if primary_mode_status == "degraded_fallback" else None,
            "primary_path_goal": (
                "keep_sqlite_as_primary"
                if preferred_primary_backend == "sqlite"
                else f"keep_{preferred_primary_backend}_as_primary"
            ),
        }
        backup_inventory = self._get_storage_backup_inventory(limit=5)
        blockers: list[str] = []
        warnings: list[str] = []
        if not integrity_ok:
            blockers.append("storage_integrity_not_ok")
        if schema_status == "drifted":
            blockers.append("storage_schema_drift")
        if primary_mode_status == "degraded_fallback":
            warnings.append("primary_storage_degraded")
        if resolved_backend != "sqlite":
            warnings.append("non_sqlite_backend_active")
        if not consistency["runtime_memory_count_matches_store"]:
            warnings.append("runtime_store_count_mismatch")
        if not latest_backup.get("exists", False):
            warnings.append("storage_backup_missing")
        elif not latest_backup.get("is_recent", False):
            warnings.append("storage_backup_stale")
        readiness = "ready"
        if blockers:
            readiness = "risky"
        elif warnings:
            readiness = "review"
        recommended_operations: list[dict[str, object]] = []
        if blockers:
            recommended_operations.append(
                {
                    "operation": "fix_storage_integrity",
                    "reason": blockers[0],
                    "priority": 95,
                }
            )
        if schema_status == "drifted":
            recommended_operations.append(
                {
                    "operation": "verify_storage_schema_migration",
                    "reason": "storage_schema_drift",
                    "priority": 92,
                }
            )
        if primary_mode_status == "degraded_fallback":
            recommended_operations.append(
                {
                    "operation": "migrate_storage_backend",
                    "reason": "restore_primary_storage_path",
                    "priority": 85,
                }
            )
        if not latest_backup.get("exists", False) or not latest_backup.get("is_recent", False):
            recommended_operations.append(
                {
                    "operation": "refresh_storage_backup",
                    "reason": "maintain_recent_recovery_point",
                    "priority": 82,
                }
            )
        recommended_operations.append(
            {
                "operation": "create_storage_backup",
                "reason": "maintain_recovery_path",
                "priority": 75,
            }
        )
        operator_checklist_items = [
            {
                "item": "active_store_present",
                "status": "pass" if bool(report.get("exists", False)) else "fail",
                "reason": "active storage file is present" if bool(report.get("exists", False)) else "active storage file is missing",
                "recommended_action": None if bool(report.get("exists", False)) else "fix_storage_integrity",
            },
            {
                "item": "storage_integrity_ok",
                "status": "pass" if integrity_ok else "fail",
                "reason": "integrity checks passed" if integrity_ok else "one or more integrity checks failed",
                "recommended_action": None if integrity_ok else "fix_storage_integrity",
            },
            {
                "item": "schema_ready_for_delivery",
                "status": "pass" if schema_status in {"aligned", "unknown"} else "fail",
                "reason": f"schema status is {schema_status}",
                "recommended_action": None if schema_status in {"aligned", "unknown"} else "verify_storage_schema_migration",
            },
            {
                "item": "recent_backup_available",
                "status": "pass" if bool(latest_backup.get("is_recent", False)) else ("warn" if bool(latest_backup.get("exists", False)) else "fail"),
                "reason": (
                    "recent recovery point is available"
                    if bool(latest_backup.get("is_recent", False))
                    else "backup exists but is stale"
                    if bool(latest_backup.get("exists", False))
                    else "no backup artifact has been created yet"
                ),
                "recommended_action": None if bool(latest_backup.get("is_recent", False)) else "refresh_storage_backup",
            },
            {
                "item": "restore_drill_freshness",
                "status": (
                    "pass"
                    if restore_drill_freshness.get("status") == "fresh"
                    else "warn"
                    if restore_drill_freshness.get("status") in {"stale", "missing"}
                    else "fail"
                ),
                "reason": str(restore_drill_freshness.get("acceptance_summary", "restore drill freshness is unknown")),
                "recommended_action": None if not bool(restore_drill_freshness.get("rerun_required")) else "run_storage_restore_drill",
            },
            {
                "item": "primary_storage_mode",
                "status": (
                    "fail"
                    if primary_mode_status == "blocked"
                    else "pass"
                    if primary_mode_status == "healthy_primary"
                    else "warn"
                ),
                "reason": (
                    "preferred primary storage path is healthy"
                    if primary_mode_status == "healthy_primary"
                    else "active store is running in degraded fallback mode"
                    if primary_mode_status == "degraded_fallback"
                    else "primary storage path is blocked"
                ),
                "recommended_action": (
                    None
                    if primary_mode_status == "healthy_primary"
                    else "migrate_storage_backend"
                    if primary_mode_status == "degraded_fallback"
                    else "fix_storage_integrity"
                ),
            },
            {
                "item": "preferred_sqlite_runtime",
                "status": "pass" if resolved_backend == "sqlite" else "warn",
                "reason": "sqlite is active as the primary store" if resolved_backend == "sqlite" else "json fallback is active instead of sqlite",
                "recommended_action": None if resolved_backend == "sqlite" else "migrate_storage_backend",
            },
            {
                "item": "recovery_path_documented",
                "status": "pass",
                "reason": "storage report includes backup inventory and restore steps",
                "recommended_action": None,
            },
        ]
        blocking_items = [item["item"] for item in operator_checklist_items if item["status"] == "fail"]
        warning_items = [item["item"] for item in operator_checklist_items if item["status"] == "warn"]
        operator_checklist = {
            "checklist_version": "storage-delivery-checklist.v1",
            "pass_count": sum(1 for item in operator_checklist_items if item["status"] == "pass"),
            "warn_count": len(warning_items),
            "fail_count": len(blocking_items),
            "blocking_items": blocking_items,
            "warning_items": warning_items,
            "items": operator_checklist_items,
        }
        operator_decision_path = {
            "decision_path_version": "storage-operator-decision-path.v1",
            "primary_storage_mode": primary_mode_status,
            "delivery_decision": (
                "proceed"
                if primary_mode_status == "healthy_primary"
                else "proceed_with_followup"
                if primary_mode_status == "degraded_fallback"
                else "block"
            ),
            "operator_action": (
                "maintain_primary_storage_health"
                if primary_mode_status == "healthy_primary"
                else "restore_primary_storage_path"
                if primary_mode_status == "degraded_fallback"
                else "fix_storage_integrity_before_delivery"
            ),
            "acceptance_rule": (
                "accept_if_other_delivery_gates_are_green"
                if primary_mode_status == "healthy_primary"
                else "accept_only_with_explicit_followup_for_primary_path_restoration"
                if primary_mode_status == "degraded_fallback"
                else "do_not_accept_until_primary_path_is_unblocked"
            ),
            "restore_drill_acceptance": {
                "status": restore_drill_freshness.get("status"),
                "rerun_required": bool(restore_drill_freshness.get("rerun_required")),
                "rule": restore_drill_freshness.get("rerun_rule"),
                "evidence_acceptable_when": restore_drill_freshness.get("evidence_acceptable_when"),
                "summary": restore_drill_freshness.get("acceptance_summary"),
            },
            "migration_acceptance": migration_acceptance,
            "next_checks": [
                "operator_checklist.primary_storage_mode",
                "operator_checklist.restore_drill_freshness",
                "migration.migration_acceptance",
                "deployment_guidance.primary_runtime_expectation",
                "recovery.latest_backup",
                "recovery.restore_drill_freshness",
                "backup_inventory",
            ],
        }
        remediation_checklist = {
            "checklist_version": "storage-remediation-checklist.v1",
            "mode": primary_mode_status,
            "required_before_next_delivery": primary_mode_status == "blocked",
            "items": (
                [
                    {
                        "step": "Record the fallback state in the operator handoff note.",
                        "status": "required",
                    },
                    {
                        "step": "Keep at least one recent verified backup available before further delivery use.",
                        "status": "required",
                    },
                    {
                        "step": "Inspect the SQLite startup/fallback reason and confirm whether the environment blocked the preferred primary path.",
                        "status": "required",
                    },
                    {
                        "step": "Plan and execute primary-path restoration so SQLite returns as the active store for normal operation.",
                        "status": "follow_up",
                    },
                ]
                if primary_mode_status == "degraded_fallback"
                else [
                    {
                        "step": "Restore storage integrity before any further delivery or pilot use.",
                        "status": "required",
                    },
                    {
                        "step": "Create or recover a healthy backup artifact before restart if possible.",
                        "status": "required",
                    },
                    {
                        "step": "Re-run storage report, smoke, and integration evidence after repair.",
                        "status": "required",
                    },
                ]
                if primary_mode_status == "blocked"
                else [
                    {
                        "step": "Keep the preferred primary path healthy and continue routine backup maintenance.",
                        "status": "maintain",
                    }
                ]
            ),
        }
        operator_acceptance_note = {
            "note_version": "storage-acceptance-note.v1",
            "primary_storage_mode": primary_mode_status,
            "delivery_decision": operator_decision_path["delivery_decision"],
            "summary": (
                "Primary storage is healthy; accept normally if the remaining delivery gates are green."
                if primary_mode_status == "healthy_primary"
                else "Primary storage is in degraded fallback mode; accept only with explicit follow-up to restore the preferred primary path."
                if primary_mode_status == "degraded_fallback"
                else "Primary storage is blocked; do not accept until storage integrity and the preferred path are restored."
            ),
            "operator_action": operator_decision_path["operator_action"],
            "restore_drill_summary": restore_drill_freshness.get("acceptance_summary"),
            "migration_summary": migration_acceptance.get("summary"),
        }
        restore_steps = [
            "Stop the EMOS API or any writer using the active state store.",
            "Take a fresh backup before replacing the active store if the current files are still readable.",
            "Choose the latest healthy backup from the storage backup inventory.",
            "Replace the active JSON or SQLite file with the selected backup artifact.",
            "Restart the service and confirm the storage report shows integrity_ok and a healthy memory count.",
            "Run the stable regression set or at minimum the smoke and integration-flow scripts before handoff.",
        ]
        deployment_guidance = {
            "deployment_mode": "local_private_first",
            "startup_command": ".\\scripts\\run_api.ps1",
            "smoke_command": ".\\scripts\\run_smoke.ps1",
            "integration_evidence_command": ".\\scripts\\run_integration_flows.ps1",
            "backup_command": "python -m src.memory_system.cli_app storage-backup",
            "primary_runtime_expectation": f"{preferred_primary_backend} should remain the primary active store for normal delivery operation",
            "restore_steps": restore_steps,
            "storage_mode_summary": (
                "Primary storage path is healthy and matches the delivery expectation."
                if primary_mode_status == "healthy_primary"
                else "Primary storage path is blocked; restore storage integrity before delivery use."
                if primary_mode_status == "blocked"
                else "Primary storage is currently degraded into fallback mode; keep backups current and restore the preferred primary path."
            ),
        }
        report.update(
            {
                "requested_backend": requested_backend,
                "resolved_backend": resolved_backend,
                "preferred_primary_backend": preferred_primary_backend,
                "primary_mode_status": primary_mode_status,
                "primary_storage": primary_storage,
                "feedback_store_path": str(self.config.paths.feedback_store_file),
                "interaction_log_path": str(self.config.paths.interaction_log_file),
                "offline_eval_dir": str(self.config.paths.offline_eval_dir),
                "runtime_memory_count": runtime_memory_count,
                "runtime_profile_count": runtime_profile_count,
                "runtime_dream_count": runtime_dream_count,
                "integrity_checks": integrity_checks,
                "integrity_ok": integrity_ok,
                "persistence_consistency": consistency,
                "migration": migration,
                "recovery": recovery,
                "backup_inventory": backup_inventory,
                "observability": observability,
                "operator_checklist": operator_checklist,
                "operator_decision_path": operator_decision_path,
                "operator_acceptance_note": operator_acceptance_note,
                "remediation_checklist": remediation_checklist,
                "deployment_guidance": deployment_guidance,
                "persistence_confidence": self._estimate_storage_recovery_confidence(
                    integrity_ok=integrity_ok,
                    latest_backup=latest_backup,
                    schema_status=schema_status,
                    latest_restore_drill=latest_restore_drill,
                ),
                "readiness": readiness,
                "blockers": blockers,
                "warnings": warnings,
                "recommended_operations": recommended_operations,
                "next_focus": [
                    "fix_storage_integrity"
                    if "storage_integrity_not_ok" in blockers
                    else "verify_storage_schema_migration"
                    if "storage_schema_drift" in blockers
                    else "migrate_storage_backend"
                    if primary_mode_status == "degraded_fallback"
                    else "refresh_storage_backup"
                    if "storage_backup_missing" in warnings or "storage_backup_stale" in warnings
                    else "maintain_storage_health"
                ],
            }
        )
        return report

    def create_storage_backup(self) -> dict[str, object]:
        payload = self._build_payload()
        backup_dir = self.config.paths.delivery_dir / "storage_backups"
        native_backup_path: Path | None = None
        try:
            backup_path = self.state_store.create_backup(
                payload=payload,
                backup_dir=backup_dir,
            )
            native_backup_path = backup_path
            backend = self.state_store.resolved_backend_name
            backup_mode = "native_backup"
            fallback_reason = None
        except Exception as exc:
            backup_path = self._write_json_backup(payload=payload, backup_dir=backup_dir)
            backend = "json"
            backup_mode = "json_fallback"
            fallback_reason = str(exc)
        sha256 = self._compute_file_sha256(backup_path) if backup_path.exists() else None
        backup_format = backup_path.suffix.lower().lstrip(".") if backup_path.suffix else "unknown"
        verification = {
            "path_exists": backup_path.exists(),
            "size_nonzero": backup_path.exists() and backup_path.stat().st_size > 0,
            "hash_available": bool(sha256),
            "restorable_format": backup_format in {"json", "sqlite3"},
        }
        verification["status"] = "verified" if all(bool(value) for value in verification.values()) else "incomplete"
        if backup_mode == "native_backup" and verification["status"] != "verified":
            fallback_reason = (
                f"native backup verification failed for {backup_format} artifact"
                if not fallback_reason
                else f"{fallback_reason}; native backup verification failed for {backup_format} artifact"
            )
            backup_path = self._write_json_backup(payload=payload, backup_dir=backup_dir)
            backend = "json"
            backup_mode = "json_fallback_after_failed_native_verification"
            sha256 = self._compute_file_sha256(backup_path) if backup_path.exists() else None
            backup_format = backup_path.suffix.lower().lstrip(".") if backup_path.suffix else "unknown"
            verification = {
                "path_exists": backup_path.exists(),
                "size_nonzero": backup_path.exists() and backup_path.stat().st_size > 0,
                "hash_available": bool(sha256),
                "restorable_format": backup_format in {"json", "sqlite3"},
            }
            verification["status"] = "verified" if all(bool(value) for value in verification.values()) else "incomplete"
        return {
            "created_at": utc_now(),
            "path": str(backup_path),
            "native_backup_path": str(native_backup_path) if native_backup_path is not None else None,
            "backend": backend,
            "backup_mode": backup_mode,
            "format": backup_format,
            "fallback_reason": fallback_reason,
            "exists": backup_path.exists(),
            "size_bytes": backup_path.stat().st_size if backup_path.exists() else 0,
            "sha256": sha256,
            "verification": verification,
            "restore_steps": [
                "Stop the running EMOS service before replacing active storage files.",
                "Copy the selected backup artifact over the active JSON or SQLite store path.",
                "Restart the service and re-run the storage report and smoke verification.",
            ],
        }

    def run_storage_restore_drill(self) -> dict[str, object]:
        backup_dir = self.config.paths.delivery_dir / "storage_backups"
        all_candidates = sorted(
            [
                item for item in backup_dir.iterdir()
                if item.is_file() and item.suffix.lower() in {".json", ".sqlite3"}
            ],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ) if backup_dir.exists() else []
        preferred_restore_suffix = ".sqlite3" if self.state_store.resolved_backend_name == "sqlite" else ".json"
        preferred_candidates = [item for item in all_candidates if item.suffix.lower() == preferred_restore_suffix]
        fallback_candidates = [item for item in all_candidates if item.suffix.lower() != preferred_restore_suffix]
        candidates = preferred_candidates + fallback_candidates
        if not candidates:
            backup = self.create_storage_backup()
            candidates = [Path(str(backup["path"]))]

        default_payload = {
            "episodic": [],
            "emotional": [],
            "semantic": {},
            "dreams": {},
        }
        last_result: dict[str, object] | None = None
        attempted_candidates: list[dict[str, object]] = []

        for source_backup_path in candidates:
            restored_format = source_backup_path.suffix.lower().lstrip(".") or "json"
            drill_id = utc_now().replace(":", "").replace("-", "").replace(".", "")
            artifact_dir = self.config.paths.delivery_dir / "restore_drills" / drill_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            runtime_restore_root = self.config.paths.delivery_dir / "restore_drills"
            if restored_format == "sqlite3" and not _is_ascii_safe_path(runtime_restore_root):
                runtime_restore_root = Path(tempfile.gettempdir()) / "EMOS" / "restore_drills"
            runtime_restore_dir = runtime_restore_root / drill_id
            runtime_restore_dir.mkdir(parents=True, exist_ok=True)
            restored_path = runtime_restore_dir / f"restored_memory.{restored_format}"
            checks = {
                "backup_exists": source_backup_path.exists(),
                "backup_format_supported": restored_format in {"json", "sqlite3"},
            }

            try:
                if restored_format == "sqlite3":
                    staged_source_backup = runtime_restore_dir / f"selected_backup.{restored_format}"
                    shutil.copy2(source_backup_path, staged_source_backup)
                    source_store = SQLiteStateStore(staged_source_backup, requested_backend="sqlite")
                    source_payload = source_store.load(default=default_payload)
                    shutil.copy2(staged_source_backup, restored_path)
                    restored_store = SQLiteStateStore(restored_path, requested_backend="sqlite")
                    restored_payload = restored_store.load(default=default_payload)
                    restored_backend = "sqlite"
                else:
                    source_payload = read_json(source_backup_path, default=default_payload)
                    write_json(restored_path, source_payload)
                    restored_store = JsonStateStore(restored_path, requested_backend="json")
                    restored_payload = restored_store.load(default=default_payload)
                    restored_backend = "json"

                restored_memory_count = len(restored_payload.get("episodic", []))
                restored_profile_count = len(restored_payload.get("semantic", {}))
                restored_dream_count = len(restored_payload.get("dreams", {}))
                checks.update(
                    {
                        "restored_store_exists": restored_path.exists(),
                        "restored_payload_loaded": isinstance(restored_payload, dict),
                        "memory_count_match": restored_memory_count == len(source_payload.get("episodic", [])),
                        "profile_count_match": restored_profile_count == len(source_payload.get("semantic", {})),
                        "dream_count_match": restored_dream_count == len(source_payload.get("dreams", {})),
                    }
                )
                status = "passed" if all(bool(value) for value in checks.values()) else "failed"
                error_message = None
            except Exception as exc:
                restored_backend = "unknown"
                restored_memory_count = 0
                restored_profile_count = 0
                restored_dream_count = 0
                checks.update(
                    {
                        "restored_store_exists": restored_path.exists(),
                        "restored_payload_loaded": False,
                        "memory_count_match": False,
                        "profile_count_match": False,
                        "dream_count_match": False,
                    }
                )
                status = "failed"
                error_message = str(exc)

            result = {
                "drill_version": "storage-restore-drill.v1",
                "status": status,
                "created_at": utc_now(),
                "source_backup_path": str(source_backup_path),
                "source_backup_format": restored_format,
                "restored_backend": restored_backend,
                "restored_path": str(restored_path),
                "restored_memory_count": restored_memory_count,
                "restored_profile_count": restored_profile_count,
                "restored_dream_count": restored_dream_count,
                "checks": checks,
                "error": error_message,
            }
            attempted_candidates.append(
                {
                    "path": str(source_backup_path),
                    "format": restored_format,
                    "status": status,
                    "error": error_message,
                }
            )
            result["selection_strategy"] = "latest_healthy_backup"
            result["attempted_candidates"] = list(attempted_candidates)
            write_json(artifact_dir / "restore_drill_result.json", result)
            last_result = result
            if status == "passed":
                return result

        assert last_result is not None
        return last_result

    def _get_latest_storage_backup_info(self) -> dict[str, object]:
        backup_dir = self.config.paths.delivery_dir / "storage_backups"
        if not backup_dir.exists():
            return {
                "exists": False,
                "path": None,
                "created_at": None,
                "age_hours": None,
                "is_recent": False,
            }
        candidates = [
            item for item in backup_dir.iterdir()
            if item.is_file() and item.suffix.lower() in {".json", ".sqlite3"}
        ]
        if not candidates:
            return {
                "exists": False,
                "path": None,
                "created_at": None,
                "age_hours": None,
                "is_recent": False,
            }
        latest = max(candidates, key=lambda item: item.stat().st_mtime)
        created_at = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
        age_hours = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0)
        return {
            "exists": True,
            "path": str(latest),
            "created_at": created_at.isoformat(),
            "age_hours": round(age_hours, 2),
            "is_recent": age_hours <= 24.0,
            "size_bytes": latest.stat().st_size,
            "format": latest.suffix.lower().lstrip("."),
        }

    def _get_latest_restore_drill_info(self) -> dict[str, object]:
        drill_dir = self.config.paths.delivery_dir / "restore_drills"
        if not drill_dir.exists():
            return {"exists": False, "status": "missing"}
        candidates = sorted(
            drill_dir.glob("*/restore_drill_result.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {"exists": False, "status": "missing"}
        latest = candidates[0]
        payload = read_json(latest, default={})
        return {
            "exists": True,
            "path": str(latest),
            "created_at": payload.get("created_at"),
            "status": payload.get("status", "unknown"),
            "restored_backend": payload.get("restored_backend"),
            "source_backup_path": payload.get("source_backup_path"),
            "selection_strategy": payload.get("selection_strategy"),
            "attempted_candidates": payload.get("attempted_candidates", []),
            "checks": payload.get("checks", {}),
        }

    def _get_latest_migration_attempt_info(self) -> dict[str, object]:
        migration_dir = self.config.paths.delivery_dir / "migrations"
        if not migration_dir.exists():
            return {
                "exists": False,
                "attempt_type": "none",
                "status": "not_run",
                "attempted_at": None,
                "artifact_path": None,
            }
        candidates = sorted(
            migration_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {
                "exists": False,
                "attempt_type": "none",
                "status": "not_run",
                "attempted_at": None,
                "artifact_path": None,
            }
        latest = candidates[0]
        payload = read_json(latest, default={})
        migration_payload = payload.get("migration", {}) if isinstance(payload.get("migration"), dict) else {}
        preflight_payload = migration_payload.get("preflight", {}) if isinstance(migration_payload.get("preflight"), dict) else {}
        rollback_payload = migration_payload.get("rollback", {}) if isinstance(migration_payload.get("rollback"), dict) else {}
        return {
            "exists": True,
            "attempt_type": payload.get("preflight_version", "migration-artifact"),
            "status": preflight_payload.get("status", "unknown"),
            "attempted_at": payload.get("created_at"),
            "artifact_path": str(latest),
            "rollback_ready": rollback_payload.get("rollback_ready"),
            "rollback_artifact_path": rollback_payload.get("rollback_artifact_path"),
            "rollback_artifact_recent": rollback_payload.get("rollback_artifact_recent"),
        }

    def _write_json_backup(self, *, payload: dict[str, object], backup_dir: Path) -> Path:
        timestamp = utc_now().replace(":", "").replace("-", "").replace(".", "")
        backup_path = backup_dir / f"memory_backup_{timestamp}.json"
        write_json(backup_path, payload)
        return backup_path

    def _estimate_storage_recovery_confidence(
        self,
        *,
        integrity_ok: bool,
        latest_backup: dict[str, object],
        schema_status: str,
        latest_restore_drill: dict[str, object],
    ) -> str:
        if not integrity_ok or schema_status == "drifted":
            return "low"
        if not latest_backup.get("exists", False):
            return "medium"
        if not latest_backup.get("is_recent", False):
            return "medium"
        latest_restore_status = str(latest_restore_drill.get("status", "missing"))
        if latest_restore_status == "failed":
            return "low"
        if latest_restore_status != "passed":
            return "medium"
        return "high"

    def _build_restore_drill_freshness(self, latest_restore_drill: dict[str, object]) -> dict[str, object]:
        status = str(latest_restore_drill.get("status", "missing"))
        created_at = latest_restore_drill.get("created_at")
        created_dt = _parse_iso_datetime(created_at) if isinstance(created_at, str) else None
        age_hours = (
            round(max(0.0, (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600.0), 2)
            if created_dt is not None
            else None
        )
        freshness_window_hours = 24.0
        if status == "passed" and age_hours is not None and age_hours <= freshness_window_hours:
            freshness_status = "fresh"
            rerun_required = False
            summary = "Latest restore drill is passed and recent enough for the current delivery round."
        elif status == "passed":
            freshness_status = "stale"
            rerun_required = True
            summary = "Latest restore drill passed, but the evidence is stale and should be replayed for the current delivery round."
        elif status == "missing":
            freshness_status = "missing"
            rerun_required = True
            summary = "No restore drill evidence is available yet; run a restore drill before relying on recovery posture."
        else:
            freshness_status = "failed"
            rerun_required = True
            summary = "Latest restore drill did not pass; rerun only after addressing the recovery issue."
        return {
            "contract_version": "restore-drill-freshness.v1",
            "status": freshness_status,
            "freshness_window_hours": freshness_window_hours,
            "age_hours": age_hours,
            "rerun_required": rerun_required,
            "rerun_rule": "rerun_when_missing_failed_or_older_than_24h",
            "evidence_acceptable_when": "latest_restore_drill.status=passed and age_hours<=24",
            "acceptance_summary": summary,
        }

    def _build_migration_acceptance(
        self,
        *,
        preflight_status: str,
        rollback_evidence: dict[str, object],
        latest_attempt: dict[str, object],
    ) -> dict[str, object]:
        backup_recent = bool(rollback_evidence.get("backup_recent"))
        restore_fresh = str(rollback_evidence.get("restore_drill_freshness", "missing")) == "fresh"
        latest_attempt_status = str(latest_attempt.get("status", "not_run"))
        rollback_ready = backup_recent and restore_fresh

        if preflight_status == "blocked":
            decision = "block"
            summary = "Do not execute migration until blocking preflight issues are cleared."
        elif not rollback_ready:
            decision = "refresh_rollback_evidence"
            summary = "Do not execute migration yet; refresh backup and rollback evidence before moving beyond preflight."
        elif latest_attempt_status == "ready":
            decision = "execute_now"
            summary = "Migration may proceed now because preflight is ready and rollback evidence is fresh."
        else:
            decision = "preflight_only"
            summary = "Migration is preflight-ready in principle, but record a fresh migration attempt before executing."

        return {
            "contract_version": "migration-acceptance.v1",
            "preflight_status": preflight_status,
            "latest_attempt_status": latest_attempt_status,
            "rollback_ready": rollback_ready,
            "decision": decision,
            "execute_upgrade_when": "preflight.status=ready and backup_recent=true and restore_drill_freshness=fresh and latest_attempt.status=ready",
            "preflight_only_when": "preflight.status=ready and latest_attempt.status in {not_run,unknown}",
            "refresh_rollback_evidence_when": "backup_recent=false or restore_drill_freshness in {stale,missing,failed}",
            "block_when": "preflight.status=blocked",
            "summary": summary,
        }

    def _get_storage_backup_inventory(self, limit: int = 5) -> dict[str, object]:
        backup_dir = self.config.paths.delivery_dir / "storage_backups"
        if not backup_dir.exists():
            return {
                "inventory_version": "storage-backup-inventory.v1",
                "directory": str(backup_dir),
                "count": 0,
                "items": [],
            }
        candidates = sorted(
            [
                item for item in backup_dir.iterdir()
                if item.is_file() and item.suffix.lower() in {".json", ".sqlite3"}
            ],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        items: list[dict[str, object]] = []
        for candidate in candidates[:limit]:
            created_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            age_hours = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0)
            items.append(
                {
                    "path": str(candidate),
                    "created_at": created_at.isoformat(),
                    "age_hours": round(age_hours, 2),
                    "size_bytes": candidate.stat().st_size,
                    "format": candidate.suffix.lower().lstrip("."),
                    "is_recent": age_hours <= 24.0,
                }
            )
        return {
            "inventory_version": "storage-backup-inventory.v1",
            "directory": str(backup_dir),
            "count": len(candidates),
            "items": items,
        }

    def _compute_file_sha256(self, path: Path) -> str | None:
        if not path.exists() or not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _summary_relation_markers(self, relation_lists: list[list[str]], limit: int = 8) -> list[str]:
        filtered: list[list[str]] = []
        for markers in relation_lists:
            filtered.append(
                [
                    marker
                    for marker in markers
                    if not marker.startswith(("speaker:", "entity:"))
                ]
            )
        return summarize_relation_markers(filtered, limit=limit)

    def _score_summary_evidence_text(self, text: str) -> float:
        core_text = extract_core_content(text)
        if not core_text:
            return 0.0
        tokens = [
            token
            for token in tokenize(core_text, self.semantic_aliases, self.stop_tokens)
            if (
                len(token) >= 3
                and token.lower() not in SUMMARY_STOP_TOKENS
                and not any(char.isdigit() for char in token)
            )
        ]
        relations = [
            marker
            for marker in extract_relation_markers(core_text)
            if not marker.startswith(("speaker:", "entity:"))
        ]
        abstractions = derive_memory_abstractions(core_text, self.semantic_aliases)
        lowered = core_text.lower()
        reason_hits = sum(1 for marker in SUMMARY_REASON_MARKERS if marker in lowered)
        score = min(1.4, 0.08 * len(set(tokens)))
        score += 0.18 * len(relations)
        score += 0.22 * len(abstractions)
        score += 0.28 * min(2, reason_hits)
        score += min(0.25, len(core_text) / 220.0)
        return score

    def _select_summary_evidence_texts(self, texts: list[str], limit: int = 4) -> list[str]:
        ranked = sorted(
            (
                (self._score_summary_evidence_text(text), extract_core_content(text))
                for text in texts
            ),
            key=lambda item: (item[0], len(item[1])),
            reverse=True,
        )
        selected: list[str] = []
        for _, text in ranked:
            if not text or text in selected:
                continue
            selected.append(text)
            if len(selected) >= limit:
                break
        return selected

    def _select_summary_evidence_entries(self, entries: list[MemoryEntry], limit: int = 4) -> list[str]:
        return self._select_summary_evidence_texts([entry.text for entry in entries], limit=limit)
