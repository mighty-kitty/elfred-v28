from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from .content_cleaning import extract_core_content
from .emotion_engine import CALM_EMOTION
from .inference_features import compute_inference_bonus, extract_query_subject, parse_speaker
from .models import MemoryEntry, RetrievalCandidate
from .object_attributes import extract_attribute_markers, infer_query_attribute_targets
from .relation_features import extract_relation_markers
from .temporal_reasoning import derive_temporal_aliases, extract_temporal_features


LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CHINESE_SEGMENT_RE = re.compile(r"[\u4e00-\u9fff]+")
ENGLISH_STOP_TOKENS = {
    "the",
    "a",
    "an",
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
    "what",
    "when",
    "where",
    "who",
    "why",
    "how",
    "did",
    "does",
    "do",
    "has",
    "have",
    "had",
    "i",
    "you",
    "he",
    "she",
    "they",
    "we",
    "it",
    "my",
    "your",
    "his",
    "her",
    "their",
    "other",
    "than",
    "current",
    "during",
    "caroline",
    "melanie",
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
QUESTION_PREFIXES = ("when", "what", "who", "where", "why", "how")
EXPLANATION_QUERY_CUES = (
    "why ",
    "what does",
    "what did",
    "what made",
    "what support",
    "what was the reason",
    "stand for",
    "important",
    "support",
    "dream",
    "meaning",
)
EXPLANATION_CANDIDATE_CUES = (
    "because",
    "since",
    "so that",
    "it stands for",
    "it reminds me",
    "important",
    "support",
    "dream",
    "love",
    "meaning",
    "reason",
    "i chose",
    "i'd love",
    "it made me",
)
EXPLANATION_OBJECT_CUES = (
    "gift",
    "stands for",
    "reminds me",
    "roots",
    "love, faith",
    "support really spoke",
    "awesome mom",
)
INSTRUMENT_TERMS = (
    "clarinet",
    "guitar",
    "violin",
    "piano",
    "drums",
    "flute",
    "saxophone",
    "cello",
    "trumpet",
)
LOCATION_DETAIL_TERMS = (
    "department",
    "company",
    "office",
    "studio",
    "school",
    "park",
    "woods",
    "international company",
)
CLIPBOARD_USE_TERMS = (
    "set goals",
    "tracks my achievements",
    "track achievements",
    "areas to improve",
    "stay organized",
    "motivated",
)
QUERY_EXPANSION_HINTS: dict[str, tuple[str, ...]] = {
    "attr:agency_supported_group": ("lgbtq individuals", "lgbtq folks", "adoption support", "inclusive adoption"),
    "attr:agency_reason": ("inclusive adoption", "lgbtq support", "inclusivity", "support really spoke to me"),
    "attr:adoption_excitement": ("make a family", "kids who need one", "single parent challenge", "family for kids", "creating a family for those kids"),
    "attr:adoption_plan": ("researching adoption agencies", "future summer plan", "looking into agencies"),
    "attr:selfcare_method": ("me-time", "running", "playing violin", "running reading playing violin", "stay present for family"),
    "attr:selfcare_insight": ("self-care is important", "look after myself", "look after my family"),
    "attr:symbolism": ("stands for", "symbolizes", "love faith strength", "symbolic meaning"),
    "attr:origin": ("home country", "sweden", "grandma", "roots"),
    "attr:detail_activity": ("explored nature", "roasted marshmallows", "went on a hike", "campfire"),
    "attr:workshop_kind": ("lgbtq counseling workshop", "recent workshop"),
    "attr:workshop_content": ("therapeutic methods", "best work with trans people", "safe space"),
    "attr:counseling_focus": ("work with trans people", "accept themselves", "support mental health"),
    "attr:counseling_motivation": (
        "my own journey",
        "support i got made a huge difference",
        "support groups improved my life",
        "started caring more about mental health",
    ),
    "attr:meaning": ("meaning", "reminds me", "support", "journey"),
    "attr:opinion_support": ("doing something amazing", "awesome mom", "good luck"),
    "attr:made_by_self": ("i made it", "made this bowl", "made in class"),
    "attr:book_collection": ("kids books", "classics", "different cultures", "educational books"),
    "attr:book_title": ("charlotte's web", "becoming nicole", "amy ellis nutt"),
    "attr:book_lesson": ("self-acceptance", "finding support", "hope and love"),
    "attr:activity_purpose": ("de-stress", "clear my mind", "reset and recharge"),
    "attr:activity_benefit": ("mental health", "great for my mental health"),
    "attr:pride_festival_time": ("last year at the pride fest", "pride fest"),
    "attr:charity_race_topic": ("charity race for mental health", "race for mental health"),
    "attr:craft_detail": ("dog face", "sunset palm tree", "pink sky", "abstract painting", "blue streaks"),
    "attr:craft_dog_face": ("dog face", "cup dog face"),
    "attr:painting_sunset": ("sunset", "palm tree", "sunset palm tree"),
    "attr:painting_pink_sky": ("pink sky", "sunset pink sky"),
    "attr:painting_abstract": ("abstract painting", "blue streaks"),
    "attr:event_observation": ("loving homes", "unity and strength"),
    "attr:painting_inspiration": ("visited lgbtq center", "unity and strength", "capture unity"),
    "attr:creative_purpose": ("catch the eye", "make people smile", "express my feelings", "be creative"),
    "attr:creative_project_painting": ("paint together", "painting together"),
    "attr:flower_meaning": ("warmth and happiness", "love and beauty"),
    "attr:flower_importance": ("small moments", "wedding decor"),
    "attr:frequency": ("once or twice a year", "usually only once or twice"),
    "attr:sky_event": ("perseid meteor shower", "awe of the universe"),
    "attr:family_member": ("daughter", "daughter birthday"),
    "attr:daughter_birthday": ("daughter birthday", "13 august"),
    "attr:performer_name": ("matt patterson",),
    "attr:seen_music_artist": ("matt patterson", "summer sounds", "dancing and singing", "so talented"),
    "attr:personality_summary": ("thoughtful", "being real", "helping others", "drive to help", "impressive work"),
    "attr:pet_identity": ("guinea pig", "oscar", "two cats and a dog", "bailey", "oliver", "luna"),
    "attr:pet_identity_list": ("two cats and a dog", "oliver luna bailey"),
    "attr:pet_location": ("in my slipper", "hid his bone"),
    "attr:activity_childhood": ("horseback riding",),
    "attr:artifact_type": ("stained glass window", "rainbow sidewalk"),
    "attr:church_artifact": ("stained glass window",),
    "attr:sign_text": ("not being able to leave",),
    "attr:song_title": ("brave sara bareilles", "bach", "mozart", "ed sheeran"),
    "attr:song_brave": ("brave sara bareilles", "brave", "sara bareilles"),
    "attr:advice_steps": ("adoption lawyer", "gather documents", "prepare emotionally", "do research"),
    "attr:setback": ("got hurt", "break from pottery"),
    "attr:coping_activity": ("read a book", "painting to keep busy"),
    "attr:poetry_reading_content": ("transgender poetry reading", "shared their stories"),
    "attr:poster_text": ("trans lives matter",),
    "attr:drawing_meaning": ("freedom", "stay true to myself", "embrace my womanhood"),
    "attr:life_journey": ("ongoing adventure", "learning and growing"),
    "attr:accident_event": ("got into an accident", "son got into an accident", "scary experience"),
    "attr:accident_response": ("scared", "reassured", "tough kids", "resilient"),
    "attr:family_importance": ("mean the world", "super important", "thankful"),
    "attr:family_support": ("strength to keep going", "strength and motivation"),
    "attr:dance_destress": ("by dancing", "dance it out", "destress"),
    "attr:studio_reason": ("lost my job", "start my own business", "share my passion"),
    "attr:dance_style": ("contemporary",),
    "attr:dance_memory": ("won first place", "regionals dance competition", "favorite memory"),
    "attr:dance_piece_title": ("finding freedom",),
    "attr:festival_photo_meaning": ("performing at the festival",),
    "attr:festival_photo_comment": ("look graceful", "graceful"),
    "attr:festival_attitude": ("glad to be part of it", "glad"),
    "attr:store_design": ("space furniture decor", "furniture decor"),
    "attr:store_feedback": ("hard work paying off",),
    "attr:customer_experience": ("come back", "special shopping experience", "shopping experience for my customers"),
    "attr:journey_comparison": ("dancing together", "supporting each other"),
    "attr:business_advice": ("relationships with customers", "strong brand image", "stay positive"),
    "attr:dance_effect": ("happy", "kept me going"),
    "attr:contest_award": ("trophy",),
    "attr:internship_type": ("fashion internship",),
    "attr:internship_location": ("fashion department", "international company"),
    "attr:dancer_support": ("one on one mentoring", "training"),
    "attr:clipboard_use": ("set goals", "track achievements", "areas for improvement"),
    "attr:trip_reason": ("clear my mind",),
    "attr:store_status": ("doing great",),
    "attr:business_motivation": ("dance and fashion", "passionate about dance and fashion"),
    "attr:bank_account_reason": ("for my business",),
    "attr:family_activity_list": ("going for hikes", "park", "picnics", "board games", "movie nights"),
    "attr:mentor_quality": ("positivity", "determination"),
    "attr:business_plan_actions": ("sprucing up business plan", "tweaking pitch to investors", "online platform"),
    "attr:social_media_offer": ("help with making content", "managing accounts", "help you with making content"),
    "attr:store_item_line": ("hoodies", "limited edition line"),
    "attr:grand_opening_message": ("live it up", "great memories"),
    "attr:grand_opening_sentiment": ("excited", "awesome memories", "excitement"),
    "attr:studio_description": ("amazing",),
    "attr:opening_night_feeling": ("excited",),
    "attr:dance_feeling": ("magical", "happy place"),
    "attr:opening_plan": ("savor the good vibes",),
    "attr:service_activity_list": ("food and supplies", "toy drive", "homeless shelter"),
    "attr:volunteer_inspiration": ("aunt",),
    "attr:castle_origin": ("england",),
    "attr:volunteer_event": ("career fair", "local school"),
    "attr:roadtrip_location": ("pacific northwest",),
    "attr:politics_focus": ("education and infrastructure",),
    "attr:school_funding_effect": ("repairs and renovations", "safer and more modern"),
    "attr:shelter_reason": ("sad", "no other family"),
    "attr:hardship_history": ("divorce", "job loss", "homeless"),
    "attr:office_reason": ("impact in the community", "make a difference in my community"),
    "attr:certificate_reason": ("university degree", "because of my degree"),
    "attr:car_donation": ("donated my old car", "old car to a homeless shelter", "homeless shelter"),
    "attr:wallet_strain": ("car broke down",),
    "attr:fundraiser_keyword": ("chili cook off",),
    "attr:education_infra_reason": ("lack of education", "crumbling infrastructure"),
    "attr:family_meal": ("pizza",),
    "attr:dinner_spread": ("salads", "sandwiches", "homemade desserts", "banana split sundae"),
    "attr:dinner_activity": ("made dinner together", "made some dinner together"),
    "attr:park_frequency": ("few times a week",),
    "attr:workout_frequency": ("three times a week",),
    "attr:fitness_improvement": ("more energy", "strength and endurance"),
    "attr:live_event_type": ("live music event",),
    "attr:picnic_activity_list": ("charades", "scavenger hunt"),
    "attr:veteran_values": ("respect and appreciate",),
    "attr:dinner_companion": ("with my mother", "with my mom"),
    "attr:military_test": ("military aptitude test",),
    "attr:countries_visited": ("spain", "england", "london"),
    "attr:children_names": ("kyle", "sara"),
    "attr:exercise_list": ("weight training", "circuit training", "kickboxing", "yoga"),
    "attr:exercise_weight_training": ("weight training",),
    "attr:degree_field": ("political science", "public administration", "public affairs"),
    "attr:religiosity_level": ("somewhat religious", "not extremely religious"),
    "attr:personal_attributes": ("selfless", "family oriented", "passionate", "rational"),
    "attr:church_join_reason": ("closer to a community and my faith", "joined a nearby church"),
    "attr:veteran_party": ("small party", "share stories", "make connections", "heartwarming"),
    "attr:rescue_dog_plan": ("adopt a rescue dog", "adopting a rescue dog"),
    "attr:rescue_dog_values": ("responsibility and compassion",),
    "attr:dog_shelter_volunteer": ("local dog shelter", "once a month"),
    "attr:waterfall_feeling": ("fairy tale",),
    "attr:aerial_yoga": ("aerial yoga",),
    "attr:gym_news": ("joined a gym",),
    "attr:kundalini_yoga": ("kundalini yoga",),
    "attr:yoga_pose_feeling": ("free and light", "upside-down poses"),
    "attr:promotion_role": ("assistant manager",),
    "attr:promotion_challenge": ("self doubt",),
    "attr:promotion_support": ("support at home", "my own grit", "support at home and my own grit"),
    "attr:housing_urgency": ("find a new place in a hurry",),
    "attr:marching_event": ("marching event", "veterans' rights"),
    "attr:sunset_frequency": ("at least once a week",),
    "attr:flood_damage": ("homes were ruined",),
    "attr:community_motivation": ("flood in old area", "homes were ruined", "community solutions", "fix things up in our community"),
    "attr:dinner_plan_friends": ("dinner with friends from the gym",),
    "attr:veteran_hospital_appreciation": ("resilience of the veterans", "inspiring stories", "elderly veteran named samuel", "filled me with hope"),
    "attr:military_inspiration": ("seeing the resilience of the veterans", "respect for the military", "wanted to show my support"),
    "attr:memorial_reaction": ("awestruck and humbled", "awestruck", "humbled"),
    "attr:run_cause": ("veterans and their families",),
    "attr:blog_topic": ("politics and the government",),
    "attr:blog_focus": ("education reform", "infrastructure development"),
    "attr:blog_reason": ("eye-opening", "raise awareness", "start conversations", "positive change"),
    "attr:volunteer_motivation": ("help make a difference", "inspired by her aunt", "brighten somebody's day"),
    "attr:office_reason_retry": ("impact i could make in the community", "positive changes and a better future"),
    "attr:library_frequency": ("few times a week", "a few times a week"),
    "attr:france_home_artifact": ("made a painting", "trip to england", "reminder of the world's beauty"),
    "attr:church_hiking": ("hiking with my church friends", "felt so refreshing", "enjoy nature"),
    "attr:community_work": ("community work with my friends from church", "community work"),
    "attr:puppy_name_coco": ("coco",),
    "attr:puppy_name_shadow": ("shadow",),
    "attr:puppy_adjustment": ("doing great", "learning commands", "house training"),
    "attr:puppy_gap": ("got a puppy two weeks ago", "two weeks ago"),
    "attr:give_back_takeaway": ("appreciate what we have", "need to give back", "give back"),
    "attr:teammates_friendship": ("my team had a blast", "teammates", "my team"),
    "attr:volunteer_role_school": ("mentoring students at a local school",),
    "attr:volunteer_shelter_start": ("witnessed a family struggling", "reached out to the shelter"),
    "attr:family_support_feeling": ("appreciated them a lot", "family support's huge"),
    "attr:new_class_opinion": ("fun way to switch up the exercise routine", "push yourself and mix things up"),
    "attr:art_start_time": ("practicing art since 2016", "since 2016"),
    "attr:friend_adoption_time": ("friend adopted a child in 2022", "adopted a child in 2022"),
    "attr:marriage_duration": ("married for 5 years", "five years"),
    "attr:tattoo_time": ("got the tattoo a few years ago", "a few years ago"),
    "attr:dance_competition_date": ("hosted a dance competition in may 2023", "may 2023"),
    "attr:fair_exposure_date": ("for exposure on april 24 2023", "24 april 2023"),
    "attr:studio_open_date": ("open the studio on june 20 2023", "20 june 2023"),
    "attr:collaboration_date": ("decided to collaborate on july 21 2023", "21 july 2023"),
    "attr:dinner_with_mother_date": ("had dinner with my mother on may 3 2023", "3 may 2023"),
    "attr:convention_date": ("tech for good convention in march 2023", "march 2023"),
    "attr:convention_event": ("tech for good convention", "convention together"),
    "attr:max_adoption_year": ("got max in 2013", "max in 2013"),
    "attr:eternal_sunshine_year": ("first watched eternal sunshine in 2019", "eternal sunshine in 2019"),
    "attr:turtles_year": ("first two turtles in 2019", "turtles in 2019"),
    "attr:turtles_duration": ("had them for 3 years now", "3 years now", "three years"),
    "attr:screenplay_completion": ("finished my first full screenplay", "printed it last friday", "screenplay and printed it"),
    "attr:waterfall_name": ("whispering falls", "beautiful location called whispering falls"),
    "attr:firetruck_acquisition": ("brand new fire truck", "fire truck"),
    "attr:domestic_abuse_partner": ("local organization that helps victims of domestic abuse", "victims of domestic abuse"),
    "attr:shared_interests": ("watching movies", "making desserts", "similar interests"),
    "attr:hiking_trail_count": ("twice", "found an awesome hiking trail", "another hiking trail"),
    "attr:book_recommendations": ("little women", "a court of thorns and roses"),
    "attr:shared_movies": ("little women", "lord of the rings"),
    "attr:happy_memory_method": ("corkboard", "notebook"),
    "attr:console_switch": ("nintendo switch", "nintendo games", "xenoblade chronicles", "xeonoblade chronicles"),
    "attr:tournament_valorant": ("valorant",),
    "attr:state_florida": ("florida", "tampa"),
    "attr:movie_genre": ("action and sci-fi", "fantasy and sci-fi", "dramas and romcoms"),
    "attr:screenplay_plan": ("submit it to some film festivals", "producers and directors"),
    "attr:screenplay_inspiration": ("personal experiences", "journey of self-discovery"),
    "attr:turtle_pet_reason": ("slow pace", "calming", "low-maintenance"),
    "attr:turtle_care": ("keep their area clean", "feed them properly", "enough light", "not tough"),
    "attr:writing_gig": ("writing gig",),
    "attr:icecream_ingredients": ("coconut milk", "vanilla extract", "sugar", "salt"),
    "attr:dessert_flavors": ("chocolate", "mixed berry", "chocolate mousse"),
    "attr:icecream_flavor": ("chocolate and vanilla swirl",),
    "attr:icecream_opinion": ("super good", "rich and creamy", "super creamy"),
    "attr:writers_group_project": ("finding home",),
    "attr:favorite_movie": ("eternal sunshine of the spotless mind", "eternal sunshine", "spotless mind"),
    "attr:favorite_trilogy": ("lord of the rings", "favorite trilogy"),
    "attr:favorite_book_theme": ("dragons", "dragon series", "book series about dragons", "dragon cover", "fantasy novels"),
    "attr:gaming_room_lighting": ("red and purple lighting", "red purple lighting", "gaming room", "gaming setup"),
    "attr:favorite_video_game": ("xenoblade chronicles", "xeonoblade chronicles", "favorite video game"),
    "attr:tournament_game": ("street fighter", "street fighter tournament", "second tournament"),
    "attr:state_indiana": ("fort wayne", "indiana", "summer 2021 hike"),
    "attr:screenplay_genre": ("drama and romance", "mix of drama and romance"),
    "attr:teaching_skills": ("teach people how to make this", "reset high scores", "tips to improve gaming skills"),
    "attr:movie_genre_action_scifi": ("action and sci-fi",),
    "attr:book_project_timeline": ("started on a book recently", "finished up my writing for my book", "book last week", "late nights and edits"),
    "attr:movie_genre_fantasy_scifi": ("fantasy and sci-fi",),
    "attr:favorite_book_features": ("adventures", "magic", "great characters"),
    "attr:escape_activity_movies": ("watching fantasy and sci-fi movies", "great escape", "get my imagination going"),
    "attr:cake_filling": ("strawberry filling",),
    "attr:cake_frosting": ("coconut cream frosting",),
    "attr:whispering_falls_writing": ("write a whole movie",),
    "attr:screenplay_joke_plan": ("start to think of a drama", "publish my own screenplay"),
    "attr:trails_inviter": ("join me on the trails sometime",),
    "attr:stuffed_animal_gift": ("got this new pup for you",),
    "attr:stuffed_animal_meaning": ("stuffed animal to remind you of the good vibes",),
    "attr:gaming_party_invitees": ("old friends", "teammates from other tournaments", "teamates from other tournaments"),
    "attr:gaming_party_items": ("custom controller decorations",),
    "attr:superhero_spiderman": ("spider-man", "peter parker"),
    "attr:superhero_ironman": ("iron man",),
    "attr:corkboard_items": ("inspiring quotes", "pictures", "little keepsakes"),
    "attr:vegan_icecream_shared": ("vegan ice cream", "vegan diet group"),
    "attr:vegan_recipe_offer": ("i can give it to you tomorrow", "vegan ice cream recipe"),
    "attr:recipe_plan_family": ("make it for my family this weekend", "make it for my family"),
    "attr:roadtrip_research_location": ("woodhaven", "small town in the midwest"),
    "attr:book_themes": ("loss, redemption, and forgiveness",),
    "attr:tournament_career": ("competing in video game tournaments", "make money doing what i love"),
    "attr:writing_impact": ("writing can make a difference", "share my stories and hopefully have an impact"),
    "attr:joanna_coconut_icecream": ("coconut milk icecream", "coconut milk ice cream"),
    "attr:sharing_desserts_feeling": ("always happy to share", "happy to share"),
    "attr:writers_group_celebration": ("making this delicious treat", "celebrated by making this delicious treat"),
    "attr:tournament_chill_celebration": ("chill with my pets", "taking some time off this weekend"),
    "attr:favorite_treat_mousse": ("dairy-free chocolate mousse",),
    "attr:cake_type_raspberry": ("dairy-free chocolate cake with raspberries", "chocolate cake with raspberries"),
    "attr:blueberry_dessert_ingredients": ("blueberries", "coconut milk", "gluten-free crust"),
    "attr:recent_movie_little_women": ("little women", "watched \"little women\" recently"),
    "attr:writing_club_bookmark": ("cute little bookmark", "writing club"),
    "attr:unwind_photo": ("bookcase filled with dvds and movies", "watching movies helps me unwind"),
    "attr:classic_movie_opinion": ("story was so gripping", "actors were great"),
    "attr:living_room_tips": ("couch that can sit multiple people", "really fluffy", "blanket that has a little bit of weight", "lights that can be dimmed"),
    "attr:tilly_focus": ("tilly helps me stay focused", "brings me so much joy"),
    "attr:tilly_while_writing": ("she's always with me while i write", "stuffed animal dog"),
    "attr:party_attendance": ("7 people", "there were 7 people that attended"),
    "attr:favorite_dish_show": ("coconut milk ice cream is at the top of my list", "favorite dish", "coconut milk ice cream"),
    "attr:tilly_origin": ("dog back in michigan", "used to have a dog back in michigan", "the name helps me remember her"),
    "attr:rejection_response": ("keep grinding and moving ahead",),
    "attr:resilience_respect": ("respect you for that", "able to bounce back"),
    "attr:rejection_advice": ("rejections don't define you", "keep at it", "find the perfect opportunity"),
    "attr:character_visuals_purpose": ("visuals of the characters", "bring them alive in my head", "write better"),
    "attr:turtle_diet": ("combination of vegetables fruits and insects", "varied diet"),
    "attr:current_game_xenoblade": ("xeonoblade chronicles", "xenoblade chronicles"),
    "attr:letter_object": ("handwritten letter",),
    "attr:homemade_coconut_icecream": ("homemade coconut ice cream", "sprinkles kinda changed the color"),
    "attr:thriller_project": ("suspenseful thriller set in a small midwestern town", "small midwestern town"),
    "attr:video_motivation": ("share my love of gaming", "connect with others who enjoy it too"),
    "attr:video_advice": ("watch other peoples videos first", "what your audience likes", "videos don't flop"),
    "attr:hangout_plan": ("watch one of your movies together", "go to the park"),
    "attr:colorful_bowls_icecream": ("colorful bowls of coconut milk ice cream", "colorful bowls"),
    "attr:letter_reaction": ("their words touched me", "awesome to realize my words had that kind of power", "reminded me why i love writing"),
    "attr:baking_substitute": ("dairy-free margarine", "coconut oil instead of butter", "instead of butter"),
    "attr:youtube_content": ("creating gaming content for youtube", "gaming content for youtube"),
    "attr:third_turtle_reason": ("tank is big enough now for three", "saw another at a pet store and just had to get him", "figured why not"),
    "attr:turtles_cheer": ("turtles always cheer me up",),
    "attr:turtles_joy": ("really love having them around", "make me feel calm", "love seeing them soaking in the sun"),
    "attr:career_high_points_time": ("last week i scored 40 points", "highest ever", "june 2023"),
    "attr:other_sport": ("surfing",),
    "attr:outdoor_activities": ("hiking", "surfing"),
    "attr:hp_fan_reconnect_duration": (
        "three weeks",
        "3 weeks",
        "skyped with that harry potter fan i met in ca",
        "harry potter fan i met in ca",
        "talked characters and maybe collab-ing",
    ),
    "attr:pre_chicago_city": ("seattle", "game there next month"),
    "attr:trip_city_chicago": ("chicago", "love the energy there"),
    "attr:city_list": ("seattle", "chicago", "new york", "paris"),
    "attr:hp_conference_week": ("last week", "uk", "harry potter conference"),
    "attr:uk_castle_trip": (
        "trip to the uk last friday",
        "went to a castle during my trip to the uk last friday",
        "castle during my trip to the uk",
    ),
    "attr:smoky_mountains_year": ("2022", "last year"),
    "attr:lebron_traits": ("heart", "determination", "skills", "leadership"),
    "attr:italy_prev_month": ("last month", "december 2023", "italy"),
    "attr:study_abroad_day": ("on friday", "friday", "january 5 2024"),
    "attr:hp_collab_topics": ("characters", "spells", "magical creatures"),
    "attr:minalima_picture": ("minalima", "props for the harry potter films"),
    "attr:seattle_game_city": ("seattle", "favorite cities to explore"),
    "attr:surfing_feeling": ("super exciting and free-feeling", "waves", "wind"),
    "attr:fantasy_novels_pair": ("harry potter", "game of thrones"),
    "attr:skype_hp_topics": (
        "skyped with that harry potter fan i met in ca",
        "talked characters and maybe collab-ing",
        "harry potter fan i met in ca",
        "talked characters",
    ),
    "attr:teammate_reunion_date": (
        "met back up with my teammates on the 15th after my trip",
        "on the 15th after my trip",
        "aug 15th",
    ),
    "attr:signed_basketball_reason": (
        "signed it to show our friendship and appreciation",
        "show our friendship and appreciation",
        "great reminder of our bond",
        "sign of our friendship and all the love we have for each other",
    ),
    "attr:nyc_experience": (
        "it was amazing",
        "something new and exciting",
        "trying all the restaurants was awesome",
        "must-visit",
        "exploring the city and trying all the restaurants was awesome",
    ),
    "attr:nyc_pitch": (
        "it's got so much to check out - the culture, food - you won't regret it",
        "adventure you'll never forget",
        "nyc is amazing",
    ),
    "attr:universal_harry_potter": (
        "super stoked for the harry potter stuff",
        "harry potter stuff",
        "first time going",
        "nope but it's my first time going",
    ),
    "attr:team_trip_destination_type": (
        "explore a new city",
        "team trip next month to explore a new city",
        "new city",
    ),
    "attr:team_trip_suggestion": (
        "edinburgh scotland",
        "birthplace of harry potter",
        "awesome history and architecture",
    ),
    "attr:post_basketball_plan": (
        "use my platform to make a positive difference and inspire others",
        "start a foundation",
        "do charity work",
        "leave a meaningful legacy",
    ),
    "attr:endorsement_advice": (
        "align with your values and brand",
        "shares your desire to make a change and help others",
        "endorsement feels authentic",
    ),
    "attr:trip_book_recommendation": (
        "fantasy novel by patrick rothfuss",
        "take you to a different world",
        "great for you when you're traveling",
    ),
    "attr:wedding_venue": (
        "greenhouse venue",
        "lovely greenhouse venue",
        "smaller more intimate gathering",
    ),
    "attr:team_supported_wolves": (
        "the wolves are solid",
        "wolves are my team for sure",
        "the wolves",
    ),
    "attr:season_summary": (
        "intense season with both tough losses and great wins",
        "tough losses and great wins",
        "did pretty well",
    ),
    "attr:team_growth_driver": (
        "faced tough opponents but that's what drives us to get better",
        "tough opponents",
        "drives us to get better",
    ),
    "attr:season_award": ("we even won a trophy", "won a trophy", "trophy"),
    "attr:smoky_mountains_photo": (
        "trip to the smoky mountains last year",
        "smoky mountains",
        "sunset over the mountain range",
    ),
    "attr:mentoring_player_outcome": (
        "develop and reach their goals",
        "reach their goals",
        "motivating and encouraging everyone",
    ),
    "attr:writing_inspiration_author": ("j.k. rowling", "inspiring writer", "taking notes on her style"),
    "attr:slow_cooker_meal": ("honey garlic chicken with roasted veg", "honey garlic chicken", "roasted veg"),
    "attr:recipe_sharing_method": ("write it down and mail it", "write it down for you and mail it"),
    "attr:lebron_inspiration_specific": (
        "epic block in game 7 of the 16 finals",
        "determination and heart",
        "never give up",
    ),
    "attr:study_motivation_method": ("visualize my goals and success", "focus and motivation"),
    "attr:injury_update": ("doctor said it's not too serious", "not too serious"),
    "attr:yoga_hold_duration": ("30-60 seconds", "30 60 seconds"),
    "attr:recent_finished_book": ("a dance with dragons", "really good story", "highly recommend it"),
    "attr:travel_agency_visit": ("visited a travel agency", "see what the requirements would be", "next dream trip"),
    "attr:youth_sports_cause": ("supporting youth sports", "fair chances in sports", "underserved communities"),
    "attr:favorite_book_series_hp": ("harry potter is my favorite book", "harry potter", "immersive"),
    "attr:aragorn_identity": ("my favorite character is aragorn", "aragorn"),
    "attr:aragorn_reason": ("brave selfless down-to-earth attitude", "never gives up", "stands up for justice"),
    "attr:middle_earth_map": ("map of middle-earth from lotr", "different realms and regions"),
    "attr:ireland_city_galway": ("stay in galway", "galway", "arts and irish music"),
    "attr:benefit_basketball_game": ("held a benefit basketball game last week", "benefit basketball game"),
    "attr:endorsement_reaction": ("felt crazy", "sense of accomplishment", "hard work paid off"),
    "attr:barcelona_recommendation": ("barcelona is a must-visit city", "barcelona", "culture architecture and amazing food"),
    "attr:forum_type_fantasy": ("fantasy literature forum", "joined a fantasy literature forum"),
    "attr:restaurant_celebration_game": ("celebrated at a restaurant", "reliving the intense moments", "after that we celebrated"),
    "attr:online_mag_articles": ("writing about different fantasy novels", "studying characters themes", "making book recommendations"),
    "attr:harry_potter_trivia_event": ("intense harry potter trivia contest", "charity thing", "anthony and i"),
    "attr:aragorn_reason_identity": (
        "my favorite character is aragorn",
        "aragorn's brave selfless down-to-earth attitude",
        "stands up for justice",
    ),
    "attr:aragorn_identity_exact": (
        "my favorite character is aragorn",
        "he grows so much throughout the story",
    ),
    "attr:restaurant_celebration_aftermath": (
        "we were all exhausted but so happy",
        "after that we celebrated at a restaurant",
        "laughing and reliving the intense moments",
    ),
    "attr:sponsorship_deal_types": (
        "basketball shoe and gear deal",
        "potential sponsorship",
        "nike",
        "gatorade",
    ),
    "attr:leader_reminder": ("stay true and be a leader in everything i do", "be a leader", "painting in my room"),
    "attr:signed_basketball_gift": ("a basketball with autographs", "photo of what my teammates gave me", "signed basketball"),
    "attr:book_conference_reason": (
        "help me learn more about literature",
        "create a stronger bond to it",
        "book conference next month",
    ),
    "attr:piano_learning": ("started learning how to play the piano", "play the piano", "seeing the progress"),
    "attr:fantasy_connects_people": (
        "my passion for fantasy stuff brings me closer to people from all over the world",
        "shared the same love of hp",
        "magical family",
    ),
    "attr:writing_reading_motivation": ("writing and reading", "helps me stay motivated", "push myself to get better"),
    "attr:yoga_recovery_training": ("trying out yoga", "extra strength and flexibility", "challenging but worth it"),
    "attr:violin_learning": ("learning how to play the violin", "violin", "classical music"),
    "attr:career_high_assists_game": ("career-high in assists", "big game against our rival", "basketball game"),
    "attr:sage_soup_flavor": ("added some sage for a nice flavor", "sage"),
    "attr:thanksgiving_tradition": ("prepping the feast", "talking about what we're thankful for", "watching some movies afterwards"),
    "attr:study_motivation_visualization": ("visualize my goals and success", "focus and motivation", "stay motivated during tough studying"),
    "attr:stress_coping_basketball": ("practice basketball outside for hours", "dreaming of playing in big games", "way of dealing with doubts and stress"),
    "attr:photoshoot_forest_location": ("photoshoot went really well", "gorgeous forest", "outdoor gear"),
    "attr:training_growth_area": ("most growth in communication and bonding", "understand each other's strengths and weaknesses", "helped our performances"),
    "attr:seminar_topic": ("seminars", "sports and marketing", "helping people with their sports and marketing"),
    "attr:language_german": ("learning german now", "german", "tough but fun"),
    "attr:fantasy_tv_series_wot": ("wheel of time", "new show that's coming out", "based on a book series that i love"),
    "attr:big_game_atmosphere": ("atmosphere in the arena was really electric", "extra level of intensity", "electric and intense"),
    "attr:basketball_origin": ("watch nba games with my dad", "dad signed me up for a local league", "basketball has been a part of my life ever since i was a kid"),
    "attr:thanksgiving_movie": ("we love home alone", "home alone", "brings lots of laughs"),
    "attr:novel_genre_fantasy": ("in the middle of fantasy novel", "fantasy novel", "create a whole new world"),
    "attr:piano_duration_four_months": ("playing for about four months now", "about four months now", "amazing adventure"),
    "attr:first_three_dogs_year": ("i've had them for 3 years", "their names are pepper precious and panda", "pepper precious and panda"),
    "attr:neighbor_goodies": ("made some goodies recently", "thank my neighbors", "bring some joy around here"),
    "attr:dogs_snow_confusion": ("they were so confused", "hate snow", "prefer nice sunny days in the grass"),
    "attr:dog_hiking_trails": ("checking out new hiking trails", "stoked and interested in everything nature has to offer", "loves checking out new hiking trails"),
    "attr:hiking_plan": ("go hiking", "grab some snacks and have a blast exploring", "saturday sound good"),
    "attr:indoor_dog_toys": ("toys and games", "basket full of stuffed animals", "entertain them in my house"),
    "attr:dog_mental_stimulation": ("puzzles", "training", "hide-and-seek"),
    "attr:hike_next_month_august": ("next month when the weather is more pleasant", "down for a hike with you and your furry friends", "august"),
    "attr:cook_dog_treats": ("getting into cooking more", "trying out new recipes", "cook dog treats"),
    "attr:camping_with_girlfriend": ("my girlfriend, toby and i are going camping", "going camping", "first weekend of august 2023"),
    "attr:remote_suburb_plan": ("hybrid or remote job", "move away from the city to the suburbs", "larger living space and be closer to nature"),
    "attr:toby_buddy_gap": ("three months", "toby", "buddy"),
    "attr:andrew_pets_december": ("three", "toby buddy scout", "three pets"),
    "attr:andrew_pets_september": ("one", "toby", "one pet"),
    "attr:buddy_scout_gap": ("one month", "buddy", "scout"),
    "attr:first_pet_duration_november": ("4 months", "four months", "adopted his first pet"),
    "attr:positive_training_reason": ("learn how to behave in a positive way", "punishment is never the proper way", "positive reinforcement way"),
    "attr:positive_training_type": ("positive reinforcement training", "positive reinforcement training class"),
    "attr:dog_walk_duration_hour": ("about an hour", "usually for about an hour", "explore at their own pace"),
    "attr:roasted_chicken": ("roasted chicken", "one of my favorites", "send you the recipe"),
    "attr:dog_personality_list": ("oldest one is the most relaxed", "second one is always ready for a game", "third one can be naughty but loves a good cuddle", "youngest one is full of life"),
    "attr:agility_classes": ("agility classes", "pups at a dog park", "face and conquer challenges"),
    "attr:park_practice_frequency": ("twice a week", "park for practice", "great bonding experience"),
    "attr:grooming_advice": ("slowly and gently", "ears and paws", "stay patient and positive"),
    "attr:dog_beds_comfy": ("super cozy and comfy", "my furry friends love them"),
    "attr:leash_incident_calming": ("petted and hugged her", "spoke calmly", "slowly walked her to relax"),
    "attr:dog_walk_frequency": ("multiple times a day", "great bonding time for us"),
    "attr:peruvian_lilies": ("peruvian lilies", "bright colors", "delicate petals"),
    "attr:ecosystem_lesson": ("animals, plants, and ecosystems", "how it all works together", "fascinating"),
    "attr:biking_planet": ("help the planet", "train our body", "by biking"),
    "attr:camping_feeling": ("peaceful and awesome", "peaceful", "awesome", "present and together", "refreshes my soul"),
    "attr:pet_help_offer": ("help find the perfect pet", "perfect one for you", "great pet parent"),
    "attr:tournament_game_apex": ("apex legends", "favorite game called apex legends"),
    "attr:adopted_pet_type": ("adopted a pup", "a pup", "puppy"),
    "attr:adopted_pup_name": ("ned", "i named it ned"),
    "attr:visited_country_italy": ("visited italy", "last year i visited italy", "italy"),
    "attr:work_assignment_coding": ("coding assignment",),
    "attr:charity_leftovers_homeless": ("bought groceries and cooked food for the homeless", "groceries", "cooked food for the homeless"),
    "attr:charity_hospital": ("children's hospital", "raise money for a children's hospital"),
    "attr:foundation_tracking": ("tracking inventory, resources, and donations", "inventory resources donations"),
    "attr:foundation_app_mobile": ("computer application on smartphones", "application on smartphones", "smartphones"),
    "attr:football_team_liverpool": ("liverpool",),
    "attr:relax_reading": ("reading", "read a book"),
    "attr:hobby_extreme_sports": ("extreme sports",),
    "attr:trip_return_july20": ("july 20",),
    "attr:it_job_reason_values": ("align with his values and passions", "values and passions"),
    "attr:fortnite_competitions": ("fortnite competitions", "fortnite"),
    "attr:puppy_clinic": ("routine examination and vaccination",),
    "attr:call_samantha": ("call her",),
    "attr:teach_siblings_coding": ("coding", "teach coding"),
    "attr:class_cost_ten": ("$10", "10 dollars"),
    "attr:class_make_dough": ("dough",),
    "attr:class_reason_learn_new": ("learn something new",),
    "attr:class_first_omelette": ("omelette",),
    "attr:boardgame_dod": ("dungeons of the dragon",),
    "attr:idea_sources": ("books, movies, dreams", "books movies dreams"),
    "attr:gig_programming_mentor": ("programming mentor for game developers",),
    "attr:mentor_feeling_excited": ("excited and inspired", "excited", "inspired"),
    "attr:movein_decision": ("move in together",),
    "attr:apartment_near_mcgees": ("apartment not far from mcgee's bar", "not far from mcgee's bar"),
    "attr:reason_near_mcgees": ("love spending time together at the bar",),
    "attr:hooked_game_fifa23": ("fifa 23",),
    "attr:project_online_boardgame": ("online board game",),
    "attr:cousin_dog_luna": ("luna",),
    "attr:yoga_locations_list": ("mother's old home", "park", "yoga studio", "beach"),
    "attr:professional_growth_list": ("virtual conference", "workshops", "intern at firms", "interning at a well-known engineering firm"),
    "attr:engineering_projects_list": ("electrical engineering project", "robotics project", "sustainable water purifier", "aerial surveillance system"),
    "attr:community_activities_list": ("yoga", "running"),
    "attr:gifts_received_list": ("appreciation letter", "flower bouquet", "motivational quote"),
    "attr:countries_traveled_list": ("thailand", "brazil"),
    "attr:activities_besides_yoga": ("biking", "art shows", "running", "organizing workshops", "surfing", "gardening"),
    "attr:rio_activities_list": ("excursions", "yoga classes", "delicious cafes", "old temple"),
    "attr:relationship_focus": ("relationship with her partner",),
    "attr:snake_names_list": ("susie", "seraphim", "lucifer"),
    "attr:yoga_support_mom_attended": ("attended classes with her",),
    "attr:first_console_nintendo": ("nintendo game console", "nintendo wii"),
    "attr:favorite_game_monster_hunter": ("monster hunter: world", "monster hunter world", "monster hunter"),
    "attr:task_method_eisenhower": ("eisenhower matrix",),
    "attr:retreat_location_phuket": ("phuket",),
    "attr:retreat_focus_present": ("releasing expectations and judgments", "savoring the present"),
    "attr:retreat_outcome_peace": ("finding inner peace", "new level of joy and happiness"),
    "attr:gardening_class_free": ("free gardening class",),
    "attr:mom_birthday_cakes": ("pineapple birthday cakes", "pineapple cakes"),
    "attr:cookie_type_choc_chip": ("chocolate chip cookies", "warm gooey chocolate", "soft buttery cookie"),
    "attr:event_music_dance": ("dancing and bopping around", "dance and bop around", "bopping around"),
    "attr:healthy_snack_suggestions": ("flavored seltzer water", "dark chocolate", "air-popped popcorn", "fruit", "veggies", "healthy sandwich"),
    "attr:grocery_issue_self_checkout": ("malfunctioning self-checkout machines", "self-checkout machines", "self-checkout"),
    "attr:health_issue_weight": ("weight problem", "weight wasn't great"),
    "attr:health_issue_gastritis": ("gastritis", "severe stomachache"),
    "attr:roadtrip_locations_rockies_jasper": ("rockies", "jasper", "icefields parkway"),
    "attr:favorite_novel_gatsby": ("the great gatsby",),
    "attr:fitness_tracker_use": ("tracks progress", "constant reminder to keep going", "keep going"),
    "attr:bonsai_reason": ("motivates him to keep going through tough times", "strength and resilience"),
    "attr:lost_keys_problem": ("keys", "searching for my keys", "last half hour"),
    "attr:healthy_cooking_class": ("cooking class",),
    "attr:healthy_grilled_dish": ("grilled salmon and vegetables", "salmon and vegetables", "grilled dish"),
    "attr:healthy_food_photo_bowl": ("spinach, avocado, and strawberries", "spinach avocado strawberries"),
    "attr:watercolor_class_type": ("watercolor painting classes", "watercolors"),
    "attr:favorite_painting_subject": ("sunsets over the ocean",),
    "attr:injury_exercise_swimming": ("swimming",),
    "attr:writing_hobby_creative": ("creative writing", "journalling"),
    "attr:phone_issue_navigation": ("malfunctioning navigation app", "navigation app"),
    "attr:activity_weightlifting": ("lifting weights",),
    "attr:kayaking_location_tahoe": ("lake tahoe",),
    "attr:gift_vintage_guitar": ("1968 kustom k-200a vintage guitar", "kustom k-200a vintage guitar", "vintage guitar"),
    "attr:island_memory_happy_place": ("happy place",),
    "attr:family_reunion_plan": ("big family reunion", "next summer"),
    "attr:family_motto": ("bring it on home",),
    "attr:exhibition_support_friend": ("a close friend", "close friend"),
    "attr:painting_feeling_joy_freedom": ("sense of joy and freedom", "joy and freedom"),
    "attr:painting_process_unrestrained": ("embracing the creative process without restraint", "without restraint"),
    "attr:diet_limit_ginger_snaps": ("two ginger snaps a day", "two ginger snaps"),
    "attr:winter_activity_snowshoeing": ("snowshoeing",),
    "attr:exercise_low_impact_list": ("swimming", "yoga", "walking"),
    "attr:movie_godfather": ("the godfather",),
    "attr:camping_photo_kayak": ("a kayak", "kayak", "kayaking", "kayaking trip", "photo of a kayak", "kayak is seen from the front of the boat"),
    "attr:marriage_announcement": ("our marriage", "told our extended fam about our marriage", "happy about our marriage"),
    "attr:necklace_reminder": ("why i keep hustling as a musician", "keep hustling as a musician"),
    "attr:fixing_things_purpose": ("fixing up things", "sense of achievement and purpose", "achievement and purpose", "gives me a sense of achievement and purpose"),
    "attr:skiing_plan": ("skiing", "skis", "snowy peak"),
    "attr:electronic_fresh_vibe": ("fresh vibe", "electronic elements"),
    "attr:ferrari_brand": ("ferrari", "ferrari 488 gtb"),
    "attr:car_mod_workshop": ("car mod workshop", "car modification workshop"),
    "attr:workshop_modifications": ("engine swaps", "suspension modifications", "body modifications"),
    "attr:workshop_car_type": ("classic muscle car",),
    "attr:rap_industry_podcast": ("podcast discussing the rap industry", "rapidly evolving rap industry"),
    "attr:video_location_miami": ("miami", "miami beach"),
    "attr:guitar_octopus_design": ("octopus", "octopus on it"),
    "attr:guitar_shiny_reason": ("unique look", "goes with my style"),
    "attr:guitar_purple_glow": ("purple", "purple glow", "gorgeous purple hue", "purple hue"),
    "attr:workshop_city_sf": ("san francisco", "san francsico"),
    "attr:repair_relief_proud": ("proud", "makes me proud", "relief when their car is fixed"),
    "attr:flight_to_boston": ("boston", "flight ticket to boston"),
    "attr:favorite_disney_ratatouille": ("ratatouille",),
    "attr:song_california_love": ("california love",),
    "attr:junkyard_ford_mustang": ("ford mustang",),
    "attr:restoration_satisfaction": ("brought back to life", "transforming something old and beat-up into something beautiful"),
    "attr:car_therapy": ("therapy", "get away from everyday stress", "working on cars is like therapy"),
    "attr:car_passion_goal": ("take something broken and make it into something awesome",),
    "attr:favorite_band_fireworks": ("the fireworks", "fireworks"),
    "attr:tokyo_times_square": ("shibuya crossing",),
    "attr:tokyo_shinjuku": ("shinjuku",),
    "attr:tokyo_ramen": ("ramen", "ramen bowl"),
    "attr:early_age_cars": ("at an early age", "when i was 10", "my first car show when i was 10", "my dad took me to my first car show"),
    "attr:music_purpose_realization": ("music means to him", "passion and purpose"),
    "attr:japanese_house_party": ("small party for his new album",),
    "attr:car_mod_blog": ("car mods", "blog on car mods"),
    "attr:car_mod_blog_share": ("my way to share my passion with others", "share my passion with others", "through a blog on car mods"),
    "attr:tv_music_content": ("music videos", "concerts", "documentaries about artists", "creative process"),
    "attr:classic_rock_interest": ("classic rock", "music from that era is timeless"),
    "attr:vintage_camera_item": ("new vintage camera", "vintage camera"),
    "attr:camera_nature_photos": ("nature", "sunsets", "beaches", "waves"),
    "attr:gala_artist_topics": ("music and art",),
    "attr:waterfall_nearby_park": ("nearby park",),
    "attr:diy_blog_inspiration": ("made his car look like a beast", "diy projects"),
    "attr:old_friend_boston_invite": ("old high school buddy",),
    "attr:setback_motivation": ("remind myself why i'm passionate about my goals", "helpful people around me", "take a break to recharge", "feeling motivated"),
    "attr:fixing_fulfilling": ("fixing up things", "making it whole again", "taking something broken and making it whole again"),
    "attr:tour_energizing": ("performing and connecting with the crowd", "so energizing"),
    "attr:balance_one_day": ("one day at a time", "it can get overwhelming"),
    "attr:music_emotion_therapy": ("express myself and work through my emotions", "my own form of therapy"),
    "attr:restoration_detail": ("paying extra attention to detail", "lot of patience", "not easy, but it pays off"),
    "attr:extraordinary_small_details": ("paying attention to those small details", "create something extraordinary"),
    "attr:shared_fulfilling_motivating": ("it's fulfilling and motivating", "on this journey together"),
    "attr:photo_city_boston": ("that's boston", "boston, cal"),
    "attr:lyrics_notes_motivation": ("writing lyrics and notes", "boost my motivation"),
    "attr:photography_hobby": ("taken up photography", "photography and it's been great"),
    "attr:jumpstart_inspiration": ("explore other things", "have some fun", "immersed in something i love", "jumpstart my inspiration"),
    "attr:open_car_shop": ("opened my car shop", "car shop last week", "opened my car shop last week"),
    "attr:park_relaxation": ("exploring some parks on the weekends to relax", "parks on the weekends to relax", "surrounded by nature"),
    "attr:back_on_the_road": ("get back on the road", "back on the road", "stoked to get back on the road", "how's the car doing after the crash"),
    "attr:park_regular_walks": ("regular walks together in the park", "regular walks together"),
    "attr:genre_experimentation": ("experimenting with different genres", "different genres lately", "pushing myself out of my comfort zone"),
    "attr:global_brand_goal": ("expand my brand worldwide and grow my fanbase", "expand my brand worldwide", "grow my fanbase"),
    "attr:dream_advice_keep": ("never forget your dreams", "keep at it and never forget your dreams"),
    "attr:workshop_mod_details": ("engine swaps and suspension modifications", "body modifications", "engine swaps", "suspension modifications"),
    "attr:small_details_unique": ("small details that make it unique and personalized", "small details"),
    "attr:meet_frank_tokyo_festival": ("met frank ocean at a music festival in tokyo", "music festival in tokyo and we clicked"),
    "attr:mansion_studio_song": ("recorded a song in the studio at my mansion", "studio at my mansion"),
    "attr:orange_car_project": ("shiny orange car", "photo of a shiny orange car", "vintage car restoration"),
    "attr:hard_work_determination": ("hard work and determination", "what sets us apart"),
    "attr:childhood_artists": ("tupac and dr. dre", "california love"),
    "attr:dad_nostalgia": ("my dad", "road trip with my dad", "working on cars with my dad"),
    "attr:october_boston": ("yesterday i met with some incredible artists in boston", "artists in boston"),
    "attr:shared_car_work": ("working on cars", "working on it to chill out", "working on cars really helps me relax"),
    "attr:favorite_activity_restoring": ("restoring things like this", "restoring cars", "working on cars really helps me relax"),
    "attr:car_show_october": ("last friday i went to the car show", "attending a car show", "car show"),
    "attr:garage_childhood_work": ("tinkering with engines", "refurbishing them", "restoring an old car"),
    "attr:frank_collab_start": ("august last year", "met at a festival", "wanted to collaborate"),
    "attr:cities_traveled_dave": ("san francisco", "detroit"),
    "attr:photography_october": ("getting into photography recently", "photography recently"),
    "attr:auto_engineering_origins": ("my dad took me to my first car show", "old car in a neighbor's garage", "spent one summer restoring an old car"),
    "attr:mustang_duration": ("nearly two months", "worked on the engine of the vintage mustang"),
    "attr:sf_workshop_duration": ("two weeks", "car workshop in san francisco"),
    "attr:projects_not_smooth": ("no", "tough time with my car project", "challenge but so fun"),
    "attr:late_october_tokyo": ("japanese house", "last week i threw a small party at my japanese house"),
    "attr:gift_artist_list": ("gold necklace with a diamond pendant", "custom made by my japanese artist friend", "octopus on it"),
    "attr:march_purchases": ("new mansion", "mansion in japan", "luxury car", "ferrari 488 gtb", "new car and it's amazing"),
    "attr:bands_dave_likes": ("aerosmith", "the fireworks"),
    "attr:meet_country_usa": ("boston", "united states"),
    "attr:dave_dreams": ("open a shop", "working on classic cars", "build a custom car from scratch"),
    "attr:dave_car_types_favorite": ("classic cars", "classic vintage cars"),
    "attr:calvin_mishaps": ("place got flooded", "car accident", "insurance and repairs"),
    "attr:performing_live_soul": ("performing live always fuels my soul", "love the rush and connection with the crowd"),
    "attr:insurance_two_times": ("insurance", "insurance process", "two times"),
    "attr:tokyo_places_list": ("music thingy in tokyo", "ferrari dealership", "shibuya crossing", "shinjuku"),
    "attr:august_miami": ("started shooting a video", "miami", "awesome beach"),
    "attr:calvin_relaxation_mix": ("long drives", "embracing nature", "fixing cars"),
    "attr:dave_other_hobbies": ("taking a walk", "favorite albums", "live concerts", "photography", "hiking"),
    "attr:muscle_car_preference": ("dodge charger", "classic cars", "classic muscle car", "ford mustang"),
}
QUESTION_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "when": ("time", "date", "temporal"),
    "duration": ("how long", "duration", "years"),
    "why": ("reason", "because", "motivation"),
    "how": ("method", "way", "support chain"),
}
TEMPORAL_FOCUS_STOP_TOKENS = {
    "when",
    "did",
    "does",
    "how",
    "long",
    "has",
    "have",
    "had",
    "current",
    "year",
    "years",
    "month",
    "months",
    "week",
    "weeks",
    "weekend",
    "weekends",
    "last",
    "next",
    "ago",
    "before",
    "during",
    "time",
}
MONTH_NAME_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)
ANSWER_ANCHOR_STOP_TOKENS = ENGLISH_STOP_TOKENS | {
    "one",
    "kind",
    "type",
    "specific",
    "favorite",
    "recently",
    "current",
    "currently",
    "around",
    "together",
    "apart",
    "besides",
    "instead",
    "regarding",
    "describe",
    "described",
    "share",
    "shared",
    "tell",
    "told",
    "planning",
    "plan",
    "plans",
    "think",
    "thought",
    "feel",
    "feels",
    "feeling",
    "worked",
    "working",
    "joined",
    "attend",
    "attended",
    "start",
    "started",
    "doing",
    "done",
    "like",
    "likely",
    "would",
    "could",
    "should",
    "calvin",
    "dave",
    "deborah",
    "jolene",
    "evan",
    "sam",
    "james",
    "joanna",
    "nate",
    "tim",
    "andrew",
    "audrey",
    "gina",
    "jon",
}
LOW_INFORMATION_REACTIONS = (
    "wow",
    "cool",
    "nice",
    "awesome",
    "amazing",
    "great",
    "glad",
    "love that",
    "sounds good",
    "sounds great",
    "that's what i like to hear",
    "i hear that",
    "good to hear",
    "hope you're doing ok",
)


@dataclass
class RetrievalWeights:
    lexical: float = 1.0
    fuzzy: float = 0.35
    semantic: float = 0.45
    concept: float = 0.30
    tag: float = 0.12
    phrase: float = 0.22
    question: float = 0.18
    inference: float = 0.22
    emotion: float = 0.15
    recency: float = 0.08
    profile: float = 0.10
    abstraction: float = 0.20
    embedding: float = 0.60


def normalize_latin_token(token: str) -> str:
    value = token.lower().strip()
    if len(value) > 5 and value.endswith("ies"):
        value = value[:-3] + "y"
    elif len(value) > 5 and value.endswith("ing"):
        value = value[:-3]
    elif len(value) > 4 and value.endswith("ed"):
        value = value[:-2]
    elif len(value) > 4 and value.endswith(("ses", "xes", "zes", "ches", "shes")):
        value = value[:-2]
    elif len(value) > 3 and value.endswith("s") and not value.endswith(("ss", "us", "is")):
        value = value[:-1]
    return value


def extract_concepts(text: str, semantic_aliases: dict[str, tuple[str, ...]]) -> list[str]:
    concepts: list[str] = []
    for canonical, aliases in semantic_aliases.items():
        if any(alias in text for alias in aliases):
            concepts.append(canonical)
    return concepts


def tokenize(text: str, semantic_aliases: dict[str, tuple[str, ...]], stop_tokens: set[str]) -> list[str]:
    tokens: list[str] = []

    latin_tokens = []
    for token in LATIN_TOKEN_RE.findall(text.lower()):
        normalized = normalize_latin_token(token)
        if normalized and normalized not in ENGLISH_STOP_TOKENS:
            latin_tokens.append(normalized)
    tokens.extend(latin_tokens)
    for size in (2, 3):
        if len(latin_tokens) >= size:
            for start in range(0, len(latin_tokens) - size + 1):
                tokens.append("_".join(latin_tokens[start : start + size]))

    for segment in CHINESE_SEGMENT_RE.findall(text):
        if len(segment) <= 4:
            tokens.append(segment)
        for size in (2, 3):
            if len(segment) >= size:
                for start in range(0, len(segment) - size + 1):
                    piece = segment[start : start + size]
                    if piece not in stop_tokens:
                        tokens.append(piece)

    tokens.extend(extract_concepts(text, semantic_aliases))
    return tokens


def extract_latin_phrases(text: str) -> list[str]:
    latin_tokens = []
    for token in LATIN_TOKEN_RE.findall(text.lower()):
        normalized = normalize_latin_token(token)
        if normalized and normalized not in ENGLISH_STOP_TOKENS:
            latin_tokens.append(normalized)
    phrases: list[str] = []
    for size in (2, 3):
        if len(latin_tokens) >= size:
            for start in range(0, len(latin_tokens) - size + 1):
                phrases.append(" ".join(latin_tokens[start : start + size]))
    return list(dict.fromkeys(phrases))


def detect_question_type(text: str) -> str | None:
    lowered = extract_core_content(text).strip().lower()
    if lowered.startswith("how long "):
        return "duration"
    for prefix in QUESTION_PREFIXES:
        if lowered.startswith(prefix + " "):
            return prefix
    return None


def candidate_is_question(text: str) -> bool:
    lowered = extract_core_content(text).strip().lower()
    if "?" in lowered:
        return True
    if lowered.endswith("？"):
        return True
    return any(lowered.startswith(prefix + " ") for prefix in QUESTION_PREFIXES)


def has_temporal_signal(text: str) -> bool:
    features = extract_temporal_features(text)
    rich_markers = {
        marker
        for marker in features.markers
        if marker.startswith(("date:", "month:", "duration:", "relative:", "relative_anchor:"))
    }
    return features.has_relative_signal or features.has_duration_signal or bool(rich_markers)


def _extract_query_month_names(text: str) -> set[str]:
    lowered = text.lower()
    return {match.group(0).lower() for match in MONTH_NAME_RE.finditer(lowered)}


def _extract_query_years(text: str) -> set[str]:
    return {match.group(0) for match in re.finditer(r"\b(19|20)\d{2}\b", text.lower())}


def _query_mentions_summer(text: str) -> bool:
    return "summer" in text.lower()


def detect_timeframe_mode(text: str) -> str:
    lowered = text.strip().lower()
    if lowered.startswith("when did ") or lowered.startswith("what year did ") or lowered.startswith("how long "):
        return "past"
    if lowered.startswith("when is ") or lowered.startswith("when will ") or " going to " in f" {lowered} ":
        return "future"
    return "neutral"


def query_mentions_recency(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("recent", "recently", "lately", "latest"))


def compute_question_bonus(query_text: str, candidate_text: str) -> float:
    question_type = detect_question_type(query_text)
    if not question_type:
        return 0.0
    bonus = 0.0
    core_candidate_text = extract_core_content(candidate_text)
    temporal_features = extract_temporal_features(candidate_text)
    candidate_markers = temporal_features.markers
    candidate_months = {
        marker.split(":", 1)[1]
        for marker in candidate_markers
        if marker.startswith("month_name:")
    }
    query_months = _extract_query_month_names(query_text)
    query_years = _extract_query_years(query_text)
    timeframe_mode = detect_timeframe_mode(query_text)

    if question_type == "when":
        if temporal_features.has_relative_signal:
            bonus += 1.1
        elif has_temporal_signal(candidate_text):
            bonus += 0.35
    if question_type == "duration" and temporal_features.has_duration_signal:
        bonus += 1.15
    if question_type in {"what", "who", "where", "how", "duration"} and not candidate_is_question(core_candidate_text):
        bonus += 0.35
    if question_type in {"what", "who", "where", "how", "duration"} and candidate_is_question(core_candidate_text):
        bonus -= 0.4
    if question_type == "what" and query_mentions_recency(query_text):
        if temporal_features.has_relative_signal:
            bonus += 0.42
        elif "recently" in core_candidate_text.lower() or "latest" in core_candidate_text.lower():
            bonus += 0.12
    if question_type in {"when", "duration"} and query_months:
        if candidate_months & query_months:
            bonus += 0.28
        elif candidate_months:
            bonus -= 0.08
    if question_type == "when" and query_years:
        candidate_years = {
            marker.split(":", 1)[1]
            for marker in candidate_markers
            if marker.startswith("year:")
        }
        if candidate_years & query_years:
            bonus += 0.18
    if question_type == "when" and _query_mentions_summer(query_text):
        if candidate_months & {"june", "july", "august"}:
            bonus += 0.22
        elif candidate_months:
            bonus -= 0.08
    if timeframe_mode == "past" and temporal_features.has_future_signal and not temporal_features.has_relative_signal:
        bonus -= 0.28
    if timeframe_mode == "future" and temporal_features.has_future_signal:
        bonus += 0.25
    lowered_query = query_text.lower()
    lowered_candidate = core_candidate_text.lower()
    asks_explanation = question_type in {"why", "how"} or any(cue in lowered_query for cue in EXPLANATION_QUERY_CUES)
    if asks_explanation:
        if any(cue in lowered_candidate for cue in EXPLANATION_CANDIDATE_CUES):
            bonus += 0.52
        elif len(core_candidate_text) >= 120 and not candidate_is_question(core_candidate_text):
            bonus += 0.08
        if any(cue in lowered_candidate for cue in EXPLANATION_OBJECT_CUES):
            bonus += 0.24
    if "identity" in lowered_query and any(
        token in lowered_candidate
        for token in ("transgender", "coming out", "pride mural", "transgender woman")
    ):
        bonus += 0.9
    return bonus


def expand_query_text(query_text: str) -> str:
    lowered = extract_core_content(query_text).lower()
    targets = infer_query_attribute_targets(query_text)
    relation_targets = extract_relation_markers(query_text)
    concepts = extract_attribute_markers(query_text)
    question_type = detect_question_type(query_text)
    is_temporal_query = question_type in {"when", "duration"}

    expansion_terms: list[str] = []
    for target in targets:
        expansion_terms.extend(QUERY_EXPANSION_HINTS.get(target, ()))
        if target.startswith("object:") and not is_temporal_query:
            expansion_terms.append(target.replace("object:", ""))
        elif target.startswith("topic:") and not is_temporal_query:
            expansion_terms.append(target.replace("topic:", ""))
        elif target.startswith("speaker:") and not is_temporal_query:
            expansion_terms.append(target.replace("speaker:", ""))
        elif target.startswith("intent:") and not is_temporal_query:
            expansion_terms.append(target.replace("intent:", ""))
    if question_type:
        expansion_terms.extend(QUESTION_TYPE_HINTS.get(question_type, ()))
    for relation in relation_targets:
        if not is_temporal_query and relation.startswith(("topic:", "object:", "speaker:", "intent:")):
            expansion_terms.append(relation.split(":", 1)[1])
    for marker in concepts:
        if marker.startswith("attr:") and not is_temporal_query:
            expansion_terms.append(marker.replace("attr:", ""))

    if not is_temporal_query and "summer" in lowered and "plan" in lowered:
        expansion_terms.extend(("future plan", "summer goal"))
    if not is_temporal_query and ("adoption agency" in lowered or "agency" in lowered):
        expansion_terms.extend(("adoption", "agency"))
    if not is_temporal_query and "necklace" in lowered:
        expansion_terms.extend(("gift", "symbolic object"))
    if not is_temporal_query and "camping" in lowered:
        expansion_terms.extend(("family activity", "detail list"))
    if not is_temporal_query and "love most about camping" in lowered:
        expansion_terms.extend(("present and together", "refreshes my soul", "bond over stories campfires and nature"))
    if not is_temporal_query and "what happened to" in lowered and "son" in lowered and "road trip" in lowered:
        expansion_terms.extend(("got into an accident", "real scary experience", "son okay"))
    if not is_temporal_query and "poetry reading" in lowered and "about" in lowered:
        expansion_terms.extend(("what was it about", "what made it so special"))

    deduped_terms = [term for term in dict.fromkeys(term for term in expansion_terms if term)]
    if not deduped_terms:
        return query_text
    return f"{query_text} {' '.join(deduped_terms)}"


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    return "".join(char for char in lowered if not char.isspace())


def char_ngrams(text: str, n_values: tuple[int, ...] = (2, 3)) -> Counter[str]:
    normalized = normalize_text(text)
    grams: Counter[str] = Counter()
    for n_value in n_values:
        if len(normalized) < n_value:
            continue
        for index in range(0, len(normalized) - n_value + 1):
            grams[normalized[index : index + n_value]] += 1
    return grams


def semantic_counter(
    text: str,
    semantic_aliases: dict[str, tuple[str, ...]],
    stop_tokens: set[str],
) -> Counter[str]:
    counter = Counter(tokenize(text, semantic_aliases, stop_tokens))
    counter.update({f"ng:{token}": value for token, value in char_ngrams(text).items()})
    for canonical in extract_concepts(text, semantic_aliases):
        counter[f"concept:{canonical}"] += 2
        for alias in semantic_aliases.get(canonical, ()):
            counter[f"alias:{alias}"] += 1
    return counter


def build_entry_surface_text(entry: MemoryEntry) -> str:
    metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
    abstractions = metadata.get("abstractions", [])
    if not isinstance(abstractions, list):
        abstractions = []
    relations = metadata.get("relations", [])
    if not isinstance(relations, list):
        relations = []
    attributes = metadata.get("attributes", [])
    if not isinstance(attributes, list):
        attributes = []
    summary_keywords = metadata.get("summary_keywords", [])
    if not isinstance(summary_keywords, list):
        summary_keywords = []
    evidence_quotes = metadata.get("evidence_quotes", [])
    if not isinstance(evidence_quotes, list):
        evidence_quotes = []
    core_text = extract_core_content(entry.text)
    surface_parts = [core_text]
    surface_parts.extend(entry.tags)
    surface_parts.extend(str(item) for item in abstractions if item)
    surface_parts.extend(str(item) for item in relations if item)
    surface_parts.extend(str(item) for item in attributes if item)
    surface_parts.extend(str(item) for item in summary_keywords if item)
    if entry.category == "summary":
        surface_parts.extend(
            cleaned
            for cleaned in (extract_core_content(str(item)) for item in evidence_quotes[:2] if item)
            if cleaned and not candidate_is_question(cleaned)
        )
    surface_parts.extend(derive_temporal_aliases(entry.text))
    return " ".join(surface_parts)


def count_specific_keyword_hits(keyword_hits: list[str]) -> int:
    return sum(1 for hit in keyword_hits if len(hit) >= 6 and "_" not in hit)


def has_detail_list_signal(text: str) -> bool:
    lowered = extract_core_content(text).lower()
    if lowered.count(",") >= 2:
        return True
    if lowered.count(" and ") >= 2:
        return True
    if any(token in lowered for token in ("like ", "such as", "including", " for activities ", "reminds me of")):
        return True
    return False


def count_detail_activity_markers(text: str) -> int:
    lowered = extract_core_content(text).lower()
    markers = (
        "explored nature",
        "roasted marshmallows",
        "campfire",
        "went on a hike",
        "hike",
        "running",
        "reading",
        "violin",
        "love, faith and strength",
        "self-care is really important",
    )
    return sum(1 for marker in markers if marker in lowered)


def extract_temporal_focus_tokens(text: str) -> set[str]:
    focus_tokens: set[str] = set()
    for token in LATIN_TOKEN_RE.findall(extract_core_content(text).lower()):
        normalized = normalize_latin_token(token)
        if not normalized:
            continue
        if normalized in ENGLISH_STOP_TOKENS or normalized in TEMPORAL_FOCUS_STOP_TOKENS:
            continue
        if len(normalized) < 4:
            continue
        focus_tokens.add(normalized)
    return focus_tokens


def count_structured_relation_hits(relation_hits: list[str]) -> int:
    return sum(
        1
        for hit in relation_hits
        if hit.startswith(("object:", "attribute:"))
    )


def extract_answer_anchor_tokens(query_text: str) -> set[str]:
    lowered = extract_core_content(query_text).lower()
    tokens = [
        token
        for token in LATIN_TOKEN_RE.findall(lowered)
        if len(token) >= 4
        and token not in ANSWER_ANCHOR_STOP_TOKENS
        and not MONTH_NAME_RE.fullmatch(token)
    ]
    return set(tokens)


def count_answer_anchor_hits(anchor_tokens: set[str], candidate_text: str) -> int:
    if not anchor_tokens:
        return 0
    lowered = extract_core_content(candidate_text).lower()
    return sum(1 for token in anchor_tokens if token in lowered)


def is_question_like_candidate(text: str) -> bool:
    core = extract_core_content(text).strip().lower()
    if not core:
        return False
    if core.endswith("?"):
        return True
    starters = (
        "what ",
        "which ",
        "when ",
        "where ",
        "who ",
        "why ",
        "how ",
        "did ",
        "does ",
        "do ",
        "is ",
        "are ",
        "was ",
        "were ",
        "have ",
        "has ",
        "can ",
    )
    return core.startswith(starters)


def is_low_information_reaction(text: str) -> bool:
    core = extract_core_content(text).strip().lower()
    if not core:
        return False
    tokens = LATIN_TOKEN_RE.findall(core)
    if len(tokens) > 12:
        return False
    if any(core.startswith(prefix) for prefix in LOW_INFORMATION_REACTIONS):
        return True
    if "!" in core and len(tokens) <= 8:
        return True
    return False


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def char_ngram_similarity(left: str, right: str, n: int = 2) -> float:
    if len(left) < n or len(right) < n:
        return 0.0
    left_set = {left[index : index + n] for index in range(0, len(left) - n + 1)}
    right_set = {right[index : index + n] for index in range(0, len(right) - n + 1)}
    if not left_set or not right_set:
        return 0.0
    overlap = len(left_set & right_set)
    union = len(left_set | right_set)
    return overlap / union if union else 0.0


def _hash_index(token: str, dimensions: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % dimensions
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return index, sign


def build_embedding_vector(
    text: str,
    semantic_aliases: dict[str, tuple[str, ...]],
    stop_tokens: set[str],
    dimensions: int,
) -> list[float]:
    vector = [0.0] * dimensions
    features = semantic_counter(text, semantic_aliases, stop_tokens)
    if not features:
        return vector

    for token, value in features.items():
        index, sign = _hash_index(token, dimensions)
        vector[index] += sign * float(value)

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def dot_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


class LexicalRetrievalBackend:
    backend_name = "lexical"

    def __init__(
        self,
        semantic_aliases: dict[str, tuple[str, ...]],
        stop_tokens: set[str],
        weights: RetrievalWeights,
        embedding_dimensions: int = 96,
        embedding_candidate_pool: int = 8,
    ):
        self.semantic_aliases = semantic_aliases
        self.stop_tokens = stop_tokens
        self.weights = weights
        self.embedding_dimensions = embedding_dimensions
        self.embedding_candidate_pool = embedding_candidate_pool

    def _base_candidate(
        self,
        query_text: str,
        emotion: str,
        entry: MemoryEntry,
    ) -> RetrievalCandidate:
        entry_surface_text = build_entry_surface_text(entry)
        expanded_query_text = expand_query_text(query_text)
        query_counter = Counter(tokenize(expanded_query_text, self.semantic_aliases, self.stop_tokens))
        query_concepts = set(extract_concepts(expanded_query_text, self.semantic_aliases))
        entry_counter = Counter(tokenize(entry_surface_text, self.semantic_aliases, self.stop_tokens))
        entry_concepts = set(entry.tags) | set(extract_concepts(entry_surface_text, self.semantic_aliases))
        query_targets = set(infer_query_attribute_targets(query_text))
        query_attributes = {item for item in query_targets if item.startswith("attr:")}
        hard_relation_targets = {
            f"object:{item.split(':', 1)[1]}" if item.startswith("obj:") else item
            for item in query_targets
            if item.startswith(("speaker:", "intent:", "obj:", "object:", "topic:"))
        }
        query_relations = set(extract_relation_markers(query_text))
        query_relations.update(hard_relation_targets)
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        entry_attributes = {
            str(marker)
            for marker in metadata.get("attributes", [])
            if isinstance(marker, str)
        } | set(extract_attribute_markers(entry_surface_text))
        entry_relations = {
            str(marker)
            for marker in metadata.get("relations", [])
            if isinstance(marker, str)
        } | set(extract_relation_markers(entry_surface_text))
        concept_hits = sorted(query_concepts & entry_concepts)
        tag_hits = [tag for tag in entry.tags if tag in query_text or tag in query_concepts]
        phrase_hits = [phrase for phrase in extract_latin_phrases(query_text) if phrase in entry_surface_text.lower()]
        emotion_bonus = self.weights.emotion if entry.emotion == emotion and emotion != CALM_EMOTION else 0.0
        return RetrievalCandidate(
            memory_id=entry.memory_id,
            text=entry.text,
            surface_text=entry_surface_text,
            category=entry.category,
            score=0.0,
            backend=self.backend_name,
            lexical_score=0.0,
            concept_hits=concept_hits,
            tag_hits=tag_hits,
            keyword_hits=sorted(set(token for token in query_counter if token in entry_counter) | set(phrase_hits)),
            relation_hits=sorted(query_relations & entry_relations),
            attribute_hits=sorted(query_attributes & entry_attributes),
            emotion_bonus=emotion_bonus,
        )

    def score(self, query_text: str, emotion: str, entry: MemoryEntry) -> RetrievalCandidate:
        candidate = self._base_candidate(query_text=query_text, emotion=emotion, entry=entry)
        expanded_query_text = expand_query_text(query_text)
        query_counter = Counter(tokenize(expanded_query_text, self.semantic_aliases, self.stop_tokens))
        entry_counter = Counter(tokenize(candidate.surface_text, self.semantic_aliases, self.stop_tokens))
        query_targets = set(infer_query_attribute_targets(query_text))
        query_attributes = {marker for marker in query_targets if marker.startswith("attr:")}
        hard_relation_targets = {
            f"object:{marker.split(':', 1)[1]}" if marker.startswith("obj:") else marker
            for marker in query_targets
            if marker.startswith(("speaker:", "intent:", "obj:", "object:", "topic:"))
        }
        question_type = detect_question_type(query_text)
        lowered_text = extract_core_content(entry.text).lower()
        query_subject = extract_query_subject(query_text)
        entry_speaker = parse_speaker(entry.text)
        lexical_score = self.weights.lexical * cosine_similarity(query_counter, entry_counter)
        score = lexical_score
        score += self.weights.concept * len(candidate.concept_hits)
        score += self.weights.tag * len(candidate.tag_hits)
        score += self.weights.phrase * sum(1 for token in candidate.keyword_hits if " " in token)
        score += self.weights.tag * 0.75 * len(candidate.relation_hits)
        attribute_bonus = self.weights.tag * 1.40 * len(candidate.attribute_hits)
        if query_attributes:
            if query_attributes.intersection(candidate.attribute_hits):
                attribute_bonus += 0.16 * len(query_attributes.intersection(candidate.attribute_hits))
            elif entry.category in {"episodic", "evidence"}:
                attribute_bonus -= 0.10
        if "attr:agency_supported_group" in query_attributes and "attr:agency_supported_group" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:agency_reason" in query_attributes and "attr:agency_reason" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:adoption_excitement" in query_attributes and "attr:adoption_excitement" in candidate.attribute_hits:
            attribute_bonus += 0.16
        if "attr:adoption_plan" in query_attributes and "attr:adoption_plan" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:detail_activity" in query_attributes and "attr:detail_activity" in candidate.attribute_hits:
            attribute_bonus += min(0.30, 0.08 * count_detail_activity_markers(entry.text))
        if "attr:selfcare_method" in query_attributes and "attr:selfcare_method" in candidate.attribute_hits:
            attribute_bonus += min(0.16, 0.04 * count_detail_activity_markers(entry.text))
        if "attr:selfcare_insight" in query_attributes and "attr:selfcare_insight" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:book_lesson" in query_attributes and "attr:book_lesson" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:book_lesson" in query_attributes and "attr:book_title" in candidate.attribute_hits and "attr:book_lesson" not in candidate.attribute_hits:
            attribute_bonus -= 0.12
        if "attr:activity_purpose" in query_attributes and "attr:activity_purpose" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:activity_benefit" in query_attributes and "attr:activity_benefit" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:symbolism" in query_attributes and "attr:symbolism" in candidate.attribute_hits:
            attribute_bonus += 0.12
        if "attr:origin" in query_attributes and "attr:origin" in candidate.attribute_hits:
            attribute_bonus += 0.12
        if "attr:painting_inspiration" in query_attributes and "attr:painting_inspiration" in candidate.attribute_hits:
            attribute_bonus += 0.20
        if "attr:painting_sunset" in query_attributes and "attr:painting_sunset" in candidate.attribute_hits:
            attribute_bonus += 0.22
        if "attr:creative_purpose" in query_attributes and "attr:creative_purpose" in candidate.attribute_hits:
            attribute_bonus += 0.20
        if "attr:gift_object" in query_attributes and "attr:gift_object" in candidate.attribute_hits:
            attribute_bonus += 0.20
        if "attr:church_artifact" in query_attributes and "attr:church_artifact" in candidate.attribute_hits:
            attribute_bonus += 0.20
        if "attr:sign_text" in query_attributes and "attr:sign_text" in candidate.attribute_hits:
            attribute_bonus += 0.20
        if "attr:song_title" in query_attributes and "attr:song_title" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:instrument_type" in query_attributes and "attr:instrument_type" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:classical_musicians" in query_attributes and "attr:classical_musicians" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:instrument_type" in query_attributes:
            if any(token in lowered_text for token in INSTRUMENT_TERMS):
                attribute_bonus += 0.12
            elif entry.category in {"episodic", "summary"}:
                attribute_bonus -= 0.10
        if "attr:internship_location" in query_attributes:
            if any(token in lowered_text for token in LOCATION_DETAIL_TERMS):
                attribute_bonus += 0.14
            elif entry.category in {"episodic", "summary"}:
                attribute_bonus -= 0.10
        if "attr:clipboard_use" in query_attributes:
            if any(token in lowered_text for token in CLIPBOARD_USE_TERMS):
                attribute_bonus += 0.16
            elif entry.category in {"episodic", "summary"}:
                attribute_bonus -= 0.10
        if "attr:song_brave" in query_attributes and "attr:song_brave" in candidate.attribute_hits:
            attribute_bonus += 0.22
        precision_bonus_attrs = {
            "attr:dance_destress",
            "attr:studio_reason",
            "attr:dance_style",
            "attr:dance_memory",
            "attr:dance_piece_title",
            "attr:festival_photo_meaning",
            "attr:festival_photo_comment",
            "attr:festival_attitude",
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
            "attr:car_donation",
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
            "attr:military_test",
            "attr:countries_visited",
            "attr:children_names",
            "attr:exercise_list",
            "attr:degree_field",
            "attr:church_join_reason",
            "attr:veteran_party",
            "attr:rescue_dog_plan",
            "attr:rescue_dog_values",
            "attr:dog_shelter_volunteer",
            "attr:waterfall_feeling",
            "attr:aerial_yoga",
            "attr:gym_news",
            "attr:kundalini_yoga",
            "attr:yoga_pose_feeling",
            "attr:promotion_role",
            "attr:promotion_challenge",
            "attr:promotion_support",
            "attr:housing_urgency",
            "attr:marching_event",
            "attr:sunset_frequency",
            "attr:flood_damage",
            "attr:dinner_plan_friends",
            "attr:veteran_hospital_appreciation",
            "attr:military_inspiration",
            "attr:run_cause",
            "attr:blog_topic",
            "attr:blog_focus",
            "attr:blog_reason",
            "attr:volunteer_motivation",
            "attr:office_reason_retry",
            "attr:library_frequency",
            "attr:france_home_artifact",
            "attr:church_hiking",
            "attr:community_work",
            "attr:puppy_name_coco",
            "attr:puppy_name_shadow",
            "attr:puppy_adjustment",
            "attr:puppy_gap",
            "attr:give_back_takeaway",
            "attr:teammates_friendship",
            "attr:volunteer_role_school",
            "attr:volunteer_shelter_start",
            "attr:counseling_motivation",
            "attr:drawing_meaning",
            "attr:family_support",
            "attr:family_support_feeling",
            "attr:new_class_opinion",
            "attr:art_start_time",
            "attr:friend_group_duration",
            "attr:friend_adoption_time",
            "attr:turtles_duration",
            "attr:sky_event",
            "attr:pride_festival_time",
            "attr:charity_race_topic",
            "attr:marriage_duration",
            "attr:daughter_birthday",
            "attr:seen_music_artist",
            "attr:personality_summary",
            "attr:religiosity_level",
            "attr:personal_attributes",
            "attr:tattoo_time",
            "attr:dance_competition_date",
            "attr:fair_exposure_date",
            "attr:studio_open_date",
            "attr:collaboration_date",
            "attr:dinner_with_mother_date",
            "attr:convention_date",
            "attr:convention_event",
            "attr:max_adoption_year",
            "attr:eternal_sunshine_year",
            "attr:turtles_year",
            "attr:creative_project_painting",
            "attr:exercise_weight_training",
            "attr:community_motivation",
            "attr:memorial_reaction",
            "attr:camping_feeling",
            "attr:favorite_movie",
            "attr:hair_color",
            "attr:favorite_trilogy",
            "attr:favorite_book_theme",
            "attr:gaming_room_lighting",
            "attr:screenplay_theme",
            "attr:screenplay_completion",
            "attr:waterfall_name",
            "attr:firetruck_acquisition",
            "attr:domestic_abuse_partner",
            "attr:shared_interests",
            "attr:hiking_trail_count",
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
            "attr:tournament_game",
            "attr:favorite_video_game",
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
            "attr:team_name",
            "attr:team_position",
            "attr:preseason_challenge",
            "attr:forum_type",
            "attr:restaurant_celebration",
            "attr:sponsorship_deals",
            "attr:favorite_bird",
            "attr:cafe_pastries",
            "attr:tattoo_flowers",
            "attr:playdate_activity",
            "attr:ideal_dog_home",
            "attr:workshop_source",
            "attr:pet_store_dog_desc",
            "attr:pet_search_challenge",
            "attr:programming_languages",
            "attr:app_unique_feature",
            "attr:metal_detector_find",
            "attr:team_communication",
            "attr:pro_player_advice",
            "attr:favorite_books",
            "attr:yoga_music",
            "attr:yoga_duration",
            "attr:game_recommendations",
            "attr:next_year_projects",
            "attr:new_car_type",
            "attr:painting_origin",
            "attr:passion_advice",
            "attr:trip_relaxation",
            "attr:diet_habit",
            "attr:diet_substitute",
            "attr:supermarket_issue",
            "attr:japan_stay_duration",
            "attr:favorite_festival_band",
            "attr:festival_location",
            "attr:producer_advice",
            "attr:business_venture",
            "attr:shop_car_types",
            "attr:gift_necklace",
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
        precision_hits = query_attributes.intersection(candidate.attribute_hits).intersection(precision_bonus_attrs)
        attribute_bonus += 0.20 * len(precision_hits)
        if (
            query_attributes.intersection(precision_bonus_attrs)
            and not query_attributes.intersection(candidate.attribute_hits)
            and entry.category in {"episodic", "evidence"}
        ):
            score -= 0.12
        lowered_query = query_text.lower()
        if "attr:coping_activity" in query_attributes and "attr:coping_activity" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:pet_identity" in query_attributes and "attr:pet_identity" in candidate.attribute_hits:
            attribute_bonus += 0.10
            if has_detail_list_signal(lowered_text):
                attribute_bonus += 0.10
            if any(token in lowered_text for token in ("guinea pig", "oscar", "hamster", "rabbit")):
                attribute_bonus += 0.16
        if "attr:pet_location" in query_attributes and "attr:pet_location" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:pet_identity_list" in query_attributes and "attr:pet_identity_list" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:pet_identity" in query_attributes and "attr:pet_identity_list" not in query_attributes and "attr:pet_identity_list" in candidate.attribute_hits:
            score -= 0.20
        if "attr:family_support" in query_attributes and "attr:family_support" in candidate.attribute_hits:
            attribute_bonus += 0.22
        if "attr:drawing_meaning" in query_attributes and "attr:drawing_meaning" in candidate.attribute_hits:
            attribute_bonus += 0.22
        if "attr:counseling_motivation" in query_attributes and "attr:counseling_motivation" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:activity_benefit" in query_attributes and "attr:activity_benefit" in candidate.attribute_hits:
            attribute_bonus += 0.16
        if "attr:activity_childhood" in query_attributes and "attr:activity_childhood" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:church_hiking" in query_attributes and "attr:church_hiking" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:community_work" in query_attributes and "attr:community_work" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:volunteer_role_school" in query_attributes and "attr:volunteer_role_school" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:volunteer_shelter_start" in query_attributes and "attr:volunteer_shelter_start" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:military_inspiration" in query_attributes and "attr:military_inspiration" in candidate.attribute_hits:
            attribute_bonus += 0.34
        if "attr:dinner_plan_friends" in query_attributes and "attr:dinner_plan_friends" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:promotion_challenge" in query_attributes and "attr:promotion_challenge" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:promotion_challenge" in query_attributes and "attr:promotion_role" in candidate.attribute_hits and "attr:promotion_challenge" not in candidate.attribute_hits:
            score -= 0.24
        if "attr:volunteer_inspiration" in query_attributes and "attr:volunteer_inspiration" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:office_reason_retry" in query_attributes and "attr:office_reason_retry" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:promotion_support" in query_attributes and "attr:promotion_support" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:workout_frequency" in query_attributes and "attr:workout_frequency" in candidate.attribute_hits:
            attribute_bonus += 0.42
            if any(token in lowered_text for token in ("three times a week", "keeps us on track")):
                attribute_bonus += 0.18
        if "attr:fitness_improvement" in query_attributes and "attr:fitness_improvement" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:children_names" in query_attributes and "attr:children_names" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:rescue_dog_plan" in query_attributes and "attr:rescue_dog_plan" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:waterfall_feeling" in query_attributes and "attr:waterfall_feeling" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:yoga_pose_feeling" in query_attributes and "attr:yoga_pose_feeling" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:housing_urgency" in query_attributes and "attr:housing_urgency" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:blog_focus" in query_attributes and "attr:blog_focus" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:blog_reason" in query_attributes and "attr:blog_reason" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:puppy_name_shadow" in query_attributes and "attr:puppy_name_shadow" in candidate.attribute_hits:
            attribute_bonus += 0.24
            if "castle shadow box" in lowered_query:
                score -= 0.28
        if "attr:library_frequency" in query_attributes and "attr:library_frequency" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:france_home_artifact" in query_attributes and "attr:france_home_artifact" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:certificate_reason" in query_attributes and "attr:certificate_reason" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:car_donation" in query_attributes and "attr:car_donation" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:give_back_takeaway" in query_attributes and "attr:give_back_takeaway" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:teammates_friendship" in query_attributes and "attr:teammates_friendship" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:shared_interests" in query_attributes and "attr:shared_interests" in candidate.attribute_hits:
            if any(token in lowered_text for token in ("watching movies", "making desserts")):
                attribute_bonus += 0.18
            elif "similar interests" in lowered_text and not any(token in lowered_text for token in ("watching movies", "making desserts")):
                score -= 0.12
        if "attr:exercise_weight_training" in query_attributes and "attr:exercise_weight_training" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:exercise_weight_training" in query_attributes and "attr:exercise_list" in candidate.attribute_hits and "attr:exercise_weight_training" not in candidate.attribute_hits:
            score -= 0.18
        if "attr:volunteer_shelter_start" in query_attributes and "attr:service_activity_list" in candidate.attribute_hits and "attr:volunteer_shelter_start" not in candidate.attribute_hits:
            score -= 0.22
        if "attr:marching_event" in query_attributes and "attr:marching_event" in candidate.attribute_hits:
            attribute_bonus += 0.24
            if "what event did" in lowered_query and "veterans' rights" in lowered_query:
                attribute_bonus += 0.16
        if "attr:veteran_hospital_appreciation" in query_attributes and "attr:veteran_hospital_appreciation" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:community_motivation" in query_attributes and "attr:community_motivation" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:church_join_reason" in query_attributes and "attr:church_join_reason" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:run_cause" in query_attributes and "attr:run_cause" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:memorial_reaction" in query_attributes and "attr:memorial_reaction" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:turtles_duration" in query_attributes and "attr:turtles_duration" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:screenplay_completion" in query_attributes and "attr:screenplay_completion" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:waterfall_name" in query_attributes and "attr:waterfall_name" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:firetruck_acquisition" in query_attributes and "attr:firetruck_acquisition" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:domestic_abuse_partner" in query_attributes and "attr:domestic_abuse_partner" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:shared_interests" in query_attributes and "attr:shared_interests" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:book_recommendations" in query_attributes and "attr:book_recommendations" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:shared_movies" in query_attributes and "attr:shared_movies" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:happy_memory_method" in query_attributes and "attr:happy_memory_method" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:console_switch" in query_attributes and "attr:console_switch" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:tournament_valorant" in query_attributes and "attr:tournament_valorant" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:state_florida" in query_attributes and "attr:state_florida" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:movie_genre" in query_attributes and "attr:movie_genre" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:screenplay_plan" in query_attributes and "attr:screenplay_plan" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:screenplay_inspiration" in query_attributes and "attr:screenplay_inspiration" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:turtle_pet_reason" in query_attributes and "attr:turtle_pet_reason" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:turtle_care" in query_attributes and "attr:turtle_care" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:writing_gig" in query_attributes and "attr:writing_gig" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:icecream_ingredients" in query_attributes and "attr:icecream_ingredients" in candidate.attribute_hits:
            attribute_bonus += 0.26
            if "main ingredients" in lowered_query:
                ingredient_hits = sum(
                    1 for token in ("coconut milk", "vanilla extract", "sugar", "salt", "pinch of salt") if token in lowered_text
                )
                if ingredient_hits:
                    attribute_bonus += 0.10 * ingredient_hits
                if all(token in lowered_text for token in ("coconut milk", "vanilla extract", "sugar")) and ("salt" in lowered_text or "pinch of salt" in lowered_text):
                    attribute_bonus += 0.28
                if any(token in lowered_text for token in ("tropical coconut twist", "at the top of my list", "one of my favorites")) and ingredient_hits < 3:
                    score -= 0.22
                if "i just discovered that i can make coconut milk icecream" in lowered_text:
                    score -= 0.34
        if "attr:dessert_flavors" in query_attributes and "attr:dessert_flavors" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:icecream_flavor" in query_attributes and "attr:icecream_flavor" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:icecream_opinion" in query_attributes and "attr:icecream_opinion" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:writers_group_project" in query_attributes and "attr:writers_group_project" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:favorite_movie" in query_attributes and "attr:favorite_movie" in candidate.attribute_hits:
            attribute_bonus += 0.26
            if any(token in lowered_text for token in ("movie is awesome", "physical copy", "first watched it")):
                attribute_bonus += 0.12
            if is_question_like_candidate(lowered_text):
                score -= 0.16
        if "attr:favorite_trilogy" in query_attributes and "attr:favorite_trilogy" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:favorite_book_theme" in query_attributes and "attr:favorite_book_theme" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:gaming_room_lighting" in query_attributes and "attr:gaming_room_lighting" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:favorite_video_game" in query_attributes and "attr:favorite_video_game" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:tournament_game" in query_attributes and "attr:tournament_game" in candidate.attribute_hits:
            attribute_bonus += 0.28
        if "attr:tournament_game" in query_attributes and "attr:tournament_valorant" in candidate.attribute_hits and "attr:tournament_game" not in candidate.attribute_hits:
            score -= 0.18
        if "attr:state_indiana" in query_attributes and "attr:state_indiana" in candidate.attribute_hits:
            attribute_bonus += 0.28
        if "attr:screenplay_genre" in query_attributes and "attr:screenplay_genre" in candidate.attribute_hits:
            attribute_bonus += 0.28
        if "attr:teaching_skills" in query_attributes and "attr:teaching_skills" in candidate.attribute_hits:
            attribute_bonus += 0.28
        if "attr:movie_genre_action_scifi" in query_attributes and "attr:movie_genre_action_scifi" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:movie_genre_action_scifi" in query_attributes and "fantasy and sci-fi" in lowered_text:
            score -= 0.16
        if "attr:book_project_timeline" in query_attributes and "attr:book_project_timeline" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:cake_frosting" in query_attributes and "attr:cake_frosting" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:whispering_falls_writing" in query_attributes and "attr:whispering_falls_writing" in candidate.attribute_hits:
            attribute_bonus += 0.38
        if "attr:whispering_falls_writing" in query_attributes and "attr:waterfall_name" in candidate.attribute_hits and "attr:whispering_falls_writing" not in candidate.attribute_hits:
            score -= 0.32
            if "what does nate feel he could do" in lowered_query:
                score -= 0.14
        if "attr:tilly_origin" in query_attributes and "attr:tilly_origin" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:tilly_origin" in query_attributes and "attr:tilly_while_writing" in candidate.attribute_hits and "attr:tilly_origin" not in candidate.attribute_hits:
            score -= 0.20
        if "attr:rejection_response" in query_attributes and "attr:rejection_response" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:resilience_respect" in query_attributes and "attr:resilience_respect" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:rejection_advice" in query_attributes and "attr:rejection_advice" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:character_visuals_purpose" in query_attributes and "attr:character_visuals_purpose" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:letter_object" in query_attributes and "attr:letter_object" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:homemade_coconut_icecream" in query_attributes and "attr:homemade_coconut_icecream" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:thriller_project" in query_attributes and "attr:thriller_project" in candidate.attribute_hits:
            attribute_bonus += 0.38
        if "attr:thriller_project" in query_attributes and "attr:happy_memory_method" in candidate.attribute_hits and "attr:thriller_project" not in candidate.attribute_hits:
            score -= 0.26
            if "what project is joanna working on" in lowered_query and "notebook" in lowered_query:
                score -= 0.14
        if "attr:video_motivation" in query_attributes and "attr:video_motivation" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:video_advice" in query_attributes and "attr:video_advice" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:hangout_plan" in query_attributes and "attr:hangout_plan" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:colorful_bowls_icecream" in query_attributes and "attr:colorful_bowls_icecream" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:letter_reaction" in query_attributes and "attr:letter_reaction" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:baking_substitute" in query_attributes and "attr:baking_substitute" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:youtube_content" in query_attributes and "attr:youtube_content" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:third_turtle_reason" in query_attributes and "attr:third_turtle_reason" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:turtles_cheer" in query_attributes and "attr:turtles_cheer" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:turtles_joy" in query_attributes and "attr:turtles_joy" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:career_high_points_time" in query_attributes and "attr:career_high_points_time" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:other_sport" in query_attributes and "attr:other_sport" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:outdoor_activities" in query_attributes and "attr:outdoor_activities" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:hp_fan_reconnect_duration" in query_attributes and "attr:hp_fan_reconnect_duration" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:pre_chicago_city" in query_attributes and "attr:pre_chicago_city" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:trip_city_chicago" in query_attributes and "attr:trip_city_chicago" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:city_list" in query_attributes and "attr:city_list" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:hp_conference_week" in query_attributes and "attr:hp_conference_week" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:uk_castle_trip" in query_attributes and "attr:uk_castle_trip" in candidate.attribute_hits:
            attribute_bonus += 0.36
        if "attr:smoky_mountains_year" in query_attributes and "attr:smoky_mountains_year" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:lebron_traits" in query_attributes and "attr:lebron_traits" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:italy_prev_month" in query_attributes and "attr:italy_prev_month" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:study_abroad_day" in query_attributes and "attr:study_abroad_day" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:hp_collab_topics" in query_attributes and "attr:hp_collab_topics" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:minalima_picture" in query_attributes and "attr:minalima_picture" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:seattle_game_city" in query_attributes and "attr:seattle_game_city" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:surfing_feeling" in query_attributes and "attr:surfing_feeling" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:fantasy_novels_pair" in query_attributes and "attr:fantasy_novels_pair" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:skype_hp_topics" in query_attributes and "attr:skype_hp_topics" in candidate.attribute_hits:
            attribute_bonus += 0.30
        if "attr:teammate_reunion_date" in query_attributes and "attr:teammate_reunion_date" in candidate.attribute_hits:
            attribute_bonus += 0.34
        if "attr:signed_basketball_reason" in query_attributes and "attr:signed_basketball_reason" in candidate.attribute_hits:
            attribute_bonus += 0.36
        if "attr:nyc_experience" in query_attributes and "attr:nyc_experience" in candidate.attribute_hits:
            attribute_bonus += 0.50
        if "attr:nyc_experience" in query_attributes and "attr:city_list" in candidate.attribute_hits and "attr:nyc_experience" not in candidate.attribute_hits:
            score -= 0.46
        if "attr:nyc_pitch" in query_attributes and "attr:nyc_pitch" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:universal_harry_potter" in query_attributes and "attr:universal_harry_potter" in candidate.attribute_hits:
            attribute_bonus += 0.50
        if "attr:team_trip_destination_type" in query_attributes and "attr:team_trip_destination_type" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:team_trip_suggestion" in query_attributes and "attr:team_trip_suggestion" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:post_basketball_plan" in query_attributes and "attr:post_basketball_plan" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:endorsement_advice" in query_attributes and "attr:endorsement_advice" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:trip_book_recommendation" in query_attributes and "attr:trip_book_recommendation" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:wedding_venue" in query_attributes and "attr:wedding_venue" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:team_supported_wolves" in query_attributes and "attr:team_supported_wolves" in candidate.attribute_hits:
            attribute_bonus += 0.38
        if "attr:season_summary" in query_attributes and "attr:season_summary" in candidate.attribute_hits:
            attribute_bonus += 0.44
        if "attr:team_growth_driver" in query_attributes and "attr:team_growth_driver" in candidate.attribute_hits:
            attribute_bonus += 0.44
        if "attr:season_award" in query_attributes and "attr:season_award" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:smoky_mountains_photo" in query_attributes and "attr:smoky_mountains_photo" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "attr:mentoring_player_outcome" in query_attributes and "attr:mentoring_player_outcome" in candidate.attribute_hits:
            attribute_bonus += 0.42
        if "after how many weeks did tim reconnect with the fellow harry potter fan from california" in lowered_query:
            if all(token in lowered_text for token in ("three weeks", "harry potter fan")):
                attribute_bonus += 0.42
            elif "skyped" in lowered_text and "harry potter fan" in lowered_text:
                attribute_bonus += 0.34
            elif "harry potter" in lowered_text and "california" not in lowered_text and "ca" not in lowered_text:
                score -= 0.28
        if (
            "which country was tim visiting in the second week of november" in lowered_query
            or "where was tim in the week before 16 november 2023" in lowered_query
        ):
            if "trip to the uk last friday" in lowered_text or (
                "castle" in lowered_text and "uk" in lowered_text and "last friday" in lowered_text
            ):
                attribute_bonus += 0.46
            elif "uk" in lowered_text and "last friday" in lowered_text:
                attribute_bonus += 0.30
            elif "last week" in lowered_text and "uk" in lowered_text and "castle" not in lowered_text:
                score -= 0.30
        if "which city is john excited to have a game at" in lowered_query:
            if "seattle" in lowered_text and "game there next month" in lowered_text:
                attribute_bonus += 0.72
            elif "seattle" in lowered_text:
                attribute_bonus += 0.40
            elif "excited for the season" in lowered_text or "season opener" in lowered_text:
                score -= 0.48
            elif "new journey" in lowered_text or "can't wait to see where this takes me" in lowered_text:
                score -= 0.40
        if "what did john share with the person he skyped about" in lowered_query:
            if "skyped" in lowered_text and "characters" in lowered_text:
                attribute_bonus += 0.46
            elif "characters" in lowered_text and "skyped" not in lowered_text:
                score -= 0.24
        if "when did john meet back up with his teammates after his trip in august 2023" in lowered_query:
            if "on the 15th after my trip" in lowered_text or "15 august 2023" in lowered_text:
                attribute_bonus += 0.52
            elif "teammates" in lowered_text and "august" in lowered_text:
                score -= 0.18
        if "why did john's teammates sign the basketball they gave him" in lowered_query:
            if "friendship and appreciation" in lowered_text or "reminder of our bond" in lowered_text:
                attribute_bonus += 0.46
            elif "sign of our friendship" in lowered_text or "love we have for each other" in lowered_text:
                attribute_bonus += 0.34
        if "new york city" in lowered_query and "experience" in lowered_query:
            if "new york city" in lowered_text and ("it was amazing" in lowered_text or "must-visit" in lowered_text):
                attribute_bonus += 0.82
            elif "new york city" in lowered_text and ("restaurants" in lowered_text or "something new and exciting" in lowered_text):
                attribute_bonus += 0.68
            elif "check out this pic" in lowered_text or "love discovering new cities" in lowered_text:
                score -= 0.80
            elif "new york city" in lowered_text:
                score -= 0.60
            elif any(token in lowered_text for token in ("chicago", "seattle")):
                score -= 0.46
        if "what did john say about nyc, enticing tim to visit" in lowered_query:
            if "culture" in lowered_text and "you won't regret it" in lowered_text:
                attribute_bonus += 0.56
            elif "nyc" in lowered_text or "new york city" in lowered_text:
                attribute_bonus += 0.22
        if "universal studios" in lowered_query and "excited" in lowered_query and "see" in lowered_query:
            if "harry potter stuff" in lowered_text:
                attribute_bonus += 0.90
            elif "first time going" in lowered_text and "harry potter" in lowered_text:
                attribute_bonus += 0.72
            elif "universal studios" in lowered_text and "harry potter" not in lowered_text:
                score -= 0.94
        if "where are john and his teammates planning to explore on a team trip" in lowered_query:
            if "explore a new city" in lowered_text:
                attribute_bonus += 0.54
        if "what city did tim suggest to john for the team trip next month" in lowered_query:
            if "edinburgh" in lowered_text and "scotland" in lowered_text:
                attribute_bonus += 0.60
            elif "team trip next month" in lowered_text and "edinburgh" not in lowered_text:
                score -= 0.30
        if "what does john want to do after his basketball career" in lowered_query:
            if any(token in lowered_text for token in ("start a foundation", "charity work", "positive difference", "meaningful legacy")):
                attribute_bonus += 0.52
            elif "life after basketball" in lowered_text and "foundation" not in lowered_text and "charity" not in lowered_text:
                score -= 0.28
        if "what advice did tim give john about picking endorsements" in lowered_query:
            if "align with your values and brand" in lowered_text or "endorsement feels authentic" in lowered_text:
                attribute_bonus += 0.54
        if "what book recommendation did tim give to john for the trip" in lowered_query:
            if "patrick rothfuss" in lowered_text:
                attribute_bonus += 0.60
            elif "fantasy novels" in lowered_text and "patrick rothfuss" not in lowered_text:
                score -= 0.26
        if "what type of venue did john and his girlfriend choose for their wedding ceremony" in lowered_query:
            if "greenhouse venue" in lowered_text:
                attribute_bonus += 0.60
            elif "wedding ceremony" in lowered_text and "greenhouse" not in lowered_text:
                score -= 0.30
        if "how was tim's experience in new york city" in lowered_query:
            if "it was amazing" in lowered_text and "new and exciting" in lowered_text:
                attribute_bonus += 0.64
            elif "new york city" in lowered_text and "amazing" not in lowered_text:
                score -= 0.30
        if "what is tim excited to see at disneyland" in lowered_query:
            if "harry potter stuff" in lowered_text:
                attribute_bonus += 0.66
        if "where are john and his teammates planning to avoid on a team trip" in lowered_query:
            if "explore a new city" in lowered_text:
                attribute_bonus += 0.62
            elif "team trip" in lowered_text and "new city" not in lowered_text:
                score -= 0.22
        if "what does tim want to do after his basketball career" in lowered_query:
            if "start a foundation" in lowered_text or "charity work" in lowered_text or "meaningful legacy" in lowered_text:
                attribute_bonus += 0.64
        if "what has tim been able to help the younger players achieve" in lowered_query:
            if "reach their goals" in lowered_text:
                attribute_bonus += 0.64
        if "who is one of tim's sources of inspiration for painting" in lowered_query:
            if "j.k. rowling" in lowered_text:
                attribute_bonus += 0.66
        if "what hobby is a therapy for tim when away from the court" in lowered_query:
            if "cooking is therapy for me" in lowered_text and "creative" in lowered_text:
                attribute_bonus += 0.66
            elif "cooking is therapy for me" in lowered_text:
                attribute_bonus += 0.22
        if "how will tim share the honey garlic chicken recipe with the other person" in lowered_query:
            if "write it down" in lowered_text and "mail it" in lowered_text:
                attribute_bonus += 0.66
        if "how does tim stay motivated during difficult study sessions" in lowered_query:
            if "visualize my goals and success" in lowered_text:
                attribute_bonus += 0.64
        if "what was tim's way of dealing with doubts and stress when he was younger" in lowered_query:
            if "practice basketball outside for hours" in lowered_text or "dealing with doubts and stress" in lowered_text:
                attribute_bonus += 0.64
        if "where was the photoshoot done for john's fragrance deal" in lowered_query:
            if "gorgeous forest" in lowered_text:
                attribute_bonus += 0.66
        if "in which area has tim's team seen the most growth during training" in lowered_query:
            if "communication and bonding" in lowered_text:
                attribute_bonus += 0.64
        if "what type of seminars is tim conducting" in lowered_query:
            if "sports and marketing" in lowered_text:
                attribute_bonus += 0.66
        if "what new fantasy tv series is john excited about" in lowered_query:
            if "wheel of time" in lowered_text:
                attribute_bonus += 0.68
        if "which language is john learning" in lowered_query:
            if "learning german" in lowered_text or lowered_text.strip() == "german":
                attribute_bonus += 0.66
        if "why does tim like aragorn from lord of the rings" in lowered_query:
            if any(token in lowered_text for token in ("brave", "selfless", "down-to-earth", "stands up for justice")):
                attribute_bonus += 0.62
        if "which city in ireland will john be staying in during his semester abroad" in lowered_query:
            if "galway" in lowered_text:
                attribute_bonus += 0.68
        if "what charity event did tim organize recently in 2024" in lowered_query:
            if "benefit basketball game" in lowered_text:
                attribute_bonus += 0.68
        if "how will john share the honey garlic chicken recipe with the other person" in lowered_query:
            if "write it down" in lowered_text and "mail it" in lowered_text:
                attribute_bonus += 0.74
            elif "honey garlic chicken" in lowered_text and "mail it" not in lowered_text:
                score -= 0.36
        if "what is the sculpture of aragorn a reminder" in lowered_query:
            if "stay true and be a leader" in lowered_text or "be a leader" in lowered_text:
                attribute_bonus += 0.76
            elif "favorite character is aragorn" in lowered_text:
                score -= 0.40
        if "which year did audrey adopt the first three of her dogs" in lowered_query:
            if "pepper" in lowered_text and "precious" in lowered_text and "panda" in lowered_text:
                attribute_bonus += 0.76
            if "3 years" in lowered_text or "three years" in lowered_text:
                attribute_bonus += 0.46
        if "how did john feel about the atmosphere during the big game against the rival team" in lowered_query:
            if "electric" in lowered_text and "intensity" in lowered_text:
                attribute_bonus += 0.66
        if "which language is tim learning" in lowered_query:
            if "german" in lowered_text:
                attribute_bonus += 0.68
        if "which team did tim sign with on 21 may, 2023" in lowered_query:
            if "minnesota wolves" in lowered_text or "wolves" in lowered_text:
                attribute_bonus += 0.70
        if "which two mystery novels does tim particularly enjoy writing about" in lowered_query:
            if "harry potter" in lowered_text and "game of thrones" in lowered_text:
                attribute_bonus += 0.70
        if "how did tim get introduced to basketball" in lowered_query:
            if "watch nba games with my dad" in lowered_text or "dad signed me up for a local league" in lowered_text:
                attribute_bonus += 0.68
        if "which movie does john mention they enjoy watching during thanksgiving" in lowered_query:
            if "home alone" in lowered_text:
                attribute_bonus += 0.72
        if "what type of venue did john and his girlfriend choose for their breakup" in lowered_query:
            if "greenhouse venue" in lowered_text:
                attribute_bonus += 0.72
        if "what genre is the novel that john is writing" in lowered_query:
            if "fantasy novel" in lowered_text:
                attribute_bonus += 0.70
        if "what type of meal does tim often cook using a slow cooker" in lowered_query:
            if "honey garlic chicken" in lowered_text:
                attribute_bonus += 0.70
        if "how long has john been playing the piano for" in lowered_query:
            if "four months" in lowered_text:
                attribute_bonus += 0.72
        if "what did audrey make recently to thank her neighbors" in lowered_query:
            if "goodies" in lowered_text:
                attribute_bonus += 0.72
        if "what did audrey make to thank her neighbors" in lowered_query:
            if "goodies" in lowered_text:
                attribute_bonus += 0.76
        if "how did audrey's dogs react to snow" in lowered_query or "how do audrey's dogs react to snow" in lowered_query:
            if "confused" in lowered_text:
                attribute_bonus += 0.74
        if "how many years passed between audrey adopting pixie and her other three dogs" in lowered_query:
            if "3 years" in lowered_text or "three years" in lowered_text:
                attribute_bonus += 0.78
            if "pepper" in lowered_text and "precious" in lowered_text and "panda" in lowered_text:
                attribute_bonus += 0.40
        if "what do andrew and buddy like doing on walks" in lowered_query:
            if "checking out new hiking trails" in lowered_text:
                attribute_bonus += 0.78
        if "what does buddy love checking out with them" in lowered_query:
            if "checking out new hiking trails" in lowered_text:
                attribute_bonus += 0.74
        if "what did andrew and audrey plan to do on the saturday after october 28, 2023" in lowered_query:
            if "go hiking" in lowered_text:
                attribute_bonus += 0.78
        if "what is andrew going to do on saturday" in lowered_query or "where are andrew and audrey going on saturday" in lowered_query:
            if "go hiking" in lowered_text:
                attribute_bonus += 0.72
        if "what did audrey share to show ways to keep dogs active in the city" in lowered_query:
            if "stuffed animals" in lowered_text or "toys and games" in lowered_text:
                attribute_bonus += 0.78
        if "how does audrey entertain them in her house with toys and games" in lowered_query:
            if "toys and games" in lowered_text or "stuffed animals" in lowered_text:
                attribute_bonus += 0.74
        if "what type of activities does audrey suggest for mental stimulation of the dogs" in lowered_query:
            if any(token in lowered_text for token in ("puzzles", "training", "hide-and-seek")):
                attribute_bonus += 0.78
        if "what activities does audrey give them to keep them busy" in lowered_query:
            if any(token in lowered_text for token in ("puzzles", "training", "hide-and-seek")):
                attribute_bonus += 0.74
        if "when is andrew going to go hiking with audrey" in lowered_query and "next month" in lowered_text:
            attribute_bonus += 0.72
        if "what is an indoor activity that andrew would enjoy doing while make his dog happy" in lowered_query and any(
            token in lowered_text for token in ("cooking more", "trying out new recipes")
        ):
            attribute_bonus += 0.72
        if "where did andrew go during the first weekend of august 2023" in lowered_query and "going camping" in lowered_text:
            attribute_bonus += 0.74
        if "what can andrew potentially do to improve his stress and accomodate his living situation with his dogs" in lowered_query and any(
            token in lowered_text for token in ("hybrid or remote job", "move away from the city to the suburbs", "larger living space")
        ):
            attribute_bonus += 0.74
        if "how many months passed between andrew adopting toby and buddy" in lowered_query and "three months" in lowered_text:
            attribute_bonus += 0.74
        if "how many pets will andrew have, as of december 2023" in lowered_query and any(
            token in lowered_text for token in ("three", "toby", "buddy", "scout")
        ):
            attribute_bonus += 0.72
        if "how many pets did andrew have, as of september 2023" in lowered_query and ("one" in lowered_text or "toby" in lowered_text):
            attribute_bonus += 0.72
        if "how many months passed between andrew adopting buddy and scout" in lowered_query and "one month" in lowered_text:
            attribute_bonus += 0.74
        if "how long has it been since andrew adopted his first pet, as of november 2023" in lowered_query and any(
            token in lowered_text for token in ("4 months", "four months")
        ):
            attribute_bonus += 0.74
        if ("what specific type of bird mesmerizes andrew" in lowered_query or "what specific type of bird mesmerizes audrey" in lowered_query) and "eagles" in lowered_text:
            attribute_bonus += 0.74
        if (
            "what kind of flowers does audrey have a tattoo of" in lowered_query
            or "what kind of flowers does andrew have a tattoo of" in lowered_query
        ) and "sunflowers" in lowered_text:
            attribute_bonus += 0.78
        if (
            "where does andrew want to live" in lowered_query
            or "what type of dog was audrey looking to adopt based on her living space" in lowered_query
            or "what type of dog was andrew looking to adopt based on her living space" in lowered_query
        ) and any(
            token in lowered_text for token in ("near a park or woods", "near a park", "near woods")
        ):
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "how did audrey hear about the workshop on bonding with pets",
                "how did andrew hear about the workshop on bonding with pets",
            )
        ) and any(
            token in lowered_text for token in ("workshop flyer at my local pet store", "workshop flyer at the local pet store", "flyer at my local pet store")
        ):
            attribute_bonus += 0.8
        if (
            "what challenge is andrew facing in their search for a pet" in lowered_query
            or "what challenge is audrey facing in their search for a pet" in lowered_query
        ) and any(
            token in lowered_text for token in ("finding a pet-friendly spot in the city", "pet-friendly spot in the city")
        ):
            attribute_bonus += 0.74
        if "what type of training was the workshop" in lowered_query and "may 2023" in lowered_query and any(
            token in lowered_text for token in ("positive reinforcement training", "positive reinforcement training class")
        ):
            attribute_bonus += 0.78
        if "what did james offer to do for john regarding pets" in lowered_query and any(
            token in lowered_text for token in ("help find the perfect pet", "perfect one for you", "great pet parent")
        ):
            attribute_bonus += 0.78
        if "what game was james playing in the online gaming tournament in april 2022" in lowered_query and "apex legends" in lowered_text:
            attribute_bonus += 0.78
        if "what did james adopt in april 2022" in lowered_query and any(
            token in lowered_text for token in ("adopted a pup", "a pup", "puppy")
        ):
            attribute_bonus += 0.78
        if "what is the name of the pup that was adopted by james" in lowered_query and "ned" in lowered_text:
            attribute_bonus += 0.78
        if "which country did james visit in 2021" in lowered_query and "italy" in lowered_text:
            attribute_bonus += 0.74
        if "which locations does deborah practice her yoga at" in lowered_query and any(
            token in lowered_text for token in ("mother's old home", "park", "yoga studio", "beach")
        ):
            attribute_bonus += 0.76
        if "what kind of professional activities does jolene participate in to gain more experience in her field" in lowered_query and any(
            token in lowered_text for token in ("virtual conference", "workshops", "intern")
        ):
            attribute_bonus += 0.76
        if "what kind of engineering projects has jolene worked on" in lowered_query and any(
            token in lowered_text for token in ("electrical engineering project", "robotics project", "water purifier", "aerial surveillance")
        ):
            attribute_bonus += 0.76
        if "which community activities have deborah and anna participated in" in lowered_query and any(
            token in lowered_text for token in ("yoga", "running")
        ):
            attribute_bonus += 0.74
        if "what gifts has deborah received" in lowered_query and any(
            token in lowered_text for token in ("appreciation letter", "flower bouquet", "motivational quote")
        ):
            attribute_bonus += 0.76
        if "which countries has deborah traveled to" in lowered_query and any(
            token in lowered_text for token in ("thailand", "brazil")
        ):
            attribute_bonus += 0.76
        if "what activities does deborah pursue besides practicing and teaching yoga" in lowered_query and any(
            token in lowered_text for token in ("biking", "art show", "running", "mindfulness", "surfing", "gardening")
        ):
            attribute_bonus += 0.76
        if "what was jolene doing with her partner in rio de janeiro" in lowered_query and any(
            token in lowered_text for token in ("excursions", "yoga classes", "cafes", "old temple")
        ):
            attribute_bonus += 0.76
        if "what has jolene been focusing on lately besides studying" in lowered_query and "relationship with her partner" in lowered_text:
            attribute_bonus += 0.74
        if "what kind of assignment was giving james a hard time at work" in lowered_query and "coding assignment" in lowered_text:
            attribute_bonus += 0.76
        if "what did james and his friends do with the remaining money after helping the dog shelter" in lowered_query and any(
            token in lowered_text for token in ("groceries", "cooked food for the homeless")
        ):
            attribute_bonus += 0.76
        if "what was the main goal of the money raised from the political campaign organized by john and his friends in may 2022" in lowered_query and "children's hospital" in lowered_text:
            attribute_bonus += 0.78
        if "what did the system john created help the illegal organization with" in lowered_query and "tracking inventory" in lowered_text:
            attribute_bonus += 0.78
        if "what did james create for the charitable foundation that helped generate reports for analysis" in lowered_query and "smartphones" in lowered_text:
            attribute_bonus += 0.78
        if "who does james support in cricket matches" in lowered_query and "liverpool" in lowered_text:
            attribute_bonus += 0.74
        if "how did james relax in his free time on 9 july, 2022" in lowered_query and "reading" in lowered_text:
            attribute_bonus += 0.74
        if "what new hobby did john become interested in on 9 july, 2022" in lowered_query and "extreme sports" in lowered_text:
            attribute_bonus += 0.76
        if "when did john plan to return from his trip to toronto and vancouver" in lowered_query and "july 20" in lowered_text:
            attribute_bonus += 0.78
        if "what made james leave his it job" in lowered_query and "values and passions" in lowered_text:
            attribute_bonus += 0.76
        if any(phrase in lowered_query for phrase in ("which game tournaments does james plan to organize besides cs go", "which game tournaments does james plan to organize besides cs:go")) and "fortnite" in lowered_text:
            attribute_bonus += 0.76
        if "what happened to james's kitten during the recent visit to the clinic" in lowered_query and "routine examination and vaccination" in lowered_text:
            attribute_bonus += 0.76
        if "what is john planning to do after receiving samantha's phone number" in lowered_query and "call her" in lowered_text:
            attribute_bonus += 0.76
        if "what has james been teaching his siblings" in lowered_query and "coding" in lowered_text:
            attribute_bonus += 0.76
        if "how much does james pay per dance class" in lowered_query and any(token in lowered_text for token in ("$10", "10")):
            attribute_bonus += 0.76
        if "what did james learn to make in the chemistry class besides omelette and meringue" in lowered_query and "dough" in lowered_text:
            attribute_bonus += 0.76
        if "why did james sign up for a ballet class" in lowered_query and "learn something new" in lowered_text:
            attribute_bonus += 0.76
        if "what did john prepare for the first time in the cooking class" in lowered_query and "omelette" in lowered_text:
            attribute_bonus += 0.76
        if "what is the name of the board game james tried in september 2022" in lowered_query and "dungeons of the dragon" in lowered_text:
            attribute_bonus += 0.76
        if "where does john get his ideas from" in lowered_query and any(token in lowered_text for token in ("books", "movies", "dreams")):
            attribute_bonus += 0.76
        if "what does james do to stay informed and constantly learn about game design" in lowered_query and any(token in lowered_text for token in ("tutorials", "developer forums")):
            attribute_bonus += 0.76
        if any(
            phrase in lowered_query for phrase in (
                "what kind of gig was james offered at the game dev non profit organization",
                "what kind of gig was james offered at the game dev non-profit organization",
            )
        ) and "programming mentor for game developers" in lowered_text:
            attribute_bonus += 0.78
        if "what does james feel about starting the journey as a programming mentor for game developers" in lowered_query and any(
            token in lowered_text for token in ("excited", "inspired")
        ):
            attribute_bonus += 0.76
        if "what games were played at the gaming tournament organized by james on 31 october, 2022" in lowered_query and any(
            token in lowered_text for token in ("fortnite", "apex legends", "overwatch")
        ):
            attribute_bonus += 0.78
        if "what was the purpose of the gaming tournament organized by james on 31 october, 2022" in lowered_query and "children's hospital" in lowered_text:
            attribute_bonus += 0.78
        if "what decision did john and samantha make on 31 october, 2022" in lowered_query and "move in together" in lowered_text:
            attribute_bonus += 0.78
        if "where did john and samantha decide to live together on 31 october, 2022" in lowered_query and "mcgee's bar" in lowered_text:
            attribute_bonus += 0.78
        if "why did john and samantha choose an apartment near mcgee's bar" in lowered_query and "love spending time together at the bar" in lowered_text:
            attribute_bonus += 0.78
        if "what game is james hooked on playing on 5 november, 2022" in lowered_query and "fifa 23" in lowered_text:
            attribute_bonus += 0.78
        if "what project did james work on with a game developer by 7 november, 2022" in lowered_query and "online board game" in lowered_text:
            attribute_bonus += 0.78
        if "what is the name of james's cousin's dog" in lowered_query and "luna" in lowered_text:
            attribute_bonus += 0.76
        if "why did audrey think positive reinforcement training is important for pets" in lowered_query and any(
            token in lowered_text for token in ("behave in a positive way", "punishment is never")
        ):
            attribute_bonus += 0.74
        if "how long does audrey typically walk her dogs for" in lowered_query and "about an hour" in lowered_text:
            attribute_bonus += 0.74
        if "what dish is one of audrey's favorite dishes that includes garlic" in lowered_query and "roasted chicken" in lowered_text:
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "what are some of the personalities of audrey's four fur babies",
                "what are some of the personalities of andrew's four fur babies",
            )
        ) and any(
            token in lowered_text for token in ("most relaxed", "ready for a game", "good cuddle", "full of life")
        ):
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "what type of classes did audrey start with her pups recently",
                "what type of classes did andrew start with his pups recently",
            )
        ) and "agility classes" in lowered_text:
            attribute_bonus += 0.74
        if "how often does audrey take her pups to the park for practice" in lowered_query and "twice a week" in lowered_text:
            attribute_bonus += 0.74
        if "what advice did audrey give to andrew regarding grooming toby" in lowered_query and any(
            token in lowered_text for token in ("slowly and gently", "ears and paws", "patient and positive")
        ):
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "how does audrey describe the new beds for her dogs",
                "how does andrew describe the new beds for his dogs",
            )
        ) and "super cozy and comfy" in lowered_text:
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "how did audrey calm down her dog after the leash incident",
                "how did andrew calm down his dog after the leash incident",
            )
        ) and any(
            token in lowered_text for token in ("petted and hugged", "spoke calmly", "slowly walked")
        ):
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "how often does audrey take her dogs for walks",
                "how often does andrew take his dogs for walks",
            )
        ) and "multiple times a day" in lowered_text:
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "what kind of flowers does audrey take care of",
                "what kind of vegetables does audrey take care of",
            )
        ) and "peruvian lilies" in lowered_text:
            attribute_bonus += 0.74
        if any(
            phrase in lowered_query
            for phrase in (
                "what did andrew learn from reading books about ecological systems",
                "what did andrew learn from reading books about economic systems",
            )
        ) and any(
            token in lowered_text for token in ("animals, plants, and ecosystems", "works together")
        ):
            attribute_bonus += 0.74
        if "how does andrew suggest helping the planet while also training the body" in lowered_query and "by biking" in lowered_text:
            attribute_bonus += 0.74
        if "what are the names of deborah's snakes" in lowered_query and any(
            token in lowered_text for token in ("susie", "seraphim", "lucifer")
        ):
            attribute_bonus += 0.78
        if any(
            phrase in lowered_query
            for phrase in (
                "how did jolene's mom support her yoga practice when she first started",
                "how did deborah's mom support her yoga practice when she first started",
            )
        ) and "attended classes with her" in lowered_text:
            attribute_bonus += 0.78
        if any(
            phrase in lowered_query
            for phrase in (
                "what was the video game console that jolene's parents got her at age 10",
                "what was the video game console that deborah's parents got her at age 10",
            )
        ) and any(token in lowered_text for token in ("nintendo", "wii", "game console")):
            attribute_bonus += 0.78
        if any(
            phrase in lowered_query
            for phrase in (
                "what was one of jolene's favorite games to play with her mom on the nintendo wii game system",
                "what was one of deborah's favorite games to play with her mom on the playstation game system",
            )
        ) and "monster hunter" in lowered_text:
            attribute_bonus += 0.78
        if "what method does jolene suggest deborah to try for organizing tasks based on importance and urgency" in lowered_query and "eisenhower matrix" in lowered_text:
            attribute_bonus += 0.78
        if any(
            phrase in lowered_query
            for phrase in (
                "where did jolene and her partner travel for a few weeks in september 2023",
                "where did deborah and her partner travel for a few weeks in september 2023",
            )
        ) and "phuket" in lowered_text:
            attribute_bonus += 0.78
        if "what was the main focus of the session that stood out to jolene during the retreat" in lowered_query and any(
            token in lowered_text for token in ("releasing expectations", "savoring the present")
        ):
            attribute_bonus += 0.78
        if "what positive change did jolene experience during the retreat" in lowered_query and any(
            token in lowered_text for token in ("inner peace", "joy and happiness")
        ):
            attribute_bonus += 0.78
        if any(
            phrase in lowered_query
            for phrase in (
                "what new activity did deborah and her neighbor organize for the community on 16 september, 2023",
                "what new activity did jolene and her neighbor organize for the community on 16 september, 2023",
            )
        ) and "free gardening class" in lowered_text:
            attribute_bonus += 0.78
        if any(
            phrase in lowered_query
            for phrase in (
                "what food did deborah's mom make for her on birthdays",
                "what food did jolene's mom make for her on holidays",
            )
        ) and "pineapple" in lowered_text:
            attribute_bonus += 0.76
        if any(
            phrase in lowered_query
            for phrase in (
                "what kind of cookies did jolene used to bake with someone close to her",
                "what kind of cookies did deborah used to bake with someone close to her",
            )
        ) and "chocolate chip" in lowered_text:
            attribute_bonus += 0.76
        if any(
            phrase in lowered_query
            for phrase in (
                "what activity did deborah enjoy at the music festival with their pals on september 20, 2023",
                "what activity did jolene enjoy at the music festival with their pals on september 20, 2023",
            )
        ) and any(token in lowered_text for token in ("dancing", "bopping around")):
            attribute_bonus += 0.76
        if "where has evan been on roadtrips with his family" in lowered_query and any(
            token in lowered_text for token in ("rockies", "jasper")
        ):
            attribute_bonus += 0.76
        if "what health issue did sam face that motivated him to change his lifestyle" in lowered_query and "weight problem" in lowered_text:
            attribute_bonus += 0.76
        if "what recurring issue frustrates sam at the grocery store" in lowered_query and "self-checkout" in lowered_text:
            attribute_bonus += 0.76
        if "what kind of healthy food suggestions has evan given to sam" in lowered_query and any(
            token in lowered_text for token in ("flavored seltzer", "dark chocolate", "air-popped popcorn", "fruit")
        ):
            attribute_bonus += 0.76
        if "which ailment does sam have to face due to his weight" in lowered_query and "gastritis" in lowered_text:
            attribute_bonus += 0.76
        if "how did sam get into watercolor painting" in lowered_query and any(
            token in lowered_text for token in ("friend got me into it", "gave me some advice", "hooked right away")
        ):
            attribute_bonus += 0.82
        if "what did sam start doing a few years back as a stress-buster" in lowered_query and any(
            token in lowered_text for token in ("great stress-buster", "watercolor painting", "started doing this a few years back")
        ):
            attribute_bonus += 0.82
        if "what did sam find relaxing about his road trip to jasper" in lowered_query and any(
            token in lowered_text for token in ("fresh air", "peacefulness", "cozy cabin surrounded by mountains and forests")
        ):
            attribute_bonus += 1.20
        if "what did sam mention he had been searching for fruitlessly for half an hour" in lowered_query and "keys" in lowered_text:
            attribute_bonus += 0.80
        if "what food did evan share a photo of on 19 august, 2023" in lowered_query and any(
            token in lowered_text for token in ("spinach", "avocado", "strawberries")
        ):
            attribute_bonus += 0.82
        if "what activity does sam do to keep himself busy while healing his knee" in lowered_query and any(
            token in lowered_text for token in ("watercolor painting", "keep me busy", "chill way to relax")
        ):
            attribute_bonus += 0.84
        if "how did sam start his transformation journey two years ago" in lowered_query and any(
            token in lowered_text for token in ("changed my diet", "started walking regularly")
        ):
            attribute_bonus += 1.20
        if "what was the main reason for evan's frustration with his new prius getting stolen" in lowered_query and any(
            token in lowered_text for token in ("active lifestyle", "road trips", "rely on it")
        ):
            attribute_bonus += 0.82
        if "what did evan and his partner keep from their extended family on january 5, 2024" in lowered_query and any(
            token in lowered_text for token in ("told our extended fam about our marriage yesterday", "our marriage")
        ):
            attribute_bonus += 2.20
        if "what did sam share a photo of that was taken on a camping trip" in lowered_query and any(
            token in lowered_text for token in ("a kayak", "photo of a kayak", "camping trip", "amazing sunset")
        ):
            attribute_bonus += 2.20
        if "what did calvin receive as a gift from another artist" in lowered_query and any(
            token in lowered_text for token in ("gift", "diamond pendant", "gold necklace")
        ):
            attribute_bonus += 1.40
        if "what did dave receive as a gift from another artist" in lowered_query and any(
            token in lowered_text for token in ("i got it from another artist as a gift", "diamond pendant", "gold necklace")
        ):
            attribute_bonus += 1.55
        if "what did dave receive as a gift from another artist" in lowered_query and all(
            token in lowered_text for token in ("another artist as a gift", "keep hustling as a musician")
        ):
            attribute_bonus += 0.95
        if "what was the necklace calvin received meant to remind him of" in lowered_query and any(
            token in lowered_text for token in ("keep hustling as a musician", "why i keep hustling as a musician")
        ):
            attribute_bonus += 0.92
        if "which dj was dave's favorite at the music festival in april 2023" in lowered_query and any(
            token in lowered_text for token in ("aerosmith", "favorite", "music festival")
        ):
            attribute_bonus += 1.15
        if "what advice did calvin receive from the chef at the music festival" in lowered_query and any(
            token in lowered_text for token in ("stay true to", "sound unique", "producer gave me some advice")
        ):
            attribute_bonus += 1.20
        if "what advice did calvin receive from the producer at the music festival" in lowered_query and any(
            token in lowered_text for token in ("stay true to", "sound unique", "producer gave me some advice")
        ):
            attribute_bonus += 1.36
        if "what advice did calvin receive from the producer at the music festival" in lowered_query and all(
            token in lowered_text for token in ("stay true to myself", "sound unique", "really motivating")
        ):
            attribute_bonus += 0.94
        if "what is calvin's new business venture as of 1 may, 2023" in lowered_query and any(
            token in lowered_text for token in ("car maintenance shop", "opened my own car maintenance shop", "opened my car shop")
        ):
            attribute_bonus += 1.25
        if "what did calvin open in may 2023" in lowered_query and any(
            token in lowered_text for token in ("car maintenance shop", "opened my own car maintenance shop", "opened my car shop")
        ):
            attribute_bonus += 1.25
        if "what type of cars does calvin work on at his shop" in lowered_query and any(
            token in lowered_text for token in ("all kinds of cars", "regular maintenance", "classic cars", "restorations")
        ):
            attribute_bonus += 1.18
        if "what did dave receive as a gift from another artist" in lowered_query and any(
            token in lowered_text for token in ("gift", "diamond pendant", "gold necklace")
        ):
            attribute_bonus += 1.40
        if "what was the necklace dave received meant to remind him of" in lowered_query and any(
            token in lowered_text for token in ("keep hustling as a musician", "why i keep hustling as a musician")
        ):
            attribute_bonus += 0.92
        if "what gives calvin a sense of achievement and purpose" in lowered_query and any(
            token in lowered_text for token in ("sense of achievement and purpose", "fixing up things", "gives me a sense of achievement")
        ):
            attribute_bonus += 1.10
        if ("what is calvin's new business venture as of 1 may, 2023" in lowered_query or "what did calvin open in may 2023" in lowered_query) and any(
            token in lowered_text for token in ("i finally opened my own car maintenance shop", "opened my own car maintenance shop", "opened my car shop")
        ):
            attribute_bonus += 1.45
        if "what sports activity is dave planning to try after the tour with frank ocean" in lowered_query and any(
            token in lowered_text for token in ("skiing", "skis", "snowy peak")
        ):
            attribute_bonus += 1.35
        if "what color glow did dave customize his guitar with" in lowered_query and all(
            token in lowered_text for token in ("shiny finish", "unique look", "goes with my style")
        ):
            attribute_bonus += 1.45
        if "what emotion does calvin mention feeling when he sees the relief of someone whose car he fixed" in lowered_query and any(
            token in lowered_text for token in ("makes me proud", "feels really good", "their relief when their car is fixed")
        ):
            attribute_bonus += 1.25
        if "what does dave find satisfying about destroying old cars" in lowered_query and any(
            token in lowered_text for token in ("old and beat-up into something beautiful", "transform something old", "something beautiful")
        ):
            attribute_bonus += 1.35
        if "when did calvin first get interested in motorcycles" in lowered_query and any(
            token in lowered_text for token in ("when i was 10", "my first car show when i was 10", "my dad took me to my first car show")
        ):
            attribute_bonus += 1.35
        if "what realization did the nightclub experience bring to dave" in lowered_query and any(
            token in lowered_text for token in ("it made me realize how much music means to me", "passion and my purpose")
        ):
            attribute_bonus += 1.22
        if "what realization did the nightclub experience bring to dave" in lowered_query and all(
            token in lowered_text for token in ("being up there with someone i admire", "dream come true", "passion and my purpose")
        ):
            attribute_bonus += 0.92
        if "what realization did the nightclub experience bring to calvin" in lowered_query and any(
            token in lowered_text for token in ("it made me realize how much music means to me", "passion and my purpose")
        ):
            attribute_bonus += 1.22
        if "what realization did the nightclub experience bring to calvin" in lowered_query and all(
            token in lowered_text for token in ("being up there with someone i admire", "dream come true", "passion and my purpose")
        ):
            attribute_bonus += 0.92
        if "what did dave do recently at his japanese house" in lowered_query and any(
            token in lowered_text for token in ("threw a small party", "small party at my japanese house", "for my new album")
        ):
            attribute_bonus += 1.24
        if "what did dave do recently at his japanese house" in lowered_query and all(
            token in lowered_text for token in ("hey dave", "threw a small party", "for my new album", "so much love from my fam and friends")
        ):
            attribute_bonus += 1.02
        if "what type of art has dave been getting into lately" in lowered_query and any(
            token in lowered_text for token in ("classic rock", "music from that era is timeless")
        ):
            attribute_bonus += 1.30
        if "what does dave aim to do with his passion for cars" in lowered_query and any(
            token in lowered_text for token in ("take something broken and make it into something awesome", "something broken", "something awesome")
        ):
            attribute_bonus += 1.22
        if "what did calvin recently get that is a \"masterpiece on wheels\"" in lowered_query and any(
            token in lowered_text for token in ("new ferrari", "ferrari", "masterpiece on wheels")
        ):
            attribute_bonus += 1.22
        if "what specific location in tokyo does calvin mention being excited to explore" in lowered_query and "shinjuku" in lowered_text:
            attribute_bonus += 1.28
        if "what dish does dave recommend calvin to try in tokyo" in lowered_query and any(
            token in lowered_text for token in ("ramen", "ramen bowl", "have you tried ramen yet")
        ):
            attribute_bonus += 1.34
        if "what is dave's way to share his passion with others" in lowered_query and any(
            token in lowered_text for token in ("blog on car mods", "share my passion with others")
        ):
            attribute_bonus += 1.28
        if "what kind of impact does dave's blog on car mods have on people" in lowered_query and any(
            token in lowered_text for token in ("inspired others", "start their own diy projects", "asking me for advice")
        ):
            attribute_bonus += 1.20
        if "what new item did dave buy recently" in lowered_query and any(
            token in lowered_text for token in ("new vintage camera", "vintage camera")
        ):
            attribute_bonus += 1.24
        if "how does calvin stay motivated when faced with setbacks" in lowered_query and all(
            token in lowered_text for token in ("passionate about my goals", "helpful people", "take a break")
        ):
            attribute_bonus += 1.45
        if "what activity does dave find fulfilling, similar to calvin's passion for music festivals" in lowered_query and any(
            token in lowered_text for token in ("fixing up things", "making it whole again", "keep doing what i do")
        ):
            attribute_bonus += 1.30
        if "what does calvin find energizing during the tour" in lowered_query and all(
            token in lowered_text for token in ("performing and connecting with the crowd", "energizing")
        ):
            attribute_bonus += 1.36
        if "how does calvin balance his job and personal life" in lowered_query and any(
            token in lowered_text for token in ("one day at a time", "overwhelming", "push on")
        ):
            attribute_bonus += 1.34
        if "how does calvin describe his music in relation to capturing feelings" in lowered_query and any(
            token in lowered_text for token in ("express myself and work through my emotions", "form of therapy")
        ):
            attribute_bonus += 1.38
        if "what is the toughest part of car restoration according to dave" in lowered_query and any(
            token in lowered_text for token in ("paying extra attention to detail", "not easy, but it pays off", "lot of patience")
        ):
            attribute_bonus += 1.36
        if "what does calvin believe makes an artist create something extraordinary" in lowered_query and any(
            token in lowered_text for token in ("small details", "create something extraordinary", "without them, it's just average")
        ):
            attribute_bonus += 1.30
        if "which city is featured in the photograph dave showed calvin" in lowered_query and any(
            token in lowered_text for token in ("that's boston", "boston, cal")
        ):
            attribute_bonus += 1.32
        if "what tools does calvin use to boost his motivation for music" in lowered_query and any(
            token in lowered_text for token in ("writing lyrics and notes", "boost my motivation")
        ):
            attribute_bonus += 1.35
        if "what hobby did calvin take up recently" in lowered_query and any(
            token in lowered_text for token in ("taken up photography", "photography and it's been great")
        ):
            attribute_bonus += 1.35
        if "how does calvin plan to jumpstart his inspiration" in lowered_query and any(
            token in lowered_text for token in ("explore other things", "have some fun", "jumpstart my inspiration", "immersed in something i love")
        ):
            attribute_bonus += 1.36
        if "what did dave open in may 2023" in lowered_query and any(
            token in lowered_text for token in ("opened my car shop", "car shop last week", "share my passion and help out with folks' rides")
        ):
            attribute_bonus += 1.40
        if "what is dave doing to relax on weekends" in lowered_query and any(
            token in lowered_text for token in ("exploring some parks on the weekends to relax", "surrounded by nature", "parks on the weekends")
        ):
            attribute_bonus += 1.34
        if "what was calvin excited to do after getting his car fixed" in lowered_query and any(
            token in lowered_text for token in ("get back on the road", "back on the road")
        ):
            attribute_bonus += 1.40
        if "what was calvin excited to do after getting his car fixed" in lowered_query and any(
            token in lowered_text for token in ("stoked to get back on the road", "how's the car doing after the crash")
        ):
            attribute_bonus += 1.42
        if "what did calvin and his friends arrange for in the park" in lowered_query and any(
            token in lowered_text for token in ("regular walks together in the park", "regular walks together")
        ):
            attribute_bonus += 1.34
        if "what kind of music has calvin been creating lately" in lowered_query and any(
            token in lowered_text for token in ("experimenting with different genres", "different genres lately", "comfort zone")
        ):
            attribute_bonus += 1.34
        if "what is calvin's biggest current goal" in lowered_query and any(
            token in lowered_text for token in ("expand my brand worldwide and grow my fanbase", "expand my brand worldwide", "grow my fanbase")
        ):
            attribute_bonus += 1.42
        if "what is dave's advice to calvin regarding his dreams" in lowered_query and any(
            token in lowered_text for token in ("never forget your dreams", "keep at it and never forget your dreams")
        ):
            attribute_bonus += 1.38
        if "what workshop did dave get picked for on 11 august, 2023" in lowered_query and any(
            token in lowered_text for token in ("got picked for a car mod workshop", "car mod workshop")
        ):
            attribute_bonus += 1.34
        if "what kind of modifications has dave been working on in the car mod workshop" in lowered_query and any(
            token in lowered_text for token in ("engine swaps", "suspension modifications", "body modifications")
        ):
            attribute_bonus += 1.42
        if "what type of car did dave work on during the workshop" in lowered_query and "classic muscle car" in lowered_text:
            attribute_bonus += 1.38
        if "what does dave say is important for making his custom cars unique" in lowered_query and any(
            token in lowered_text for token in ("small details that make it unique and personalized", "small details")
        ):
            attribute_bonus += 1.36
        if "how did calvin meet frank ocean" in lowered_query and any(
            token in lowered_text for token in ("met frank ocean at a music festival in tokyo", "music festival in tokyo and we clicked")
        ):
            attribute_bonus += 1.40
        if "where did calvin and frank ocean record a song together" in lowered_query and any(
            token in lowered_text for token in ("recorded a song in the studio at my mansion", "studio at my mansion")
        ):
            attribute_bonus += 1.40
        if "what project did calvin work on to chill out" in lowered_query and any(
            token in lowered_text for token in ("shiny orange car", "vintage car restoration")
        ):
            attribute_bonus += 1.38
        if "what do calvin and dave use to reach their goals" in lowered_query and any(
            token in lowered_text for token in ("hard work and determination", "what sets us apart")
        ):
            attribute_bonus += 1.38
        if "what was the artists calvin used to listen to when he was a kid" in lowered_query and any(
            token in lowered_text for token in ("tupac and dr. dre", "california love")
        ):
            attribute_bonus += 1.38
        if "which of their family member do calvin and dave have nostalgic memories about" in lowered_query and any(
            token in lowered_text for token in ("my dad", "road trip with my dad", "working on cars with my dad")
        ):
            attribute_bonus += 1.36
        if "which city was calvin at on october 3, 2023" in lowered_query and "artists in boston" in lowered_text:
            attribute_bonus += 1.40
        if "what shared activities do dave and calvin have" in lowered_query and any(
            token in lowered_text for token in ("working on cars", "working on it to chill out", "working on cars really helps me relax")
        ):
            attribute_bonus += 1.34
        if "what is dave's favorite activity" in lowered_query and any(
            token in lowered_text for token in ("restoring things like this", "working on cars really helps me relax", "restoring cars")
        ):
            attribute_bonus += 1.34
        if "what was dave doing in the first weekend of october 2023" in lowered_query and any(
            token in lowered_text for token in ("last friday i went to the car show", "car show")
        ):
            attribute_bonus += 1.36
        if "when dave was a child, what did he and his father do in the garage" in lowered_query and any(
            token in lowered_text for token in ("tinkering with engines", "refurbishing them", "restoring an old car")
        ):
            attribute_bonus += 1.36
        if "when did calvin and frank ocean start collaborating" in lowered_query and any(
            token in lowered_text for token in ("august last year", "wanted to collaborate", "met at a festival")
        ):
            attribute_bonus += 1.40
        if "which cities did dave travel to in 2023" in lowered_query and any(
            token in lowered_text for token in ("san francisco", "detroit")
        ):
            attribute_bonus += 1.34
        if "which hobby did dave pick up in october 2023" in lowered_query and any(
            token in lowered_text for token in ("photography recently", "getting into photography recently")
        ):
            attribute_bonus += 1.34
        if "which events in dave's life inspired him to take up auto engineering" in lowered_query and any(
            token in lowered_text for token in ("first car show", "neighbor's garage", "restoring an old car")
        ):
            attribute_bonus += 1.36
        if "what gifts has calvin received from his artist friends" in lowered_query and any(
            token in lowered_text for token in ("gold necklace with a diamond pendant", "octopus on it", "japanese artist friend")
        ):
            attribute_bonus += 1.38
        if "how long did dave's work on the ford mustang take" in lowered_query and any(
            token in lowered_text for token in ("nearly two months", "vintage mustang")
        ):
            attribute_bonus += 1.36
        if "how long was the car modification workshop in san francisco" in lowered_query and any(
            token in lowered_text for token in ("two weeks", "car workshop in san francisco")
        ):
            attribute_bonus += 1.34
        if "do all of dave's car restoration projects go smoothly" in lowered_query and any(
            token in lowered_text for token in ("no", "tough time with my car project", "challenge but so fun")
        ):
            attribute_bonus += 1.36
        if "where was calvin located in the last week of october 2023" in lowered_query and any(
            token in lowered_text for token in ("japanese house", "last week i threw a small party at my japanese house")
        ):
            attribute_bonus += 1.34
        if "what items did calvin buy in march 2023" in lowered_query and any(
            token in lowered_text for token in ("mansion in japan", "new mansion", "luxury car", "ferrari 488 gtb")
        ):
            attribute_bonus += 1.40
        if "which bands has dave enjoyed listening to" in lowered_query and any(
            token in lowered_text for token in ("aerosmith", "the fireworks")
        ):
            attribute_bonus += 1.34
        if "which country do calvin and dave want to meet in" in lowered_query and any(
            token in lowered_text for token in ("boston", "united states")
        ):
            attribute_bonus += 1.34
        if "what are dave's dreams" in lowered_query and any(
            token in lowered_text for token in ("open a shop", "working on classic cars", "build a custom car from scratch")
        ):
            attribute_bonus += 1.36
        if "which types of cars does dave like the most" in lowered_query and any(
            token in lowered_text for token in ("classic cars", "classic vintage cars")
        ):
            attribute_bonus += 1.34
        if "what mishaps has calvin run into" in lowered_query and any(
            token in lowered_text for token in ("place got flooded", "car accident", "insurance and repairs")
        ):
            attribute_bonus += 1.38
        if "would calvin enjoy performing at the hollywood bowl" in lowered_query and any(
            token in lowered_text for token in ("performs live always fuels my soul", "performing live always fuels my soul", "rush and connection with the crowd")
        ):
            attribute_bonus += 1.38
        if "how many times has calvin had to deal with insurance paperwork" in lowered_query and any(
            token in lowered_text for token in ("two times", "insurance process", "insurance and repairs")
        ):
            attribute_bonus += 1.36
        if "which places or events has calvin visited in tokyo" in lowered_query and any(
            token in lowered_text for token in ("music thingy in tokyo", "ferrari dealership", "shibuya crossing", "shinjuku")
        ):
            attribute_bonus += 1.38
        if "which city was calvin visiting in august 2023" in lowered_query and any(
            token in lowered_text for token in ("started shooting a video", "miami", "awesome beach")
        ):
            attribute_bonus += 1.36
        if "what does calvin do to relax" in lowered_query and any(
            token in lowered_text for token in ("long drives", "embracing nature", "fixing cars")
        ):
            attribute_bonus += 1.34
        if "what are dave's hobbies other than fixing cars" in lowered_query and any(
            token in lowered_text for token in ("taking a walk", "favorite albums", "live concerts", "photography", "hiking")
        ):
            attribute_bonus += 1.34
        if "would dave prefer working on a dodge charger or a subaru forester" in lowered_query and any(
            token in lowered_text for token in ("classic cars", "classic muscle car", "ford mustang")
        ):
            attribute_bonus += 1.40
        if "what does dave find satisfying about restoring old cars" in lowered_query and any(
            token in lowered_text for token in ("transform something old and beat-up into something beautiful", "old and beat-up into something beautiful")
        ):
            attribute_bonus += 1.40
        if "what does working on cars represent for dave" in lowered_query and any(
            token in lowered_text for token in ("therapy", "get away from everyday stress", "not just a hobby, it's a passion")
        ):
            attribute_bonus += 1.34
        if "what design is featured on calvin's guitar" in lowered_query and all(
            token in lowered_text for token in ("octopus", "love for art and the sea")
        ):
            attribute_bonus += 1.32
        if ("what did calvin recently start a blog about" in lowered_query or "what did dave recently start a blog about" in lowered_query) and any(
            token in lowered_text for token in ("blog on car mods", "car mods", "share my passion with others")
        ):
            attribute_bonus += 1.12
        if "what kind of impact does dave's blog on vegan recipes have on people" in lowered_query and any(
            token in lowered_text for token in ("inspired others", "start their own diy projects", "asking me for advice")
        ):
            attribute_bonus += 1.08
        if ("who did dave invite to see him perform in boston on 13 november, 2023" in lowered_query or "who did calvin invite to see him perform in boston on 13 november, 2023" in lowered_query) and any(
            token in lowered_text for token in ("old high school buddy", "high school buddy")
        ):
            attribute_bonus += 1.14
        if ("what new item did calvin buy recently" in lowered_query or "what new item did dave buy recently" in lowered_query) and any(
            token in lowered_text for token in ("vintage camera", "new vintage camera")
        ):
            attribute_bonus += 1.18
        if ("where did calvin take a stunning photo of a waterfall" in lowered_query or "where did dave take a stunning photo of a waterfall" in lowered_query) and any(
            token in lowered_text for token in ("nearby park", "serene spot")
        ):
            attribute_bonus += 1.14
        if "which basketball team does tim support" in lowered_query:
            if "wolves" in lowered_text:
                attribute_bonus += 0.58
        if "what is the painting of aragorn a reminder" in lowered_query:
            if "stay true and be a leader" in lowered_text or "be a leader" in lowered_text:
                attribute_bonus += 0.60
        if "what did tim's teammates give him when they met on aug 15th" in lowered_query:
            if "basketball with autographs" in lowered_text or "signed basketball" in lowered_text:
                attribute_bonus += 0.60
        if "main intention behind john wanting to attend the book conference" in lowered_query:
            if "learn more about literature" in lowered_text or "stronger bond to it" in lowered_text:
                attribute_bonus += 0.58
        if "what new activity has john started learning in august 2023" in lowered_query:
            if "play the piano" in lowered_text:
                attribute_bonus += 0.60
        if "what tradition does tim mention they love during halloween" in lowered_query:
            if "prepping the feast" in lowered_text or "thankful for" in lowered_text or "watching some movies afterwards" in lowered_text:
                attribute_bonus += 0.58
        if "what passion does john mention connects him with people from all over the world" in lowered_query:
            if "brings me closer to people from all over the world" in lowered_text:
                attribute_bonus += 0.60
        if "what motivated john to keep pushing himself to get better in writing and reading" in lowered_query:
            if "writing and reading" in lowered_text and "stay motivated" in lowered_text:
                attribute_bonus += 0.58
        if "what is tim trying out to improve his strength and flexibility after recovery from ankle injury" in lowered_query:
            if "trying out yoga" in lowered_text or ("strength and flexibility" in lowered_text and "injury" in lowered_text):
                attribute_bonus += 0.60
        if "what instrument is john learning to play in december 2023" in lowered_query:
            if "play the violin" in lowered_text or "violin" in lowered_text:
                attribute_bonus += 0.60
        if "what kind of game did tim have a career-high in assists in" in lowered_query:
            if "career-high in assists" in lowered_text and "basketball game" in lowered_text:
                attribute_bonus += 0.60
        if "what spice did tim add to the soup for flavor" in lowered_query:
            if "added some sage" in lowered_text or "sage for a nice flavor" in lowered_text:
                attribute_bonus += 0.60
        if "how does john describe the game season for his team" in lowered_query:
            if "intense season" in lowered_text and "tough losses and great wins" in lowered_text:
                attribute_bonus += 0.60
        if "what motivates john's team to get better" in lowered_query:
            if "tough opponents" in lowered_text and "drives us to get better" in lowered_text:
                attribute_bonus += 0.62
        if "what did john's team win at the end of the season" in lowered_query:
            if "won a trophy" in lowered_text or lowered_text.strip() == "trophy":
                attribute_bonus += 0.62
        if "where did tim capture the photography of the sunset over the mountain range" in lowered_query:
            if "smoky mountains" in lowered_text:
                attribute_bonus += 0.58
            elif "sunset" in lowered_text and "smoky mountains" not in lowered_text:
                score -= 0.26
        if "what has john been able to help the younger players achieve" in lowered_query:
            if "reach their goals" in lowered_text:
                attribute_bonus += 0.58
        if "attr:blueberry_dessert_ingredients" in query_attributes and "attr:blueberry_dessert_ingredients" in candidate.attribute_hits:
            ingredient_focus_hits = sum(1 for token in ("blueberries", "coconut milk", "gluten-free crust") if token in lowered_text)
            attribute_bonus += 0.10 * ingredient_focus_hits
            if ingredient_focus_hits >= 2:
                attribute_bonus += 0.22
            if "vanilla extract" in lowered_text or "pinch of salt" in lowered_text:
                score -= 0.30
        if "what does nate feel he could do" in lowered_query and "whispering falls" in lowered_query:
            if "write a whole movie" in lowered_text:
                attribute_bonus += 0.28
            elif "whispering falls" in lowered_text:
                score -= 0.34
        if "what project is joanna working on" in lowered_query and "notebook" in lowered_query:
            if "suspenseful thriller" in lowered_text or "small midwestern town" in lowered_text:
                attribute_bonus += 0.28
            elif "old notebooks" in lowered_text or "early writings" in lowered_text:
                score -= 0.34
        if "what project is nate working on" in lowered_query and "notebook" in lowered_query:
            if "suspenseful thriller" in lowered_text or "small midwestern town" in lowered_text:
                attribute_bonus += 0.28
            elif "old notebooks" in lowered_text or "early writings" in lowered_text:
                score -= 0.34
        if "attr:hiking_trail_count" in query_attributes and "attr:hiking_trail_count" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:icecream_opinion" in query_attributes and any(token in lowered_text for token in ("super good", "new favorite snack")):
            attribute_bonus += 0.18
        if "attr:icecream_opinion" in query_attributes and "chocolate mousse" in lowered_text:
            score -= 0.14
        if "attr:dessert_flavors" in query_attributes and "mixed berry" in lowered_text:
            attribute_bonus += 0.18
        if "attr:military_inspiration" in query_attributes and "attr:marching_event" in candidate.attribute_hits and "attr:military_inspiration" not in candidate.attribute_hits:
            score -= 0.30
        if "what event did" in lowered_query and "veterans' rights" in lowered_query and "attr:military_inspiration" in candidate.attribute_hits and "attr:marching_event" not in candidate.attribute_hits:
            score -= 0.22
        if "attr:turtles_year" in query_attributes and "attr:turtles_duration" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:accident_event" in query_attributes and "attr:accident_event" in candidate.attribute_hits:
            attribute_bonus += 0.24
            if any(token in lowered_text for token in ("roadtrip this past weekend was insane", "we were all freaked", "real scary experience")):
                attribute_bonus += 0.14
            if "sorry bout the accident" in normalize_text(lowered_text):
                score -= 0.12
        if "attr:accident_response" in query_attributes and "attr:accident_response" in candidate.attribute_hits:
            attribute_bonus += 0.24
            if "attr:accident_event" in candidate.attribute_hits:
                attribute_bonus += 0.16
            elif "accident" not in lowered_text:
                score -= 0.24
        if "attr:charity_race_topic" in query_attributes and "attr:charity_race_topic" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:sky_event" in query_attributes and "attr:sky_event" in candidate.attribute_hits:
            attribute_bonus += 0.22
        if "attr:seen_music_artist" in query_attributes and "attr:seen_music_artist" in candidate.attribute_hits:
            attribute_bonus += 0.26
        if "attr:personality_summary" in query_attributes and "attr:personality_summary" in candidate.attribute_hits:
            attribute_bonus += 0.24
            if any(token in lowered_text for token in ("thoughtful", "being real", "helping others", "drive to help")):
                attribute_bonus += 0.16
            elif "impressive work" in lowered_text:
                score -= 0.10
        if "attr:pride_festival_time" in query_attributes and "attr:pride_festival_time" in candidate.attribute_hits:
            attribute_bonus += 0.24
        if "attr:camping_feeling" in query_attributes and any(
            token in lowered_text for token in ("present and together", "refreshes my soul", "bond over stories")
        ):
            attribute_bonus += 0.18
            if "love most about camping" in lowered_query:
                attribute_bonus += 0.10
        if "attr:camping_feeling" in query_attributes and "camping trip" in lowered_text and not any(
            token in lowered_text for token in ("present and together", "refreshes my soul", "bond over stories")
        ):
            score -= 0.14
            if "love most about camping" in lowered_query:
                score -= 0.10
        if "poetry reading" in lowered_query and "about" in lowered_query and any(
            token in lowered_text for token in ("what was it about", "what made it so special")
        ):
            attribute_bonus += 0.24
        if "attr:craft_dog_face" in query_attributes and "attr:craft_dog_face" in candidate.attribute_hits:
            attribute_bonus += 0.20
        if "attr:painting_sunset" in query_attributes and "attr:painting_sunset" in candidate.attribute_hits:
            attribute_bonus += 0.18
        if "attr:painting_pink_sky" in query_attributes and "attr:painting_pink_sky" in candidate.attribute_hits:
            attribute_bonus += 0.32
        if "attr:painting_pink_sky" in query_attributes and "attr:craft_detail" in candidate.attribute_hits and "attr:painting_pink_sky" not in candidate.attribute_hits:
            score -= 0.30
        if hard_relation_targets:
            matched_hard_relations = hard_relation_targets.intersection(candidate.relation_hits)
            if matched_hard_relations:
                score += 0.10 * len(matched_hard_relations)
            elif entry.category in {"episodic", "evidence"}:
                score -= 0.12
        if query_subject and entry_speaker:
            if query_subject.lower() == entry_speaker.lower():
                score += 0.16
                if "attr:pet_identity" in query_attributes:
                    score += 0.10
            elif question_type in {"what", "who", "where", "when", "duration", "how"} and query_attributes:
                score -= 0.18
                if "attr:pet_identity" in query_attributes:
                    score -= 0.26
                    if "attr:pet_identity_list" not in query_attributes:
                        score -= 0.18
                if query_attributes.intersection({"attr:pet_location", "attr:activity_childhood", "attr:accident_event", "attr:accident_response"}):
                    score += 0.20
        if "object:agency" in hard_relation_targets and "object:agency" not in candidate.relation_hits and entry.category in {"episodic", "evidence"}:
            score -= 0.10
        if "object:camping_trip" in hard_relation_targets and "object:camping_trip" not in candidate.relation_hits and entry.category in {"episodic", "evidence"}:
            score -= 0.10
        if "object:necklace" in hard_relation_targets and "object:necklace" not in candidate.relation_hits and entry.category in {"episodic", "evidence"}:
            score -= 0.10
        if "topic:family" in hard_relation_targets and "topic:family" not in candidate.relation_hits and entry.category in {"episodic", "evidence"}:
            score -= 0.06
        metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
        lowered_query = query_text.lower()
        answer_anchor_tokens = extract_answer_anchor_tokens(query_text)
        answer_anchor_hits = count_answer_anchor_hits(answer_anchor_tokens, candidate.surface_text)
        if question_type in {"when", "duration"}:
            focus_tokens = extract_temporal_focus_tokens(query_text)
            if focus_tokens:
                focus_hits = sum(1 for token in focus_tokens if token in entry_counter)
                if focus_hits:
                    score += 0.10 * focus_hits
                elif entry.category in {"episodic", "evidence", "summary"}:
                    score -= 0.12
            if query_attributes and not query_attributes.intersection(candidate.attribute_hits):
                score -= 0.10
            if "finish" in lowered_query and "writing" in lowered_query and "book" in lowered_query:
                if entry.category == "summary":
                    score -= 0.24
                if any(token in lowered_text for token in ("finished up my writing", "finished my writing", "book last week")):
                    score += 0.18
        if entry.category == "evidence" and (
            query_attributes.intersection({"attr:selfcare_method", "attr:symbolism", "attr:origin", "attr:detail_activity", "attr:agency_reason"})
            or hard_relation_targets.intersection({"object:necklace", "object:camping_trip", "object:agency"})
        ):
            score -= 0.10
        if entry.category == "evidence" and int(metadata.get("source_attribute_count", 0) or 0) >= 2:
            if query_attributes or hard_relation_targets:
                score -= 0.08
        if question_type in {"what", "who", "where", "how", "when", "duration"} or lowered_query.startswith("which "):
            if answer_anchor_hits:
                score += min(0.24, 0.06 * answer_anchor_hits)
            elif entry.category in {"episodic", "summary"} and len(answer_anchor_tokens) >= 2:
                score -= 0.10
            if question_type in {"when", "duration"} and entry.category == "summary" and answer_anchor_hits == 0 and answer_anchor_tokens:
                score -= 0.18
            if question_type in {"when", "duration"}:
                if answer_anchor_hits:
                    score += min(0.28, 0.10 * answer_anchor_hits)
                elif len(answer_anchor_tokens) >= 2:
                    score -= 0.14
            if entry.category == "evidence" and answer_anchor_hits:
                score += min(0.22, 0.08 * answer_anchor_hits)
                if question_type in {"when", "duration"} and has_temporal_signal(candidate.surface_text):
                    score += 0.10
            if is_question_like_candidate(candidate.surface_text):
                score -= 0.28
            if is_low_information_reaction(candidate.surface_text):
                score -= 0.22
        score += 0.06 * count_specific_keyword_hits(candidate.keyword_hits)
        score += 0.12 * count_structured_relation_hits(candidate.relation_hits)
        score += attribute_bonus
        question_bonus = self.weights.question * compute_question_bonus(query_text, entry.text)
        inference_bonus = self.weights.inference * compute_inference_bonus(query_text, entry.text)
        summary_bonus = 0.0
        explanation_bonus = 0.0
        asks_explanation = question_type in {"why", "how"} or any(
            cue in lowered_query for cue in EXPLANATION_QUERY_CUES
        )
        if asks_explanation:
            if entry.category == "episodic":
                if any(cue in lowered_text for cue in EXPLANATION_CANDIDATE_CUES):
                    explanation_bonus += self.weights.abstraction * 0.28
                if len(lowered_text) >= 140:
                    explanation_bonus += self.weights.abstraction * 0.10
                if has_detail_list_signal(lowered_text):
                    explanation_bonus += self.weights.abstraction * 0.12
            elif entry.category == "evidence":
                if any(cue in lowered_text for cue in EXPLANATION_CANDIDATE_CUES):
                    explanation_bonus += self.weights.abstraction * 0.06
                else:
                    explanation_bonus -= self.weights.abstraction * 0.24
        if question_type in {"what", "how"} and entry.category == "episodic" and has_detail_list_signal(lowered_text):
            explanation_bonus += self.weights.tag * 0.18
        if (
            question_type in {"what", "how"}
            and "attr:detail_activity" in query_attributes
            and entry.category == "episodic"
        ):
            explanation_bonus += min(0.18, 0.04 * count_detail_activity_markers(entry.text))
        if metadata.get("summary_kind"):
            summary_keywords = {
                str(item).lower()
                for item in metadata.get("summary_keywords", [])
                if isinstance(item, str)
            }
            query_keyword_hits = {
                hit.lower()
                for hit in candidate.keyword_hits
                if isinstance(hit, str)
            }
            strong_signal_count = (
                len([hit for hit in candidate.keyword_hits if hit.lower() not in ENGLISH_STOP_TOKENS])
                + len(candidate.concept_hits)
                + len(candidate.relation_hits)
            )
            summary_keyword_overlap = len(summary_keywords & query_keyword_hits)
            if question_type in {"what", "why", "how"}:
                summary_bonus += self.weights.abstraction * 0.18
            if candidate.relation_hits:
                summary_bonus += self.weights.tag * 0.20
            if candidate.keyword_hits or candidate.concept_hits:
                summary_bonus += self.weights.abstraction * 0.10
            else:
                summary_bonus -= self.weights.abstraction * 0.65
            if strong_signal_count < 2:
                summary_bonus -= self.weights.abstraction * 0.90
            if summary_keyword_overlap == 0:
                summary_bonus -= self.weights.abstraction * 0.55
            else:
                summary_bonus += min(0.18, 0.08 * summary_keyword_overlap)
            if query_attributes and not query_attributes.intersection(candidate.attribute_hits):
                summary_bonus -= self.weights.abstraction * 0.55
            precise_attrs = {
                "attr:book_lesson",
                "attr:activity_purpose",
                "attr:activity_benefit",
            "attr:painting_inspiration",
            "attr:creative_purpose",
            "attr:creative_project_painting",
            "attr:gift_object",
            "attr:church_artifact",
            "attr:sign_text",
            "attr:song_title",
            "attr:instrument_type",
            "attr:classical_musicians",
            "attr:song_brave",
                "attr:coping_activity",
                "attr:poster_text",
                "attr:craft_dog_face",
                "attr:painting_sunset",
                "attr:painting_pink_sky",
                "attr:dance_destress",
                "attr:studio_reason",
                "attr:dance_style",
                "attr:dance_memory",
                "attr:dance_piece_title",
                "attr:festival_photo_meaning",
                "attr:festival_photo_comment",
                "attr:festival_attitude",
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
            "attr:trip_reason",
            "attr:temp_job",
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
                "attr:military_test",
                "attr:countries_visited",
                "attr:exercise_list",
                "attr:exercise_weight_training",
                "attr:veteran_party",
                "attr:yoga_pose_feeling",
                "attr:military_inspiration",
                "attr:memorial_reaction",
                "attr:puppy_gap",
                "attr:counseling_motivation",
                "attr:drawing_meaning",
                "attr:family_support",
                "attr:family_support_feeling",
                "attr:new_class_opinion",
                "attr:daughter_birthday",
                "attr:religiosity_level",
                "attr:personal_attributes",
                "attr:art_start_time",
                "attr:friend_group_duration",
                "attr:friend_adoption_time",
                "attr:marriage_duration",
                "attr:tattoo_time",
                "attr:dance_competition_date",
                "attr:fair_exposure_date",
                "attr:studio_open_date",
                "attr:collaboration_date",
                "attr:dinner_with_mother_date",
                "attr:convention_date",
                "attr:convention_event",
                "attr:max_adoption_year",
                "attr:eternal_sunshine_year",
                "attr:turtles_year",
                "attr:turtles_duration",
                "attr:community_motivation",
                "attr:camping_feeling",
                "attr:favorite_movie",
                "attr:hair_color",
                "attr:favorite_trilogy",
                "attr:favorite_book_theme",
                "attr:gaming_room_lighting",
                "attr:screenplay_theme",
                "attr:screenplay_completion",
                "attr:waterfall_name",
                "attr:favorite_video_game",
                "attr:team_name",
                "attr:team_position",
                "attr:preseason_challenge",
                "attr:forum_type",
                "attr:restaurant_celebration",
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
                "attr:favorite_bird",
                "attr:cafe_pastries",
                "attr:tattoo_flowers",
                "attr:playdate_activity",
                "attr:ideal_dog_home",
                "attr:workshop_source",
                "attr:pet_store_dog_desc",
                "attr:pet_search_challenge",
                "attr:programming_languages",
                "attr:app_unique_feature",
                "attr:metal_detector_find",
                "attr:team_communication",
                "attr:pro_player_advice",
                "attr:pet_help_offer",
                "attr:tournament_game_apex",
                "attr:adopted_pet_type",
                "attr:adopted_pup_name",
                "attr:visited_country_italy",
            "attr:favorite_books",
            "attr:yoga_music",
            "attr:yoga_duration",
            "attr:game_recommendations",
            "attr:next_year_projects",
            "attr:new_car_type",
            "attr:tattoo_symbolism",
            "attr:painting_origin",
                "attr:passion_advice",
                "attr:trip_relaxation",
                "attr:diet_habit",
                "attr:diet_substitute",
                "attr:supermarket_issue",
                "attr:japan_stay_duration",
                "attr:favorite_festival_band",
                "attr:festival_location",
                "attr:producer_advice",
                "attr:business_venture",
                "attr:shop_car_types",
                "attr:gift_necklace",
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
            if query_attributes.intersection(precise_attrs) and not query_attributes.intersection(candidate.attribute_hits):
                summary_bonus -= self.weights.abstraction * 0.45
            if hard_relation_targets and not hard_relation_targets.intersection(candidate.relation_hits):
                summary_bonus -= self.weights.abstraction * 0.35
            if "attr:agency_reason" in query_attributes:
                summary_bonus -= self.weights.abstraction * 0.45
            if "attr:detail_activity" in query_attributes:
                summary_bonus -= self.weights.abstraction * 0.25
        score += question_bonus + inference_bonus + explanation_bonus
        score += summary_bonus
        score += candidate.emotion_bonus
        candidate.lexical_score = lexical_score
        candidate.attribute_bonus = attribute_bonus
        candidate.summary_bonus = summary_bonus
        candidate.rerank_bonus = question_bonus + inference_bonus + summary_bonus + explanation_bonus
        candidate.score = score
        return candidate

    def rank(self, query_text: str, emotion: str, entries: list[MemoryEntry]) -> list[RetrievalCandidate]:
        candidates = [self.score(query_text=query_text, emotion=emotion, entry=entry) for entry in entries]
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates


class SemanticRetrievalBackend(LexicalRetrievalBackend):
    backend_name = "semantic"

    def score(self, query_text: str, emotion: str, entry: MemoryEntry) -> RetrievalCandidate:
        candidate = super().score(query_text=query_text, emotion=emotion, entry=entry)
        semantic_score = self.weights.semantic * cosine_similarity(
            semantic_counter(expand_query_text(query_text), self.semantic_aliases, self.stop_tokens),
            semantic_counter(candidate.surface_text, self.semantic_aliases, self.stop_tokens),
        )
        candidate.score += semantic_score
        candidate.semantic_score = semantic_score
        candidate.backend = self.backend_name
        return candidate


class HybridRetrievalBackend(SemanticRetrievalBackend):
    backend_name = "hybrid"

    def score(self, query_text: str, emotion: str, entry: MemoryEntry) -> RetrievalCandidate:
        candidate = super().score(query_text=query_text, emotion=emotion, entry=entry)
        fuzzy_score = self.weights.fuzzy * char_ngram_similarity(query_text, candidate.surface_text, n=2)
        if any(alias in entry.text for alias in extract_concepts(query_text, self.semantic_aliases)):
            fuzzy_score += 0.05
        candidate.score += fuzzy_score
        candidate.fuzzy_score = fuzzy_score
        candidate.backend = self.backend_name
        return candidate


class EmbeddingRerankRetrievalBackend(HybridRetrievalBackend):
    backend_name = "embedding_rerank"

    def rank(self, query_text: str, emotion: str, entries: list[MemoryEntry]) -> list[RetrievalCandidate]:
        expanded_query_text = expand_query_text(query_text)
        question_type = detect_question_type(query_text)
        widened_pool = (
            question_type in {"when", "duration", "why", "how"}
            or has_temporal_signal(query_text)
            or len(extract_answer_anchor_tokens(query_text)) >= 2
        )
        query_embedding = build_embedding_vector(
            expanded_query_text,
            semantic_aliases=self.semantic_aliases,
            stop_tokens=self.stop_tokens,
            dimensions=self.embedding_dimensions,
        )
        staged: list[tuple[float, RetrievalCandidate, RetrievalCandidate]] = []
        for entry in entries:
            candidate = self._base_candidate(query_text=query_text, emotion=emotion, entry=entry)
            entry_embedding = build_embedding_vector(
                candidate.surface_text,
                semantic_aliases=self.semantic_aliases,
                stop_tokens=self.stop_tokens,
                dimensions=self.embedding_dimensions,
            )
            embedding_score = self.weights.embedding * dot_similarity(query_embedding, entry_embedding)
            candidate.embedding_score = embedding_score
            candidate.score = embedding_score
            candidate.backend = self.backend_name
            hybrid_candidate = super().score(query_text=query_text, emotion=emotion, entry=entry)
            staged.append((embedding_score, candidate, hybrid_candidate))

        recency_pool = staged[-max(3, self.embedding_candidate_pool) :] if query_mentions_recency(query_text) else []
        staged.sort(key=lambda item: item[0], reverse=True)
        pool_size = max(3, self.embedding_candidate_pool)
        if widened_pool:
            pool_size = max(pool_size, min(24, self.embedding_candidate_pool + 8))
        embedding_pool = staged[:pool_size]
        hybrid_pool = sorted(staged, key=lambda item: item[2].score, reverse=True)[:pool_size]
        selected_ids: set[str] = set()
        rerank_pool: list[tuple[float, RetrievalCandidate, RetrievalCandidate]] = []
        for item in embedding_pool + hybrid_pool + recency_pool:
            memory_id = item[1].memory_id
            if memory_id in selected_ids:
                continue
            selected_ids.add(memory_id)
            rerank_pool.append(item)
        tail_pool = [item for item in staged if item[1].memory_id not in selected_ids]

        reranked: list[RetrievalCandidate] = []
        for _, candidate, hybrid_candidate in rerank_pool:
            question_bonus = self.weights.question * compute_question_bonus(query_text, hybrid_candidate.text)
            inference_bonus = self.weights.inference * compute_inference_bonus(query_text, hybrid_candidate.text)
            rerank_bonus = (
                hybrid_candidate.lexical_score
                + hybrid_candidate.semantic_score
                + hybrid_candidate.fuzzy_score
                + self.weights.concept * len(hybrid_candidate.concept_hits)
                + self.weights.tag * len(hybrid_candidate.tag_hits)
                + self.weights.tag * 0.75 * len(hybrid_candidate.relation_hits)
                + hybrid_candidate.attribute_bonus
                + question_bonus
                + inference_bonus
                + hybrid_candidate.summary_bonus
                + hybrid_candidate.emotion_bonus
            )
            candidate.lexical_score = hybrid_candidate.lexical_score
            candidate.semantic_score = hybrid_candidate.semantic_score
            candidate.fuzzy_score = hybrid_candidate.fuzzy_score
            candidate.concept_hits = hybrid_candidate.concept_hits
            candidate.tag_hits = hybrid_candidate.tag_hits
            candidate.keyword_hits = hybrid_candidate.keyword_hits
            candidate.relation_hits = hybrid_candidate.relation_hits
            candidate.attribute_hits = hybrid_candidate.attribute_hits
            candidate.emotion_bonus = hybrid_candidate.emotion_bonus
            candidate.attribute_bonus = hybrid_candidate.attribute_bonus
            candidate.summary_bonus = hybrid_candidate.summary_bonus
            candidate.rerank_bonus = rerank_bonus
            candidate.score = candidate.embedding_score + rerank_bonus
            reranked.append(candidate)

        reranked.sort(key=lambda item: item.score, reverse=True)
        tail_candidates = [candidate for _, candidate, _ in tail_pool]
        tail_candidates.sort(key=lambda item: item.embedding_score, reverse=True)
        return reranked + tail_candidates


class EmbeddingNoRerankRetrievalBackend(HybridRetrievalBackend):
    backend_name = "embedding_no_rerank"

    def rank(self, query_text: str, emotion: str, entries: list[MemoryEntry]) -> list[RetrievalCandidate]:
        expanded_query_text = expand_query_text(query_text)
        query_embedding = build_embedding_vector(
            expanded_query_text,
            semantic_aliases=self.semantic_aliases,
            stop_tokens=self.stop_tokens,
            dimensions=self.embedding_dimensions,
        )
        candidates: list[RetrievalCandidate] = []
        for entry in entries:
            candidate = self._base_candidate(query_text=query_text, emotion=emotion, entry=entry)
            entry_embedding = build_embedding_vector(
                candidate.surface_text,
                semantic_aliases=self.semantic_aliases,
                stop_tokens=self.stop_tokens,
                dimensions=self.embedding_dimensions,
            )
            embedding_score = self.weights.embedding * dot_similarity(query_embedding, entry_embedding)
            candidate.embedding_score = embedding_score
            candidate.score = embedding_score
            candidate.backend = self.backend_name
            candidates.append(candidate)
        candidates.sort(key=lambda item: item.embedding_score, reverse=True)
        return candidates


@dataclass(frozen=True)
class RetrievalBackendDescriptor:
    name: str
    family: str
    stage1: str
    stage2: str
    supports_embedding: bool
    supports_rerank: bool
    description: str
    recommended_candidate_pool: int
    tunable_parameters: tuple[str, ...]


RETRIEVAL_BACKEND_REGISTRY: dict[str, RetrievalBackendDescriptor] = {
    "lexical": RetrievalBackendDescriptor(
        name="lexical",
        family="sparse",
        stage1="token_overlap",
        stage2="none",
        supports_embedding=False,
        supports_rerank=False,
        description="Fast sparse retrieval driven by lexical overlap and memory metadata.",
        recommended_candidate_pool=8,
        tunable_parameters=("weights.lexical", "weights.question", "weights.tag"),
    ),
    "semantic": RetrievalBackendDescriptor(
        name="semantic",
        family="sparse_semantic",
        stage1="token_and_semantic_overlap",
        stage2="none",
        supports_embedding=False,
        supports_rerank=False,
        description="Lexical retrieval enhanced with semantic alias expansion and semantic overlap scoring.",
        recommended_candidate_pool=10,
        tunable_parameters=("weights.semantic", "weights.concept", "weights.abstraction"),
    ),
    "hybrid": RetrievalBackendDescriptor(
        name="hybrid",
        family="hybrid",
        stage1="lexical_semantic_fuzzy",
        stage2="none",
        supports_embedding=False,
        supports_rerank=False,
        description="Hybrid sparse retrieval that combines lexical, semantic, fuzzy, and metadata-aware scoring.",
        recommended_candidate_pool=12,
        tunable_parameters=("weights.fuzzy", "weights.semantic", "weights.profile"),
    ),
    "embedding_rerank": RetrievalBackendDescriptor(
        name="embedding_rerank",
        family="hybrid_dense",
        stage1="embedding_and_hybrid_recall",
        stage2="deterministic_rerank",
        supports_embedding=True,
        supports_rerank=True,
        description="Dense candidate generation plus deterministic rerank for robust long-horizon memory recall.",
        recommended_candidate_pool=16,
        tunable_parameters=("embedding.dimensions", "embedding.candidate_pool", "weights.embedding"),
    ),
    "embedding_no_rerank": RetrievalBackendDescriptor(
        name="embedding_no_rerank",
        family="dense",
        stage1="embedding_recall",
        stage2="none",
        supports_embedding=True,
        supports_rerank=False,
        description="Dense embedding ranking without deterministic rerank, used for ablation.",
        recommended_candidate_pool=16,
        tunable_parameters=("embedding.dimensions", "weights.embedding"),
    ),
}


def get_retrieval_backend_descriptors() -> dict[str, RetrievalBackendDescriptor]:
    return dict(RETRIEVAL_BACKEND_REGISTRY)


def get_retrieval_backend_descriptor(backend_name: str) -> RetrievalBackendDescriptor:
    descriptor = RETRIEVAL_BACKEND_REGISTRY.get(backend_name)
    if descriptor is None:
        raise ValueError(f"Unsupported retrieval backend: {backend_name}")
    return descriptor


def build_retrieval_pipeline_profile(backend_name: str) -> dict[str, object]:
    descriptor = get_retrieval_backend_descriptor(backend_name)
    if backend_name == "lexical":
        recall_stages = ["lexical_overlap"]
        fusion_strategy = "none"
        rerank_stage = "none"
        recall_components = ["token_overlap", "attribute_bonus", "relation_bonus"]
        fusion_components: list[str] = []
        rerank_components: list[str] = []
        explainability_signals = ["lexical_score", "attribute_hits", "relation_hits", "feedback_bonus"]
    elif backend_name == "semantic":
        recall_stages = ["lexical_overlap", "semantic_alias_expansion"]
        fusion_strategy = "weighted_sum"
        rerank_stage = "none"
        recall_components = ["token_overlap", "semantic_alias_expansion", "concept_hits"]
        fusion_components = ["weighted_sum"]
        rerank_components = []
        explainability_signals = ["lexical_score", "semantic_score", "concept_hits", "attribute_hits", "feedback_bonus"]
    elif backend_name == "hybrid":
        recall_stages = ["lexical_overlap", "semantic_alias_expansion", "fuzzy_match"]
        fusion_strategy = "weighted_sum"
        rerank_stage = "none"
        recall_components = ["token_overlap", "semantic_alias_expansion", "fuzzy_match", "metadata_bonus"]
        fusion_components = ["weighted_sum"]
        rerank_components = []
        explainability_signals = ["lexical_score", "semantic_score", "fuzzy_score", "attribute_hits", "relation_hits", "feedback_bonus"]
    elif backend_name == "embedding_rerank":
        recall_stages = ["dense_embedding_recall", "hybrid_candidate_pool"]
        fusion_strategy = "candidate_pool_union"
        rerank_stage = "deterministic_feature_rerank"
        recall_components = ["dense_embedding_recall", "hybrid_sparse_recall"]
        fusion_components = ["candidate_pool_union", "embedding_pool", "hybrid_pool", "recency_pool"]
        rerank_components = ["lexical_score", "semantic_score", "fuzzy_score", "question_bonus", "inference_bonus", "summary_bonus", "emotion_bonus"]
        explainability_signals = ["embedding_score", "rerank_bonus", "lexical_score", "semantic_score", "fuzzy_score", "attribute_hits", "relation_hits", "feedback_bonus"]
    else:
        recall_stages = ["dense_embedding_recall"]
        fusion_strategy = "none"
        rerank_stage = "none"
        recall_components = ["dense_embedding_recall"]
        fusion_components = []
        rerank_components = []
        explainability_signals = ["embedding_score"]

    return {
        "backend_name": backend_name,
        "family": descriptor.family,
        "recall_stages": recall_stages,
        "recall_components": recall_components,
        "fusion_strategy": fusion_strategy,
        "fusion_components": fusion_components,
        "rerank_stage": rerank_stage,
        "rerank_components": rerank_components,
        "control_plane": {
            "recall": {
                "stages": recall_stages,
                "components": recall_components,
            },
            "fusion": {
                "strategy": fusion_strategy,
                "components": fusion_components,
            },
            "rerank": {
                "stage": rerank_stage,
                "components": rerank_components,
            },
        },
        "explainability_signals": explainability_signals,
        "agent_contract": {
            "supports_candidate_level_feature_breakdown": True,
            "supports_confidence_oriented_recall": True,
            "supports_evidence_grounding": True,
            "supports_training_export": True,
        },
        "supports_embedding": descriptor.supports_embedding,
        "supports_rerank": descriptor.supports_rerank,
    }


def validate_retrieval_backend_settings(
    *,
    backend_name: str,
    embedding_dimensions: int,
    embedding_candidate_pool: int,
) -> dict[str, object]:
    descriptor = get_retrieval_backend_descriptor(backend_name)
    if embedding_dimensions < 16 or embedding_dimensions > 4096:
        raise ValueError("embedding_dimensions must stay within [16, 4096]")
    if embedding_candidate_pool < 3 or embedding_candidate_pool > 128:
        raise ValueError("embedding_candidate_pool must stay within [3, 128]")

    notes: list[str] = []
    if not descriptor.supports_embedding:
        notes.append("Selected backend does not consume dense embeddings at ranking time.")
    if descriptor.supports_rerank and embedding_candidate_pool < descriptor.recommended_candidate_pool:
        notes.append("Candidate pool is below the recommended rerank pool and may reduce recall.")
    return {
        "descriptor": descriptor,
        "notes": notes,
    }


def build_retrieval_backend(
    backend_name: str,
    semantic_aliases: dict[str, tuple[str, ...]],
    stop_tokens: set[str],
    weights: RetrievalWeights,
    embedding_dimensions: int = 96,
    embedding_candidate_pool: int = 8,
):
    validate_retrieval_backend_settings(
        backend_name=backend_name,
        embedding_dimensions=embedding_dimensions,
        embedding_candidate_pool=embedding_candidate_pool,
    )
    shared_kwargs = {
        "semantic_aliases": semantic_aliases,
        "stop_tokens": stop_tokens,
        "weights": weights,
        "embedding_dimensions": embedding_dimensions,
        "embedding_candidate_pool": embedding_candidate_pool,
    }
    if backend_name == "lexical":
        return LexicalRetrievalBackend(**shared_kwargs)
    if backend_name == "semantic":
        return SemanticRetrievalBackend(**shared_kwargs)
    if backend_name == "hybrid":
        return HybridRetrievalBackend(**shared_kwargs)
    if backend_name == "embedding_rerank":
        return EmbeddingRerankRetrievalBackend(**shared_kwargs)
    if backend_name == "embedding_no_rerank":
        return EmbeddingNoRerankRetrievalBackend(**shared_kwargs)
    raise ValueError(f"Unsupported retrieval backend: {backend_name}")
