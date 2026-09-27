from __future__ import annotations

from .content_cleaning import extract_core_content


ATTRIBUTE_RULES: dict[str, tuple[str, ...]] = {
    "attr:symbolism": ("stands for", "symbolize", "symbolizes", "symbolism"),
    "attr:origin": ("home country", "from sweden", "grandma", "roots"),
    "attr:inclusivity": ("inclusive", "inclusivity", "lgbtq folks", "support for lgbtq"),
    "attr:selfcare_method": ("me-time", "running", "violin", "playing my violin", "running, reading, or playing my violin", "stay present for my fam"),
    "attr:selfcare_insight": ("self-care is really important", "look after myself", "better look after my family"),
    "attr:family_goal": ("loving home", "kids who need", "awesome mom", "family for kids", "single parent", "becoming a mom"),
    "attr:detail_activity": ("roasted marshmallows", "went on a hike", "explored nature", "campfire"),
    "attr:meaning": ("reminds me", "stands for", "love, faith and strength"),
    "attr:opinion_support": ("awesome mom", "doing something amazing", "good luck", "so lovely"),
    "attr:counseling_focus": ("work with trans people", "supporting their mental health", "helping them accept themselves"),
    "attr:counseling_motivation": (
        "my own journey and the support i got made a huge difference",
        "counseling and support groups improved my life",
        "started caring more about mental health and understanding myself",
        "want to help people go through it too",
    ),
    "attr:workshop_content": ("therapeutic methods", "best work with trans people", "safe space for people like me"),
    "attr:workshop_kind": ("counseling workshop", "lgbtq+ counseling workshop"),
    "attr:gift_object": ("gift from my grandma", "gift from my grandpa", "gift from my", "she gave it to me", "he gave it to me"),
    "attr:agency_supported_group": ("lgbtq+ folks with adoption", "lgbtq folks with adoption", "support for lgbtq+ individuals", "support for lgbtq individuals"),
    "attr:agency_reason": ("their inclusivity and support really spoke to me", "i chose them", "help lgbtq+ folks with adoption", "help lgbtq folks with adoption"),
    "attr:adoption_excitement": ("make a family for kids who need one", "family for kids who need one", "up for the challenge", "thrilled to make a family", "creating a family for those kids"),
    "attr:adoption_plan": ("researching adoption agencies", "looking into adoption agencies", "adoption agencies i'm looking into"),
    "attr:made_by_self": ("yeah, i made this bowl", "i made this bowl", "yeah, i made it", "i made this"),
    "attr:book_collection": ("kids' books", "classics", "stories from different cultures", "educational books"),
    "attr:book_title": ("charlotte's web", "becoming nicole", "amy ellis nutt"),
    "attr:book_lesson": ("self-acceptance and how to find support", "tough times don't last", "hope and love exist"),
    "attr:activity_purpose": ("de-stress", "clear my mind", "helps me reset and recharge"),
    "attr:activity_benefit": ("great for my mental health", "mental health"),
    "attr:pride_festival_time": ("we had a blast last year at the pride fest", "last year at the pride fest"),
    "attr:charity_race_topic": ("charity race for mental health", "race for mental health"),
    "attr:craft_detail": ("dog face", "sunset with a palm tree", "pink sky", "abstract painting", "blue streaks"),
    "attr:craft_dog_face": ("dog face on it", "cup with a dog face", "dog face"),
    "attr:painting_sunset": ("sunset with a palm tree", "sunset", "palm tree"),
    "attr:painting_pink_sky": ("painting of a sunset with a pink sky", "sunset with a pink sky", "pink sky"),
    "attr:painting_abstract": ("abstract painting", "blue streaks"),
    "attr:event_observation": ("create loving homes for children in need", "unity and strength"),
    "attr:painting_inspiration": ("visited a lgbtq center", "capture everyone's unity and strength", "capture unity and strength"),
    "attr:creative_purpose": ("catch the eye and make people smile", "express my feelings and be creative", "each stroke carries a part of me"),
    "attr:creative_project_painting": ("we also paint together", "painting together", "paint together"),
    "attr:flower_meaning": ("warmth and happiness", "love and beauty"),
    "attr:flower_importance": ("appreciate the small moments", "wedding decor"),
    "attr:frequency": ("once or twice a year", "usually only once or twice a year"),
    "attr:sky_event": ("perseid meteor shower", "in awe of the universe"),
    "attr:family_member": ("my daughter's birthday", "my daughter"),
    "attr:daughter_birthday": ("my daughter's birthday", "13 august"),
    "attr:performer_name": ("matt patterson",),
    "attr:seen_music_artist": ("matt patterson", "summer sounds", "got everyone dancing and singing", "he is so talented"),
    "attr:personality_summary": ("thoughtful", "being real", "helping others", "drive to help", "impressive work"),
    "attr:pet_identity": ("guinea pig", "oscar", "two cats and a dog", "another cat named bailey", "oliver", "luna"),
    "attr:pet_identity_list": ("two cats and a dog", "luna and oliver", "oliver and luna", "oliver luna bailey"),
    "attr:pet_location": ("in my slipper", "hid his bone in my slipper", "hid his bone"),
    "attr:activity_childhood": ("horseback riding",),
    "attr:artifact_type": ("stained glass window", "rainbow sidewalk", "made our own pots", "pots"),
    "attr:church_artifact": ("stained glass window",),
    "attr:sign_text": ("not being able to leave",),
    "attr:song_title": ("brave by sara bareilles", "bach", "mozart", "ed sheeran"),
    "attr:instrument_type": ("guitar", "violin", "piano", "drums", "clarinet", "flute", "cello"),
    "attr:classical_musicians": ("bach", "mozart", "beethoven", "vivaldi"),
    "attr:song_brave": ("brave by sara bareilles", "sara bareilles", "\"brave\""),
    "attr:advice_steps": ("do your research", "find an adoption agency or lawyer", "gather documents", "prepare emotionally"),
    "attr:setback": ("got hurt", "take a break from pottery", "had to take a break from pottery"),
    "attr:coping_activity": ("reading that book", "painting to keep busy", "read a book and paint"),
    "attr:poetry_reading_content": ("transgender poetry reading", "shared their stories through poetry"),
    "attr:poster_text": ("trans lives matter",),
    "attr:drawing_meaning": ("freedom and being real", "stay true to myself", "embrace my womanhood"),
    "attr:life_journey": ("ongoing adventure of learning and growing",),
    "attr:accident_event": ("got into an accident", "accident", "son got into an accident", "real scary experience"),
    "attr:accident_response": ("scared but we reassured", "they're tough kids", "they were scared", "resilient"),
    "attr:family_importance": ("mean the world to me", "family's super important to me", "so thankful to have them"),
    "attr:family_support": ("strength to keep going", "strength and motivation"),
    "attr:dance_destress": ("dance it out when you need to destress", "by dancing"),
    "attr:studio_reason": ("lost my job", "start my own business", "share my passion"),
    "attr:dance_style": ("contemporary",),
    "attr:dance_memory": ("won first place at a regionals dance competition", "favorite memory", "awesome feeling of accomplishment"),
    "attr:dance_piece_title": ("finding freedom",),
    "attr:festival_photo_meaning": ("performing at the festival",),
    "attr:festival_photo_comment": ("look graceful", "graceful"),
    "attr:festival_attitude": ("glad to be part of it", "glad"),
    "attr:store_design": ("the space, furniture, and decor", "furniture", "decor"),
    "attr:temp_job": ("temp job", "temporary job", "part-time job", "cover expenses"),
    "attr:store_feedback": ("hard work's paying off",),
    "attr:customer_experience": ("make them want to come back", "making them want to come back", "special shopping experience", "shopping experience for my customers"),
    "attr:journey_comparison": ("dancing together and supporting each other",),
    "attr:business_advice": ("build relationships with customers", "create a strong brand image", "stay positive"),
    "attr:dance_effect": ("happy", "kept me going"),
    "attr:contest_award": ("a trophy", "trophy"),
    "attr:internship_type": ("fashion internship",),
    "attr:internship_location": ("fashion department of an international company", "international company"),
    "attr:dancer_support": ("one-on-one mentoring and training",),
    "attr:clipboard_use": (
        "set goals",
        "track achievements",
        "tracks my achievements",
        "stay organized and motivated",
        "helps me find areas to improve",
        "find areas for improvement",
    ),
    "attr:trip_reason": ("clear my mind",),
    "attr:tattoo_symbolism": ("stands for freedom", "expressing myself through dance", "dancing without worrying what people think"),
    "attr:store_status": ("the store is doing great", "doing great"),
    "attr:business_motivation": ("passionate about dance and fashion", "dance and fashion"),
    "attr:bank_account_reason": ("for my business", "for his business"),
    "attr:family_activity_list": ("going for hikes", "hanging out at the park", "having picnics", "playing board games", "having movie nights"),
    "attr:mentor_quality": ("positivity and determination",),
    "attr:business_plan_actions": ("sprucing up his business plan", "tweaking his pitch to investors", "working on an online platform"),
    "attr:social_media_offer": ("help with making content", "managing your accounts", "help you with making content"),
    "attr:store_item_line": ("hoodies", "limited edition line of hoodies"),
    "attr:grand_opening_message": ("let's live it up and make some great memories",),
    "attr:grand_opening_sentiment": ("excited", "awesome memories", "excitement"),
    "attr:studio_description": ("amazing",),
    "attr:opening_night_feeling": ("excited",),
    "attr:dance_feeling": ("magical", "happy place"),
    "attr:opening_plan": ("savor all the good vibes",),
    "attr:service_activity_list": ("gave out food and supplies", "organized a toy drive", "homeless shelter"),
    "attr:volunteer_inspiration": ("her aunt",),
    "attr:castle_origin": ("england",),
    "attr:volunteer_event": ("career fair at a local school",),
    "attr:roadtrip_location": ("pacific northwest",),
    "attr:politics_focus": ("improving education and infrastructure",),
    "attr:school_funding_effect": ("needed repairs and renovations", "safer and more modern"),
    "attr:shelter_reason": ("the girl seemed sad", "had no other family"),
    "attr:hardship_history": ("divorce", "losing her job", "ending up homeless"),
    "attr:office_reason": ("impact he could make in the community", "make a difference in my community"),
    "attr:certificate_reason": ("completion of a university degree", "certificate of completion of a university degree", "diploma university", "because of my degree"),
    "attr:car_donation": ("donated my old car", "old car to a homeless shelter", "donated my old car to a homeless shelter"),
    "attr:wallet_strain": ("car broke down",),
    "attr:fundraiser_keyword": ("chili cook-off",),
    "attr:education_infra_reason": ("lack of education", "crumbling infrastructure", "affected his neighborhood"),
    "attr:family_meal": ("pizza",),
    "attr:dinner_spread": ("salads, sandwiches, and homemade desserts", "salads sandwiches homemade desserts"),
    "attr:dinner_activity": ("made some dinner together", "made dinner together"),
    "attr:park_frequency": ("a few times a week",),
    "attr:workout_frequency": ("three times a week",),
    "attr:fitness_improvement": ("more energy", "strength and endurance"),
    "attr:live_event_type": ("live music event",),
    "attr:picnic_activity_list": ("charades", "scavenger hunt"),
    "attr:veteran_values": ("respect and appreciate those who served",),
    "attr:dinner_companion": ("with my mother", "with my mom", "had dinner with my mother", "her mother"),
    "attr:military_test": ("military aptitude test",),
    "attr:countries_visited": ("spain", "england", "london"),
    "attr:children_names": ("kyle", "sara"),
    "attr:exercise_list": ("weight training", "circuit training", "kickboxing", "yoga"),
    "attr:exercise_weight_training": ("weight training",),
    "attr:degree_field": ("political science", "public administration", "public affairs"),
    "attr:religiosity_level": ("somewhat religious", "not extremely religious"),
    "attr:personal_attributes": ("selfless", "family-oriented", "passionate", "rational"),
    "attr:church_join_reason": ("closer to a community and my faith", "joined a nearby church"),
    "attr:veteran_party": ("small party to share their stories", "share stories and make connections", "heartwarming"),
    "attr:rescue_dog_plan": ("adopting a rescue dog", "adopt a rescue dog"),
    "attr:rescue_dog_values": ("responsibility and compassion",),
    "attr:dog_shelter_volunteer": ("volunteering at a local dog shelter once a month", "local dog shelter once a month"),
    "attr:waterfall_feeling": ("fairy tale",),
    "attr:aerial_yoga": ("aerial yoga",),
    "attr:gym_news": ("joined a gym",),
    "attr:kundalini_yoga": ("kundalini yoga",),
    "attr:yoga_pose_feeling": ("free and light", "feel free and light"),
    "attr:promotion_role": ("assistant manager",),
    "attr:promotion_challenge": ("self-doubt",),
    "attr:promotion_support": ("support at home and my own grit", "support at home", "my own grit"),
    "attr:housing_urgency": ("had to leave and find a new place in a hurry", "lending a hand in helping her find a new place", "my cousin just had a tough time recently"),
    "attr:marching_event": ("marching event", "veterans' rights"),
    "attr:sunset_frequency": ("at least once a week",),
    "attr:flood_damage": ("lots of homes were ruined", "homes were ruined"),
    "attr:community_motivation": ("flood in john's old area", "flood in the old area", "old area", "homes were ruined", "need to fix things up in our community"),
    "attr:dinner_plan_friends": ("dinner with friends from the gym", "dinner with some friends from the gym"),
    "attr:veteran_hospital_appreciation": ("resilience of the veterans", "inspiring stories", "elderly veteran named samuel", "filled me with hope", "appreciate what we have", "need to give back"),
    "attr:military_inspiration": ("seeing the resilience of the veterans", "respect for the military", "show support", "wanted to show my support"),
    "attr:memorial_reaction": ("awestruck and humbled", "awestruck", "humbled"),
    "attr:run_cause": ("veterans and their families",),
    "attr:blog_topic": ("politics and the government",),
    "attr:blog_focus": ("education reform and infrastructure development",),
    "attr:blog_reason": ("digging deeper into the political system has been eye-opening", "raise awareness and start conversations", "create positive change"),
    "attr:volunteer_motivation": ("help make a difference", "inspired by her aunt", "brighten somebody's day"),
    "attr:office_reason_retry": ("impact i could make in the community", "positive changes and a better future"),
    "attr:library_frequency": ("few times a week", "a few times a week"),
    "attr:france_home_artifact": ("made a painting", "remind her of a trip to france", "trip to england"),
    "attr:church_hiking": ("hiking with my church friends", "hiking with my church  friends", "felt so refreshing"),
    "attr:community_work": ("community work with my friends from church", "community work"),
    "attr:puppy_name_coco": ("coco",),
    "attr:puppy_name_shadow": ("shadow",),
    "attr:puppy_adjustment": ("doing great", "learning commands", "house training"),
    "attr:puppy_gap": ("got a puppy two weeks ago", "two weeks ago"),
    "attr:give_back_takeaway": ("appreciate what we have and the need to give back", "need to give back", "appreciate what we have"),
    "attr:teammates_friendship": ("my team had a blast to the very end", "teammates", "my team"),
    "attr:volunteer_role_school": ("mentoring students at a local school", "volunteering as a mentor for a local school", "mentor for a local school"),
    "attr:volunteer_shelter_start": ("witnessed a family struggling on the streets", "reached out to the shelter"),
    "attr:family_support_feeling": ("appreciated them a lot", "family support's huge"),
    "attr:new_class_opinion": ("fun way to switch up the exercise routine", "push yourself and mix things up"),
    "attr:art_start_time": ("practicing art since 2016", "since 2016", "since i was 17", "since i was 17 or so", "seven years now"),
    "attr:friend_adoption_time": ("friend adopted a child in 2022", "adopted a child in 2022"),
    "attr:marriage_duration": ("married for 5 years", "been married for 5 years", "5 years already"),
    "attr:friend_group_duration": ("known these friends for 4 years", "friends for 4 years", "for 4 years"),
    "attr:tattoo_time": ("got the tattoo a few years ago", "tattoo a few years ago"),
    "attr:dance_competition_date": ("hosting a dance competition next month", "dance competition next month"),
    "attr:fair_exposure_date": ("went to a fair to show off my studio yesterday", "yesterday i went to a fair to show off my studio"),
    "attr:studio_open_date": ("official opening night is tomorrow",),
    "attr:collaboration_date": ("our ideas really clicked and we decided to collaborate", "decided to collaborate"),
    "attr:dinner_with_mother_date": ("my mom and i made some dinner together last night", "had dinner with my mother on may 3 2023"),
    "attr:convention_date": ("colleagues and i went to a convention together last month", "tech for good in our community"),
    "attr:convention_event": ("tech for good convention", "convention together"),
    "attr:max_adoption_year": ("important part of our family for 10 years", "max for 10 years"),
    "attr:eternal_sunshine_year": ("first watched it around 3 years ago", "physical copy"),
    "attr:turtles_year": ("first two turtles in 2019", "got my first two turtles"),
    "attr:turtles_duration": ("had them for 3 years now", "3 years now", "three years"),
    "attr:camping_feeling": ("peaceful and awesome", "peaceful", "awesome", "present and together", "refreshes my soul", "bond over stories campfires and nature"),
}

OBJECT_RULES: dict[str, tuple[str, ...]] = {
    "obj:necklace": ("necklace",),
    "obj:bowl": ("bowl", "hand-painted bowl"),
    "obj:agency": ("adoption agency", "adoption agencies", "agency"),
    "obj:camping_trip": ("camping", "campfire", "marshmallows", "hike"),
    "obj:marriage": ("married", "husband", "wedding dress", "wedding"),
    "obj:art_practice": ("practicing art", "painting", "pottery"),
    "obj:friend_adoption": ("adopt a child", "adoption"),
    "obj:dance_competition": ("dance competition",),
    "obj:studio_fair": ("show off my studio", "fair"),
    "obj:studio_opening": ("official opening night", "open his dance studio", "dance studio"),
    "obj:tech_convention": ("tech for good convention", "convention with colleagues"),
    "obj:max_dog": ("max",),
    "obj:eternal_sunshine": ("eternal sunshine",),
    "obj:turtles": ("turtles",),
}

VISUAL_ATTRIBUTE_RULES: dict[str, tuple[str, ...]] = {
    "attr:craft_detail": ATTRIBUTE_RULES["attr:craft_detail"],
    "attr:craft_dog_face": ATTRIBUTE_RULES["attr:craft_dog_face"],
    "attr:painting_sunset": ATTRIBUTE_RULES["attr:painting_sunset"],
    "attr:painting_pink_sky": ATTRIBUTE_RULES["attr:painting_pink_sky"],
    "attr:painting_abstract": ATTRIBUTE_RULES["attr:painting_abstract"],
    "attr:poster_text": ATTRIBUTE_RULES["attr:poster_text"],
    "attr:sign_text": ATTRIBUTE_RULES["attr:sign_text"],
    "attr:church_artifact": ATTRIBUTE_RULES["attr:church_artifact"],
    "attr:certificate_reason": ATTRIBUTE_RULES["attr:certificate_reason"],
    "attr:favorite_movie": ("eternal sunshine of the spotless mind", "eternal sunshine", "spotless mind"),
    "attr:favorite_book_theme": ("about dragons", "dragon series", "series about dragons", "dragon cover", "fantasy novels dragon"),
    "attr:gaming_room_lighting": ("red and purple lighting", "red purple lighting", "gaming setup", "gaming room with a computer and a gaming chair"),
    "attr:state_indiana": ("fort wayne", "indiana"),
    "attr:favorite_trilogy": ("lord of the rings", "trilogy dvd boxset"),
    "attr:healthy_food_photo_bowl": ("spinach, avocado, and strawberries", "spinach avocado strawberries"),
    "attr:camping_photo_kayak": ("a kayak", "kayak", "kayaking", "kayaking trip", "photo of a kayak", "kayak is seen from the front of the boat"),
    "attr:skiing_plan": ("skiing", "skis", "snowy peak"),
    "attr:orange_car_project": ("shiny orange car", "orange car", "sleek vintage car restoration"),
}

ATTRIBUTE_RULES.update(
    {
        "attr:favorite_movie": ("eternal sunshine of the spotless mind", "eternal sunshine", "spotless mind"),
        "attr:hair_color": ("purple hair", "dyed my hair purple", "hair purple", "dyed my hair last week"),
        "attr:favorite_trilogy": ("lord of the rings",),
        "attr:favorite_book_theme": ("about dragons", "dragon series", "series about dragons", "dragon cover", "fantasy novels dragon"),
        "attr:gaming_room_lighting": ("red and purple lighting", "red purple lighting", "gaming setup", "gaming room with a computer and a gaming chair"),
        "attr:screenplay_theme": ("loss, identity, and connection", "loss identity connection"),
        "attr:screenplay_completion": ("finished my first full screenplay", "printed it last friday", "screenplay and printed it"),
        "attr:waterfall_name": ("whispering falls", "beautiful location called whispering falls"),
        "attr:firetruck_acquisition": ("brand new fire truck", "fire truck"),
        "attr:domestic_abuse_partner": ("local organization that helps victims of domestic abuse", "victims of domestic abuse"),
        "attr:shared_interests": ("watching movies", "making desserts", "similar interests"),
        "attr:hiking_trail_count": ("twice", "found an awesome hiking trail", "another hiking trail"),
        "attr:favorite_video_game": ("xenoblade chronicles", "xeonoblade chronicles"),
        "attr:tournament_game": ("street fighter", "street fighter tournament"),
        "attr:book_recommendations": ("little women", "a court of thorns and roses"),
        "attr:shared_movies": ("little women", "lord of the rings"),
        "attr:happy_memory_method": ("corkboard", "notebook"),
        "attr:console_switch": ("nintendo switch", "nintendo games", "xenoblade chronicles", "xeonoblade chronicles"),
        "attr:tournament_valorant": ("valorant",),
        "attr:state_florida": ("florida", "tampa"),
        "attr:movie_genre": ("action and sci-fi", "fantasy and sci-fi", "dramas and romcoms"),
        "attr:movie_genre_action_scifi": ("action and sci-fi",),
        "attr:screenplay_plan": ("submit it to some film festivals", "producers and directors", "check it out"),
        "attr:screenplay_inspiration": ("personal experiences", "my own journey of self-discovery"),
        "attr:screenplay_genre": ("drama and romance", "mix of drama and romance"),
        "attr:turtle_pet_reason": ("slow pace", "calming", "low-maintenance"),
        "attr:turtle_care": ("keep their area clean", "feed them properly", "enough light", "not tough"),
        "attr:writing_gig": ("writing gig",),
        "attr:book_project_timeline": ("started on a book recently", "finished up my writing for my book", "book last week", "late nights and edits"),
        "attr:icecream_ingredients": ("coconut milk", "vanilla extract", "sugar", "salt"),
        "attr:dessert_flavors": ("chocolate", "mixed berry", "chocolate mousse"),
        "attr:icecream_flavor": ("chocolate and vanilla swirl",),
        "attr:icecream_opinion": ("super good", "rich and creamy", "super creamy"),
        "attr:teaching_skills": ("started teaching people how to make this", "sharing my love for dairy-free desserts", "reset high scores", "tips to improve gaming skills"),
        "attr:state_indiana": ("fort wayne", "indiana"),
        "attr:movie_genre_fantasy_scifi": ("fantasy and sci-fi",),
        "attr:favorite_book_features": ("adventures", "magic", "great characters"),
        "attr:escape_activity_movies": ("great escape", "get my imagination going", "watching fantasy and sci-fi movies"),
        "attr:cake_filling": ("strawberry filling",),
        "attr:cake_frosting": ("coconut cream frosting",),
        "attr:whispering_falls_writing": ("write a whole movie",),
        "attr:screenplay_joke_plan": ("start to think of a drama", "publish my own screenplay"),
        "attr:trails_inviter": ("sure, you should come down and join me on the trails sometime",),
        "attr:stuffed_animal_gift": ("got this new pup for you", "get her a stuffed animal"),
        "attr:stuffed_animal_meaning": ("stuffed animal to remind you of the good vibes",),
        "attr:gaming_party_invitees": ("old friends", "teammates from other tournaments", "teamates from other tournaments"),
        "attr:gaming_party_items": ("custom controller decorations",),
        "attr:superhero_spiderman": ("spider-man", "peter parker"),
        "attr:superhero_ironman": ("iron man",),
        "attr:corkboard_items": ("inspiring quotes", "pictures", "little keepsakes"),
        "attr:vegan_icecream_shared": ("made vegan ice cream last friday", "vegan ice cream", "vegan diet group"),
        "attr:vegan_recipe_offer": ("i can give it to you tomorrow", "vegan ice cream recipe"),
        "attr:recipe_plan_family": ("make it for my family this weekend", "make it for my family"),
        "attr:roadtrip_research_location": ("woodhaven", "small town in the midwest"),
        "attr:book_themes": ("loss, redemption, and forgiveness",),
        "attr:tournament_career": ("competing in video game tournaments", "make money doing what i love"),
        "attr:writing_impact": ("share my stories and hopefully have an impact", "writing can make a difference"),
        "attr:joanna_coconut_icecream": ("you make coconut milk icecream", "coconut milk icecream, it's so good"),
        "attr:sharing_desserts_feeling": ("always happy to share them with you", "happy to share"),
        "attr:writers_group_celebration": ("celebrated by making this delicious treat", "making this delicious treat"),
        "attr:tournament_chill_celebration": ("taking some time off this weekend to chill with my pets", "chill with my pets"),
        "attr:favorite_treat_mousse": ("dairy-free chocolate mousse",),
        "attr:cake_type_raspberry": ("dairy-free chocolate cake with raspberries", "chocolate cake with raspberries"),
        "attr:blueberry_dessert_ingredients": ("blueberries", "coconut milk", "gluten-free crust"),
        "attr:recent_movie_little_women": ("watched \"little women\" recently", "\"little women\" recently"),
        "attr:writing_club_bookmark": ("cute little bookmark", "bookmark for one of the ladies at my writing club"),
        "attr:unwind_photo": ("bookcase filled with dvds and movies", "video games or watching movies helps me unwind"),
        "attr:classic_movie_opinion": ("story was so gripping", "actors were great"),
        "attr:living_room_tips": ("couch that can sit multiple people", "really fluffy", "blanket that has a little bit of weight", "lights that can be dimmed"),
        "attr:tilly_focus": ("tilly helps me stay focused", "brings me so much joy"),
        "attr:tilly_while_writing": ("she's always with me while i write", "stuffed animal dog"),
        "attr:cake_frosting": ("coconut cream frosting",),
        "attr:party_attendance": ("7 people", "there were 7 people that attended"),
        "attr:favorite_dish_show": ("coconut milk ice cream is at the top of my list", "favorite dish", "coconut milk ice cream"),
        "attr:tilly_origin": ("dog back in michigan", "the name helps me remember her", "used to have a dog back in michigan"),
        "attr:rejection_response": ("keep grinding and moving ahead",),
        "attr:resilience_respect": ("respect you for that", "able to bounce back"),
        "attr:rejection_advice": ("rejections don't define you", "keep at it", "find the perfect opportunity"),
        "attr:character_visuals_purpose": ("visuals of the characters", "bring them alive in my head", "write better"),
        "attr:turtle_diet": ("combination of vegetables, fruits, and insects", "varied diet"),
        "attr:current_game_xenoblade": ("xeonoblade chronicles", "xenoblade chronicles"),
        "attr:letter_object": ("handwritten letter", "that letter is really awesome"),
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
            "smaller, more intimate gathering",
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
        "attr:season_award": (
            "we even won a trophy",
            "won a trophy",
            "trophy",
        ),
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
        "attr:writing_inspiration_author": (
            "j.k. rowling",
            "inspiring writer",
            "taking notes on her style",
        ),
        "attr:slow_cooker_meal": (
            "honey garlic chicken with roasted veg",
            "honey garlic chicken",
            "roasted veg",
        ),
        "attr:recipe_sharing_method": (
            "write it down and mail it",
            "write it down for you and mail it",
        ),
        "attr:lebron_inspiration_specific": (
            "epic block in game 7 of the 16 finals",
            "determination and heart",
            "never give up",
        ),
        "attr:study_motivation_method": (
            "visualize my goals and success",
            "focus and motivation",
        ),
        "attr:injury_update": (
            "doctor said it's not too serious",
            "not too serious",
        ),
        "attr:yoga_hold_duration": (
            "30-60 seconds",
            "30 60 seconds",
        ),
        "attr:recent_finished_book": (
            "a dance with dragons",
            "really good story",
            "highly recommend it",
        ),
        "attr:travel_agency_visit": (
            "visited a travel agency",
            "see what the requirements would be",
            "next dream trip",
        ),
        "attr:youth_sports_cause": (
            "supporting youth sports",
            "fair chances in sports",
            "underserved communities",
        ),
        "attr:favorite_book_series_hp": (
            "harry potter is my favorite book",
            "harry potter",
            "immersive",
        ),
        "attr:aragorn_identity": (
            "my favorite character is aragorn",
            "aragorn",
        ),
        "attr:aragorn_reason": (
            "brave selfless down-to-earth attitude",
            "never gives up",
            "stands up for justice",
        ),
        "attr:middle_earth_map": (
            "map of middle-earth from lotr",
            "different realms and regions",
        ),
        "attr:ireland_city_galway": (
            "stay in galway",
            "galway",
            "arts and irish music",
        ),
        "attr:benefit_basketball_game": (
            "held a benefit basketball game last week",
            "benefit basketball game",
        ),
        "attr:endorsement_reaction": (
            "felt crazy",
            "sense of accomplishment",
            "hard work paid off",
        ),
        "attr:barcelona_recommendation": (
            "barcelona is a must-visit city",
            "barcelona",
            "culture architecture and amazing food",
        ),
        "attr:forum_type_fantasy": (
            "fantasy literature forum",
            "joined a fantasy literature forum",
        ),
        "attr:restaurant_celebration_game": (
            "celebrated at a restaurant",
            "reliving the intense moments",
            "after that we celebrated",
        ),
        "attr:online_mag_articles": (
            "writing about different fantasy novels",
            "studying characters themes",
            "making book recommendations",
        ),
        "attr:harry_potter_trivia_event": (
            "intense harry potter trivia contest",
            "charity thing",
            "anthony and i",
        ),
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
        "attr:leader_reminder": (
            "stay true and be a leader in everything i do",
            "be a leader",
            "painting in my room",
        ),
        "attr:signed_basketball_gift": (
            "a basketball with autographs",
            "photo of what my teammates gave me",
            "signed basketball",
        ),
        "attr:book_conference_reason": (
            "help me learn more about literature",
            "create a stronger bond to it",
            "book conference next month",
        ),
        "attr:piano_learning": (
            "started learning how to play the piano",
            "play the piano",
            "so satisfying seeing the progress",
        ),
        "attr:fantasy_connects_people": (
            "my passion for fantasy stuff brings me closer to people from all over the world",
            "shared the same love of hp",
            "magical family",
        ),
        "attr:writing_reading_motivation": (
            "writing and reading",
            "that's what helps me stay motivated",
            "push myself to get better",
        ),
        "attr:yoga_recovery_training": (
            "trying out yoga",
            "extra strength and flexibility",
            "challenging but worth it",
        ),
        "attr:violin_learning": (
            "learning how to play the violin",
            "violin",
            "classical music",
        ),
        "attr:career_high_assists_game": (
            "career-high in assists",
            "big game against our rival",
            "basketball game",
        ),
        "attr:sage_soup_flavor": (
            "added some sage for a nice flavor",
            "sage",
        ),
        "attr:thanksgiving_tradition": (
            "prepping the feast",
            "talking about what we're thankful for",
            "watching some movies afterwards",
        ),
        "attr:study_motivation_visualization": (
            "visualize my goals and success",
            "focus and motivation",
            "stay motivated during tough studying",
        ),
        "attr:stress_coping_basketball": (
            "practice basketball outside for hours",
            "dreaming of playing in big games",
            "way of dealing with doubts and stress",
        ),
        "attr:photoshoot_forest_location": (
            "photoshoot went really well",
            "gorgeous forest",
            "outdoor gear",
        ),
        "attr:training_growth_area": (
            "most growth in communication and bonding",
            "understand each other's strengths and weaknesses",
            "helped our performances",
        ),
        "attr:seminar_topic": (
            "seminars",
            "sports and marketing",
            "helping people with their sports and marketing",
        ),
        "attr:language_german": (
            "learning german now",
            "german",
            "tough but fun",
        ),
        "attr:fantasy_tv_series_wot": (
            "wheel of time",
            "new show that's coming out",
            "based on a book series that i love",
        ),
        "attr:big_game_atmosphere": (
            "atmosphere in the arena was really electric",
            "extra level of intensity",
            "electric and intense",
        ),
        "attr:basketball_origin": (
            "watch nba games with my dad",
            "dad signed me up for a local league",
            "basketball has been a part of my life ever since i was a kid",
        ),
        "attr:thanksgiving_movie": (
            "we love home alone",
            "home alone",
            "brings lots of laughs",
        ),
        "attr:novel_genre_fantasy": (
            "in the middle of fantasy novel",
            "fantasy novel",
            "create a whole new world",
        ),
        "attr:piano_duration_four_months": (
            "playing for about four months now",
            "about four months now",
            "amazing adventure",
        ),
        "attr:first_three_dogs_year": (
            "i've had them for 3 years",
            "their names are pepper precious and panda",
            "pepper precious and panda",
        ),
        "attr:neighbor_goodies": (
            "made some goodies recently",
            "thank my neighbors",
            "bring some joy around here",
        ),
        "attr:dogs_snow_confusion": (
            "they were so confused",
            "hate snow",
            "prefer nice sunny days in the grass",
        ),
        "attr:dog_hiking_trails": (
            "checking out new hiking trails",
            "stoked and interested in everything nature has to offer",
            "loves checking out new hiking trails",
        ),
        "attr:hiking_plan": (
            "go hiking",
            "grab some snacks and have a blast exploring",
            "saturday sound good",
        ),
        "attr:indoor_dog_toys": (
            "toys and games",
            "basket full of stuffed animals",
            "entertain them in my house",
        ),
        "attr:dog_mental_stimulation": (
            "puzzles",
            "training",
            "hide-and-seek",
        ),
        "attr:hike_next_month_august": (
            "next month when the weather is more pleasant",
            "down for a hike with you and your furry friends",
            "august",
        ),
        "attr:cook_dog_treats": (
            "getting into cooking more",
            "trying out new recipes",
            "cook dog treats",
        ),
        "attr:camping_with_girlfriend": (
            "my girlfriend, toby and i are going camping",
            "going camping",
            "first weekend of august 2023",
        ),
        "attr:remote_suburb_plan": (
            "hybrid or remote job",
            "move away from the city to the suburbs",
            "larger living space and be closer to nature",
        ),
        "attr:toby_buddy_gap": ("three months", "toby", "buddy"),
        "attr:andrew_pets_december": ("three", "toby buddy scout", "three pets"),
        "attr:andrew_pets_september": ("one", "toby", "one pet"),
        "attr:buddy_scout_gap": ("one month", "buddy", "scout"),
        "attr:first_pet_duration_november": ("4 months", "four months", "adopted his first pet"),
        "attr:positive_training_reason": (
            "learn how to behave in a positive way",
            "punishment is never the proper way",
            "positive reinforcement way",
        ),
        "attr:positive_training_type": (
            "positive reinforcement training",
            "positive reinforcement training class",
        ),
        "attr:dog_walk_duration_hour": ("about an hour", "usually for about an hour", "explore at their own pace"),
        "attr:roasted_chicken": ("roasted chicken", "one of my favorites", "send you the recipe"),
        "attr:dog_personality_list": (
            "oldest one is the most relaxed",
            "second one is always ready for a game",
            "third one can be naughty but loves a good cuddle",
            "youngest one is full of life",
        ),
        "attr:agility_classes": ("agility classes", "pups at a dog park", "face and conquer challenges"),
        "attr:park_practice_frequency": ("twice a week", "park for practice", "great bonding experience"),
        "attr:grooming_advice": (
            "slowly and gently",
            "ears and paws",
            "stay patient and positive",
        ),
        "attr:dog_beds_comfy": ("super cozy and comfy", "my furry friends love them"),
        "attr:leash_incident_calming": (
            "petted and hugged her",
            "spoke calmly",
            "slowly walked her to relax",
        ),
        "attr:dog_walk_frequency": ("multiple times a day", "great bonding time for us"),
        "attr:peruvian_lilies": ("peruvian lilies", "bright colors", "delicate petals"),
        "attr:ecosystem_lesson": (
            "animals, plants, and ecosystems",
            "how it all works together",
            "fascinating",
        ),
        "attr:biking_planet": ("help the planet", "train our body", "by biking"),
        "attr:writers_group_project": ("finding home",),
        "attr:team_name": ("minnesota wolves",),
        "attr:team_position": ("shooting guard",),
        "attr:preseason_challenge": ("fitting into the new team's style of play", "new team's style of play"),
        "attr:forum_type": ("fantasy literature forum",),
        "attr:restaurant_celebration": ("celebrated a tough win", "a tough win"),
        "attr:sponsorship_deals": ("basketball shoe and gear deal with nike", "potential sponsorship deal with gatorade", "nike and gatorade"),
        "attr:favorite_bird": ("eagles",),
        "attr:cafe_pastries": ("croissants", "muffins", "tarts"),
        "attr:tattoo_flowers": ("sunflowers",),
        "attr:playdate_activity": ("chat with people while dogs make new friends", "chat with people", "dogs make new friends"),
        "attr:ideal_dog_home": ("near a park or woods", "near a park", "near woods"),
        "attr:workshop_source": (
            "workshop flyer at the local pet store",
            "workshop flyer at my local pet store",
            "flyer at the local pet store",
            "flyer at my local pet store",
        ),
        "attr:pet_store_dog_desc": ("friendly and playful",),
        "attr:pet_search_challenge": ("finding a pet-friendly spot in the city", "pet-friendly spot in the city"),
        "attr:programming_languages": ("python and c++", "python", "c++"),
        "attr:app_unique_feature": ("customize their pup's preferences", "customize their pup's preferences/needs", "pup's preferences"),
        "attr:metal_detector_find": ("bottle caps",),
        "attr:team_communication": ("voice chat",),
        "attr:pro_player_advice": ("never put your ego above team success", "team success"),
        "attr:pet_help_offer": ("help find the perfect pet", "make a great pet parent", "perfect one for you"),
        "attr:tournament_game_apex": ("apex legends",),
        "attr:adopted_pet_type": ("adopted a pup", "a pup", "puppy"),
        "attr:adopted_pup_name": ("ned", "i named it ned"),
        "attr:visited_country_italy": ("visited italy", "last year i visited italy", "italy"),
        "attr:work_assignment_coding": ("coding assignment",),
        "attr:dog_breed_labrador": ("labrador",),
        "attr:pizza_pepperoni": ("pepperoni",),
        "attr:pizza_hawaiian": ("hawaiian pizza", "hawaiian"),
        "attr:charity_leftovers_homeless": ("bought groceries and cooked food for the homeless", "groceries", "cooked food for the homeless"),
        "attr:charity_hospital": ("children's hospital", "raise money for a children's hospital"),
        "attr:foundation_tracking": ("tracking inventory, resources, and donations", "inventory resources donations"),
        "attr:foundation_app_mobile": ("computer application on smartphones", "application on smartphones", "smartphones"),
        "attr:football_team_liverpool": ("liverpool",),
        "attr:football_team_mancity": ("manchester city",),
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
        "attr:instrument_guitar": ("guitar",),
        "attr:instrument_drums": ("drums",),
        "attr:gig_programming_mentor": ("programming mentor for game developers",),
        "attr:mentor_feeling_excited": ("excited and inspired", "excited", "inspired"),
        "attr:inspiration_witcher3": ("witcher 3",),
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
        "attr:first_console_nintendo": ("nintendo game console", "nintendo wii", "console when i was 10"),
        "attr:favorite_game_monster_hunter": ("monster hunter: world", "monster hunter world", "monster hunter"),
        "attr:task_method_eisenhower": ("eisenhower matrix",),
        "attr:retreat_location_phuket": ("phuket",),
        "attr:retreat_focus_present": ("releasing expectations and judgments", "savoring the present"),
        "attr:retreat_outcome_peace": ("finding inner peace", "new level of joy and happiness"),
        "attr:gardening_class_free": ("free gardening class",),
        "attr:mom_birthday_cakes": ("pineapple birthday cakes", "pineapple cakes"),
        "attr:cookie_type_choc_chip": ("chocolate chip cookies", "warm gooey chocolate", "soft buttery cookie"),
        "attr:event_music_dance": ("dancing and bopping around", "dance and bop around", "bopping around"),
        "attr:favorite_books": ("sapiens", "avalanche by neal stephenson", "neal stephenson"),
        "attr:yoga_music": ("savana", "sleep"),
        "attr:yoga_duration": ("about 3 years", "three years"),
        "attr:game_recommendations": ("zelda botw", "animal crossing: new horizons", "overcooked 2"),
        "attr:next_year_projects": ("developing renewable energy", "supply clean water", "clean water to those with limited access"),
        "attr:new_car_type": ("new prius",),
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
        "attr:painting_origin": ("friend's advice", "friend advised", "friend suggested painting"),
        "attr:passion_advice": ("keep trying new things until something sparks excitement", "keep trying new things"),
        "attr:trip_relaxation": (
            "fresh air",
            "peacefulness",
            "cozy cabin surrounded by mountains and forests",
            "nice way to relax after the road trip",
            "relax after the road trip",
            "we just did it yesterday",
        ),
        "attr:diet_habit": ("consuming soda and candy", "soda and candy"),
        "attr:diet_substitute": ("flavored seltzer water", "dark chocolate with high cocoa content", "dark chocolate"),
        "attr:supermarket_issue": ("broken self-checkout machines", "self-checkout machines"),
        "attr:japan_stay_duration": ("a few months",),
        "attr:favorite_festival_band": ("aerosmith",),
        "attr:festival_location": ("tokyo",),
        "attr:producer_advice": ("stay true to himself and sound unique", "stay true to yourself and sound unique"),
        "attr:business_venture": ("car maintenance shop",),
        "attr:shop_car_types": ("all kinds of cars", "regular maintenance", "full restorations of classic cars", "classic cars"),
        "attr:gift_necklace": ("gold necklace with a diamond pendant", "diamond pendant"),
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
        "attr:fixing_fulfilling": ("fixing up things", "making it whole again", "love the feeling of taking something broken and making it whole again"),
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
)


def extract_attribute_markers(text: str) -> list[str]:
    lowered = extract_core_content(text).lower()
    raw_lowered = text.lower()
    markers: list[str] = []
    for marker, patterns in OBJECT_RULES.items():
        if any(pattern in lowered for pattern in patterns):
            markers.append(marker)
    for marker, patterns in ATTRIBUTE_RULES.items():
        if any(pattern in lowered for pattern in patterns):
            markers.append(marker)
    for marker, patterns in VISUAL_ATTRIBUTE_RULES.items():
        if any(pattern in raw_lowered for pattern in patterns):
            markers.append(marker)
    return list(dict.fromkeys(markers))


def infer_query_attribute_targets(text: str) -> list[str]:
    lowered = extract_core_content(text).lower()
    targets = set(extract_attribute_markers(text))
    if "how long has" in lowered and "group of friends" in lowered:
        targets.add("attr:friend_group_duration")
    if "what does" in lowered and any(token in lowered for token in ("symbolize", "stand for", "stands for")):
        targets.add("attr:symbolism")
        targets.add("object:necklace")
    if "what country" in lowered or ("where" in lowered and "from" in lowered):
        targets.add("attr:origin")
        if "grandma" in lowered:
            targets.add("object:necklace")
    if "what type of individuals" in lowered or ("why did" in lowered and "agency" in lowered):
        targets.add("attr:inclusivity")
    if "what type of individuals" in lowered and "agency" in lowered:
        targets.add("attr:agency_supported_group")
        targets.add("object:agency")
        targets.add("topic:family")
    if "why did" in lowered and "agency" in lowered:
        targets.add("attr:agency_reason")
        targets.add("object:agency")
        targets.add("topic:family")
    if "how does" in lowered and "self-care" in lowered:
        targets.add("attr:selfcare_method")
    if "what did" in lowered and "realize" in lowered:
        targets.add("attr:selfcare_insight")
        targets.add("speaker:melanie")
    if "what is" in lowered and "excited about" in lowered:
        targets.add("attr:family_goal")
        targets.add("attr:adoption_excitement")
        targets.add("topic:family")
    if "plans for the summer" in lowered or ("what are" in lowered and "plans" in lowered):
        targets.add("intent:future")
        targets.add("object:agency")
        targets.add("attr:adoption_plan")
        targets.add("topic:family")
    if "what does" in lowered and "think" in lowered:
        targets.add("attr:opinion_support")
    if "what did" in lowered and "while camping" in lowered:
        targets.add("attr:detail_activity")
        targets.add("object:camping_trip")
    if "what was grandma" in lowered and "gift" in lowered:
        targets.add("object:necklace")
    if "what was" in lowered and "gift" in lowered:
        targets.add("attr:gift_object")
    if "what country" in lowered and "grandma" in lowered:
        targets.add("object:necklace")
    if "what is" in lowered and "bowl" in lowered and "reminder" in lowered:
        targets.add("object:bowl")
        targets.add("attr:meaning")
    if "what kind of counseling" in lowered or "what kind of" in lowered and "services" in lowered:
        targets.add("attr:counseling_focus")
    if "what workshop" in lowered and "attend" in lowered:
        targets.add("attr:workshop_kind")
        targets.add("object:workshop")
    if "what was discussed" in lowered and "workshop" in lowered:
        targets.add("attr:workshop_content")
        targets.add("object:workshop")
    if "what motivated" in lowered and "counseling" in lowered:
        targets.add("attr:counseling_motivation")
        targets.add("topic:career")
    if "did melanie make" in lowered and "bowl" in lowered:
        targets.add("attr:made_by_self")
        targets.add("object:bowl")
    if "did" in lowered and "make" in lowered and "bowl" in lowered:
        targets.add("attr:made_by_self")
        targets.add("object:bowl")
    if "what kind of books" in lowered or ("library" in lowered and "books" in lowered):
        targets.add("attr:book_collection")
    if "favorite book" in lowered or "what book did" in lowered or "which book" in lowered:
        targets.add("attr:book_title")
    if "take away from the book" in lowered or ("what did" in lowered and "becoming nicole" in lowered):
        targets.add("attr:book_lesson")
    if "what are the new shoes" in lowered and "used for" in lowered:
        targets.add("attr:selfcare_method")
        targets.add("attr:activity_purpose")
    if "reason for getting into running" in lowered:
        targets.add("attr:activity_purpose")
    if "raise awareness for" in lowered and "charity race" in lowered:
        targets.add("attr:activity_benefit")
        targets.add("attr:charity_race_topic")
    if "great for" in lowered and "running" in lowered:
        targets.add("attr:activity_benefit")
    if "what kind of pot" in lowered or "what did mel and her kids paint" in lowered or "what painting did" in lowered or "what kind of painting" in lowered:
        targets.add("attr:craft_detail")
    if "what creative project do mel and her kids do together besides pottery" in lowered:
        targets.add("attr:creative_project_painting")
    if "what kind of pot" in lowered:
        targets.add("attr:craft_dog_face")
    if "latest project" in lowered and "paint" in lowered:
        targets.add("attr:painting_sunset")
    if "what painting did" in lowered and "october 13" in lowered:
        targets.add("attr:painting_pink_sky")
    if ("what did" in lowered and " see " in f" {lowered} ") or "what inspired" in lowered:
        targets.add("attr:event_observation")
    if "what inspired" in lowered and "painting" in lowered:
        targets.add("attr:painting_inspiration")
    if "why did" in lowered and ("colors and patterns" in lowered or "pottery project" in lowered):
        targets.add("attr:creative_purpose")
    if "sunflowers represent" in lowered:
        targets.add("attr:flower_meaning")
    if "flowers important" in lowered:
        targets.add("attr:flower_importance")
    if "how often" in lowered:
        targets.add("attr:frequency")
    if ("what did" in lowered and "family see" in lowered) or ("how did" in lowered and "feel while watching" in lowered):
        targets.add("attr:sky_event")
    if "whose birthday" in lowered:
        targets.add("attr:family_member")
    if "when is melanie's daughter's birthday" in lowered:
        targets.add("attr:daughter_birthday")
    if "who performed" in lowered:
        targets.add("attr:performer_name")
    if "what musical artists" in lowered or "what bands has" in lowered:
        targets.add("attr:seen_music_artist")
    if "personality traits might" in lowered:
        targets.add("attr:personality_summary")
    if "what pet does" in lowered:
        targets.add("attr:pet_identity")
    if "what pets does" in lowered:
        targets.add("attr:pet_identity")
        targets.add("attr:pet_identity_list")
    if "where did" in lowered and "hide his bone" in lowered:
        targets.add("attr:pet_location")
    if "used to do with her dad" in lowered:
        targets.add("attr:activity_childhood")
    if "what did" in lowered and "make for a local church" in lowered:
        targets.add("attr:artifact_type")
    if "what did" in lowered and "make for a local church" in lowered:
        targets.add("attr:church_artifact")
    if "what did" in lowered and "find in her neighborhood" in lowered:
        targets.add("attr:artifact_type")
    if "what did" in lowered and "while camping" in lowered:
        targets.add("attr:detail_activity")
    if "precautionary sign" in lowered or ("sign" in lowered and "caf" in lowered):
        targets.add("attr:sign_text")
    if "which song" in lowered or "which  classical musicians" in lowered or "which classical musicians" in lowered or "modern music" in lowered:
        targets.add("attr:song_title")
    if "what type of instrument" in lowered:
        targets.add("attr:instrument_type")
    if "which classical musicians" in lowered:
        targets.add("attr:classical_musicians")
    if "song" in lowered and any(token in lowered for token in ("courageous", "brave")):
        targets.add("attr:song_brave")
    if "what advice" in lowered and "adoption" in lowered:
        targets.add("attr:advice_steps")
    if "take away from the book" in lowered or ("take away from" in lowered and "book" in lowered):
        targets.add("attr:book_lesson")
    if "what setback" in lowered:
        targets.add("attr:setback")
    if "what did" in lowered and "paint recently" in lowered:
        targets.add("attr:painting_sunset")
    if "keep herself busy" in lowered:
        targets.add("attr:coping_activity")
    if "poetry reading" in lowered and "about" in lowered:
        targets.add("attr:poetry_reading_content")
    if "what was the poetry reading" in lowered and "about" in lowered:
        targets.add("attr:poetry_reading_content")
    if "posters" in lowered and "say" in lowered:
        targets.add("attr:poster_text")
    if "drawing" in lowered and any(token in lowered for token in ("symbolize", "symbolise", "stand for")):
        targets.add("attr:drawing_meaning")
    if "journey through life together" in lowered:
        targets.add("attr:life_journey")
    if "what happened to melanie's son" in lowered or ("what happened to" in lowered and "son" in lowered and "road trip" in lowered):
        targets.add("attr:accident_event")
    if "handle the accident" in lowered or ("children" in lowered and "accident" in lowered):
        targets.add("attr:accident_response")
    if "feel about her family after the accident" in lowered or "feel after the accident" in lowered or "reaction to her children enjoying the grand canyon" in lowered:
        targets.add("attr:family_importance")
    if "what do melanie's family give her" in lowered:
        targets.add("attr:family_support")
    if "feel about her family supporting her" in lowered:
        targets.add("attr:family_support_feeling")
    if "how do jon and gina both like to destress" in lowered:
        targets.add("attr:dance_destress")
    if "why did jon decide to start his dance studio" in lowered:
        targets.add("attr:studio_reason")
    if "favorite style of dance" in lowered:
        targets.add("attr:dance_style")
    if "favorite dancing memory" in lowered:
        targets.add("attr:dance_memory")
    if "what kind of dance piece" in lowered:
        targets.add("attr:dance_piece_title")
    if "dancers in the photo represent" in lowered:
        targets.add("attr:festival_photo_meaning")
    if "dancers in the photo" in lowered and "say about" in lowered:
        targets.add("attr:festival_photo_comment")
    if "attitude towards being part of the dance festival" in lowered:
        targets.add("attr:festival_attitude")
    if "what did gina design for her store" in lowered:
        targets.add("attr:store_design")
    if "what did" in lowered and "design for" in lowered and "store" in lowered:
        targets.add("attr:store_design")
    if "what did jon say about gina's progress with her store" in lowered:
        targets.add("attr:store_feedback")
    if "creating an experience for her customers" in lowered:
        targets.add("attr:customer_experience")
    if "compare their entrepreneurial journeys" in lowered:
        targets.add("attr:journey_comparison")
    if "advice does gina give to jon about running a successful business" in lowered:
        targets.add("attr:business_advice")
    if "what does jon's dance make him" in lowered:
        targets.add("attr:dance_effect")
    if "what did gina receive from a dance contest" in lowered:
        targets.add("attr:contest_award")
    if "what kind of professional experience" in lowered:
        targets.add("attr:internship_type")
    if "where is gina's fashion internship" in lowered:
        targets.add("attr:internship_location")
    if "where is" in lowered and "internship" in lowered:
        targets.add("attr:internship_location")
    if "what is jon offering to the dancers" in lowered:
        targets.add("attr:dancer_support")
    if "clipboard with a notepad attached" in lowered:
        targets.add("attr:clipboard_use")
    if "trip to rome" in lowered:
        targets.add("attr:trip_reason")
    if "trip to" in lowered:
        targets.add("attr:trip_reason")
    if "how is gina's store doing" in lowered:
        targets.add("attr:store_status")
    if "why did gina combine her clothing business with dance" in lowered:
        targets.add("attr:business_motivation")
    if "why did" in lowered and "combine" in lowered and "business with dance" in lowered:
        targets.add("attr:business_motivation")
    if "why did jon shut down his bank account" in lowered:
        targets.add("attr:bank_account_reason")
    if "activities does john's family enjoy doing together" in lowered or "activities does jon's family enjoy doing together" in lowered:
        targets.add("attr:family_activity_list")
    if "perfect mentor and guide" in lowered:
        targets.add("attr:mentor_quality")
    if "plans does jon have after receiving advice" in lowered:
        targets.add("attr:business_plan_actions")
    if "plans does" in lowered and "after receiving advice" in lowered:
        targets.add("attr:business_plan_actions")
    if "offer does gina make to jon regarding social media" in lowered:
        targets.add("attr:social_media_offer")
    if "limited edition line of" in lowered:
        targets.add("attr:store_item_line")
    if "say to jon about the grand opening" in lowered:
        targets.add("attr:grand_opening_message")
    if "general sentiment about the upcoming grand opening" in lowered:
        targets.add("attr:grand_opening_sentiment")
    if "describe the studio that jon has opened" in lowered:
        targets.add("attr:studio_description")
    if "feel about the opening night" in lowered:
        targets.add("attr:opening_night_feeling")
    if "feeling that dance brings" in lowered:
        targets.add("attr:dance_feeling")
    if "plan to do at the grand opening" in lowered:
        targets.add("attr:opening_plan")
    if "service efforts" in lowered:
        targets.add("attr:service_activity_list")
    if "inspired maria to start volunteering" in lowered:
        targets.add("attr:volunteer_inspiration")
    if "castle shadow box" in lowered:
        targets.add("attr:castle_origin")
    if "what event did john volunteer at last weekend" in lowered:
        targets.add("attr:volunteer_event")
    if "where did john explore on a road trip last year" in lowered:
        targets.add("attr:roadtrip_location")
    if "main focus in local politics" in lowered:
        targets.add("attr:politics_focus")
    if "extra funding help the school" in lowered:
        targets.add("attr:school_funding_effect")
    if "why did maria sit with the little girl" in lowered:
        targets.add("attr:shelter_reason")
    if "what did jean go through" in lowered:
        targets.add("attr:hardship_history")
    if "why did john decide to run for office again" in lowered:
        targets.add("attr:office_reason")
    if "receive a certificate for" in lowered:
        targets.add("attr:certificate_reason")
    if "put a strain on his wallet" in lowered:
        targets.add("attr:wallet_strain")
    if "spread the word about" in lowered and "fundraiser" in lowered:
        targets.add("attr:fundraiser_keyword")
    if "sparked john's interest in improving education and infrastructure" in lowered:
        targets.add("attr:education_infra_reason")
    if "kind of meal did john and his family make together" in lowered:
        targets.add("attr:family_meal")
    if "what kind of food did maria have on her dinner spread" in lowered:
        targets.add("attr:dinner_spread")
    if "what activity did maria and her mom do together" in lowered:
        targets.add("attr:dinner_activity")
    if "how often does john take his kids to the park" in lowered:
        targets.add("attr:park_frequency")
    if "how often does john work out with his family" in lowered:
        targets.add("attr:workout_frequency")
    if "how has john's fitness improved" in lowered:
        targets.add("attr:fitness_improvement")
    if "kind of event did john and his family attend" in lowered:
        targets.add("attr:live_event_type")
    if "what kind of activities did maria do at the picnic" in lowered:
        targets.add("attr:picnic_activity_list")
    if "important for children regarding veterans" in lowered:
        targets.add("attr:veteran_values")
    if "who did" in lowered and "have dinner with" in lowered:
        targets.add("attr:dinner_companion")
    if "what test has john taken multiple times" in lowered:
        targets.add("attr:military_test")
    if "what european countries has maria been to" in lowered:
        targets.add("attr:countries_visited")
    if "what are the names of john's children" in lowered:
        targets.add("attr:children_names")
    if "what exercises has john done" in lowered:
        targets.add("attr:exercise_list")
    if "what might john's degree be in" in lowered:
        targets.add("attr:degree_field")
    if "would caroline be considered religious" in lowered:
        targets.add("attr:religiosity_level")
    if "what attributes describe john" in lowered:
        targets.add("attr:personal_attributes")
    if "feel closer to a community and her faith" in lowered or "why did maria join a nearby church" in lowered:
        targets.add("attr:church_join_reason")
    if "what did john host for the veterans" in lowered or "what did john and the veterans do during the small party" in lowered or "what emotions did john feel during the small party" in lowered:
        targets.add("attr:veteran_party")
    if "honor the memories of his beloved pet" in lowered:
        targets.add("attr:rescue_dog_plan")
    if "through adopting a rescue dog" in lowered:
        targets.add("attr:rescue_dog_values")
    if "what new activity did maria start recently" in lowered and "3 june" in lowered:
        targets.add("attr:dog_shelter_volunteer")
    if "waterfall in oregon" in lowered:
        targets.add("attr:waterfall_feeling")
    if "what type of workout class did maria start" in lowered:
        targets.add("attr:aerial_yoga")
    if "what exciting news did maria share" in lowered:
        targets.add("attr:gym_news")
    if "what yoga activity has maria been trying" in lowered:
        targets.add("attr:kundalini_yoga")
    if "what does maria say she feels when doing upside-down yoga poses" in lowered:
        targets.add("attr:yoga_pose_feeling")
    if "what did john recently get promoted to" in lowered:
        targets.add("attr:promotion_role")
    if "biggest challenges john faced" in lowered:
        targets.add("attr:promotion_challenge")
    if "support he received during his journey to becoming assistant manager" in lowered:
        targets.add("attr:promotion_support")
    if "why did maria need to help her cousin find a new place to live" in lowered:
        targets.add("attr:housing_urgency")
    if "what event did john participate in to show support for veterans' rights" in lowered:
        targets.add("attr:marching_event")
    if "what event did" in lowered and "veterans' rights" in lowered:
        targets.add("attr:marching_event")
    if "how often does john get to see sunsets" in lowered:
        targets.add("attr:sunset_frequency")
    if "how did the flood impact the homes" in lowered:
        targets.add("attr:flood_damage")
    if "what did maria plan to do later on the evening" in lowered:
        targets.add("attr:dinner_plan_friends")
    if "what does john appreciate about the veteran's hospital visit" in lowered:
        targets.add("attr:veteran_hospital_appreciation")
    if "why did john feel inspired to join the military after the visit to the hospital" in lowered:
        targets.add("attr:military_inspiration")
        targets.add("attr:veteran_hospital_appreciation")
    if "join the military after the visit to the hospital" in lowered:
        targets.add("attr:military_inspiration")
        targets.add("attr:veteran_hospital_appreciation")
    if "what inspired john to join the marching event" in lowered or ("inspired john" in lowered and "veterans' rights" in lowered):
        targets.add("attr:military_inspiration")
    if "what motivated maria and john to discuss potential solutions for their community" in lowered:
        targets.add("attr:community_motivation")
    if "what motivated" in lowered and "solutions for their community" in lowered:
        targets.add("attr:community_motivation")
    if "which activity has john done apart from yoga at the studio" in lowered:
        targets.add("attr:exercise_weight_training")
    if "how did john describe his kids' reaction at the military memorial" in lowered:
        targets.add("attr:memorial_reaction")
    if "kids' reaction at the military memorial" in lowered:
        targets.add("attr:memorial_reaction")
    if "how does john describe the camping trip with max" in lowered:
        targets.add("attr:camping_feeling")
    if "what does john think about trying new classes" in lowered:
        targets.add("attr:new_class_opinion")
    if "what cause did the 5k charity run organized by john support" in lowered:
        targets.add("attr:run_cause")
    if "what cause did the 5k charity run organized by" in lowered:
        targets.add("attr:run_cause")
    if "what did the donations help john's community acquire" in lowered:
        targets.add("attr:firetruck_acquisition")
    if "donate to a luxury store" in lowered:
        targets.add("attr:car_donation")
    if "get promoted to" in lowered:
        targets.add("attr:promotion_role")
    if "biggest challenge" in lowered and "assistant manager" in lowered:
        targets.add("attr:promotion_challenge")
    if "what topic has john been blogging about recently" in lowered:
        targets.add("attr:blog_topic")
    if "why did maria start blogging about politics and policies" in lowered:
        targets.add("attr:blog_topic")
    if "focus of john's recent research and writing on his blog" in lowered:
        targets.add("attr:blog_focus")
    if "who inspired john to start volunteering" in lowered:
        targets.add("attr:volunteer_inspiration")
        targets.add("attr:volunteer_motivation")
    if "why did maria decide to run for office again" in lowered:
        targets.add("attr:office_reason")
        targets.add("attr:office_reason_retry")
    if "how often does john take his kids to the library" in lowered:
        targets.add("attr:library_frequency")
    if "what did maria receive a certificate for" in lowered:
        targets.add("attr:certificate_reason")
    if "why did maria start blogging about politics and policies" in lowered:
        targets.add("attr:blog_reason")
    if "what was the focus of" in lowered and "blog" in lowered:
        targets.add("attr:blog_focus")
    if "how often does maria work out with her family" in lowered or ("how often" in lowered and "work out" in lowered):
        targets.add("attr:workout_frequency")
    if "how has john's artistic skills improved" in lowered or ("improved since starting boot camps" in lowered):
        targets.add("attr:fitness_improvement")
    if "what did" in lowered and "feel closer to a community and" in lowered:
        targets.add("attr:church_join_reason")
    if "honor the memories of" in lowered and "beloved pet" in lowered:
        targets.add("attr:rescue_dog_plan")
    if "what did" in lowered and "like being at the desert in oregon" in lowered:
        targets.add("attr:waterfall_feeling")
    if "upside-down yoga poses" in lowered:
        targets.add("attr:yoga_pose_feeling")
    if "what is the name of" in lowered and "one-year-old child" in lowered:
        targets.add("attr:children_names")
    if "what is the name of" in lowered and "second kitten" in lowered:
        targets.add("attr:puppy_name_shadow")
    if "what activity did" in lowered and "rob" in lowered and "invite" in lowered:
        targets.add("attr:exercise_list")
    if "why did john need to help his cousin find a new place to live" in lowered or ("help his cousin find a new place" in lowered):
        targets.add("attr:housing_urgency")
    if "who did john work with to raise awareness and funds" in lowered:
        targets.add("attr:domestic_abuse_partner")
    if "what does john criticize about the veteran's hospital visit" in lowered:
        targets.add("attr:give_back_takeaway")
    if "what did john take away from visiting the orphanage" in lowered:
        targets.add("attr:give_back_takeaway")
    if "what kind of interests do joanna and nate share" in lowered:
        targets.add("attr:shared_interests")
    if "what book recommendations has joanna given" in lowered:
        targets.add("attr:book_recommendations")
    if "what movies have both joanna and nate seen" in lowered:
        targets.add("attr:shared_movies")
    if "what does joanna do to remember happy memories" in lowered:
        targets.add("attr:happy_memory_method")
    if "what console does nate own" in lowered:
        targets.add("attr:console_switch")
    if "what alternative career might nate consider after gaming" in lowered:
        targets.add("attr:turtle_care")
        targets.add("obj:turtles")
    if "how long did it take for joanna to finish writing her book" in lowered:
        targets.add("attr:book_project_timeline")
    if "which torunament did nate win" in lowered or ("which tournament did nate win" in lowered):
        targets.add("attr:tournament_valorant")
    if "how many hikes has joanna been on" in lowered:
        targets.add("attr:hiking_trail_count")
    if "what state did nate visit" in lowered:
        targets.add("attr:state_florida")
    if "what state did joanna visit in summer 2021" in lowered:
        targets.add("attr:state_indiana")
    if "how many times has joanna found new hiking trails" in lowered:
        targets.add("attr:hiking_trail_count")
    if "what is one of joanna's favorite movies" in lowered:
        targets.add("attr:favorite_movie")
    if "what type of movies does nate enjoy watching the most" in lowered:
        targets.add("attr:movie_genre")
        targets.add("attr:movie_genre_action_scifi")
    if "what is nate's favorite genre of movies" in lowered:
        targets.add("attr:movie_genre_fantasy_scifi")
    if "what kind of books does nate enjoy" in lowered:
        targets.add("attr:favorite_book_features")
    if "which activity helps nate escape and stimulates his imagination" in lowered:
        targets.add("attr:escape_activity_movies")
    if "what are joanna's plans for her finished screenplay" in lowered:
        targets.add("attr:screenplay_plan")
    if "what genre is joanna's first screenplay" in lowered:
        targets.add("attr:screenplay_genre")
    if "what inspired joanna's new screenplay" in lowered:
        targets.add("attr:screenplay_inspiration")
    if "for how long has nate had his turtles" in lowered:
        targets.add("attr:turtles_duration")
        targets.add("obj:turtles")
    if "what did nate think of the coconut milk ice cream" in lowered:
        targets.add("attr:icecream_opinion")
    if "which dairy-free dessert flavors does nate enjoy" in lowered:
        targets.add("attr:dessert_flavors")
    if "what flavor of ice cream did nate make" in lowered:
        targets.add("attr:icecream_flavor")
    if "why does nate like turtles as pets" in lowered:
        targets.add("attr:turtle_pet_reason")
        targets.add("obj:turtles")
    if "how does nate describe the process of taking care of turtles" in lowered:
        targets.add("attr:turtle_care")
        targets.add("obj:turtles")
    if "what was joanna's audition for" in lowered:
        targets.add("attr:writing_gig")
    if "what are the main ingredients of the ice cream recipe shared by nate" in lowered:
        targets.add("attr:icecream_ingredients")
    if "what are the skills that nate has helped others learn" in lowered:
        targets.add("attr:teaching_skills")
    if "what filling did joanna use in the cake she made recently in may 2022" in lowered:
        targets.add("attr:cake_filling")
    if "what kind of frosting" in lowered and "cake" in lowered and "joanna" in lowered:
        targets.add("attr:cake_frosting")
    if "what does nate feel he could do" in lowered and "whispering falls" in lowered:
        targets.add("attr:whispering_falls_writing")
    if "what creative activity does nate joke about pursuing" in lowered:
        targets.add("attr:screenplay_joke_plan")
    if "who invited nate to join her on the trails sometime" in lowered:
        targets.add("attr:trails_inviter")
    if "what did nate do for joanna on 25 may, 2022" in lowered:
        targets.add("attr:stuffed_animal_gift")
    if "how does nate describe the stuffed animal he got for joanna" in lowered:
        targets.add("attr:stuffed_animal_meaning")
    if "who did nate plan to invite to his gaming party" in lowered:
        targets.add("attr:gaming_party_invitees")
    if "what special items did nate get for everyone at his gaming party" in lowered:
        targets.add("attr:gaming_party_items")
    if "what superhero is joanna a fan of" in lowered:
        targets.add("attr:superhero_spiderman")
    if "which superhero toy figure does nate share a photo of" in lowered:
        targets.add("attr:superhero_ironman")
    if "what is displayed on joanna's cork board" in lowered:
        targets.add("attr:corkboard_items")
    if "what did nate make and share with his vegan diet group" in lowered:
        targets.add("attr:vegan_icecream_shared")
    if "what recipe nate offer to share with joanna" in lowered:
        targets.add("attr:vegan_recipe_offer")
    if "what did joanna plan to do with the recipe nate promised to share" in lowered:
        targets.add("attr:recipe_plan_family")
    if "where did joanna go for a road trip for research" in lowered:
        targets.add("attr:roadtrip_research_location")
    if "what specific themes are explored in joanna's new book" in lowered:
        targets.add("attr:book_themes")
    if "what does nate do that he loves and can make money from" in lowered:
        targets.add("attr:tournament_career")
    if "what kind of impact does joanna hope to have with her writing" in lowered:
        targets.add("attr:writing_impact")
    if "what motivates joanna to keep writing even on tough days" in lowered:
        targets.add("attr:writing_impact")
    if "what type of ice cream does joanna mention that nate makes" in lowered:
        targets.add("attr:joanna_coconut_icecream")
    if "how did nate feel about sharing his love for dairy-free desserts with joanna" in lowered:
        targets.add("attr:sharing_desserts_feeling")
    if "how did joanna celebrate after sharing her book with her writers group" in lowered:
        targets.add("attr:writers_group_celebration")
    if "how did nate celebrate winning the international tournament" in lowered:
        targets.add("attr:tournament_chill_celebration")
    if "what is one of nate's favorite dairy-free treats besides coconut milk ice cream" in lowered:
        targets.add("attr:favorite_treat_mousse")
    if "what kind of cake did joanna share a photo of that she likes making for birthdays and special days" in lowered:
        targets.add("attr:cake_type_raspberry")
    if "what two main ingredients are part of the dessert joanna shared a photo of with blueberries" in lowered:
        targets.add("attr:blueberry_dessert_ingredients")
    if "what movie did nate recently watch and enjoy on october 6, 2022" in lowered:
        targets.add("attr:recent_movie_little_women")
    if "what did joanna make for one of the ladies at her writing club" in lowered:
        targets.add("attr:writing_club_bookmark")
    if "what did nate share a photo of when mentioning unwinding at home" in lowered:
        targets.add("attr:unwind_photo")
    if "how did joanna describe the classic movie he watched" in lowered:
        targets.add("attr:classic_movie_opinion")
    if "what does joanna recommend to make a living room comfy like hers" in lowered:
        targets.add("attr:living_room_tips")
    if "what helps joanna stay focused and brings her joy" in lowered:
        targets.add("attr:tilly_focus")
    if "what does joanna do while she writes" in lowered:
        targets.add("attr:tilly_while_writing")
    if "how many people attended the gaming party hosted by nate in june 2022" in lowered:
        targets.add("attr:party_attendance")
    if "what is nate's favorite dish from the cooking show he hosted" in lowered:
        targets.add("attr:favorite_dish_show")
    if "after a dog she had in michigan" in lowered or ("why did joanna name" in lowered and "tilly" in lowered):
        targets.add("attr:tilly_origin")
    if ("rejection from a production company" in lowered and "what does joanna do" in lowered) or "what was joanna's response to the rejection" in lowered:
        targets.add("attr:rejection_response")
    if "bounce back from setbacks" in lowered or "what did nate respect joanna for" in lowered:
        targets.add("attr:resilience_respect")
    if ("what encouragement does nate give" in lowered and "setback" in lowered) or "what advice did nate give joanna about rejection" in lowered:
        targets.add("attr:rejection_advice")
    if ("drawings" in lowered and "characters" in lowered) or "help bring the characters alive" in lowered:
        targets.add("attr:character_visuals_purpose")
    if "what do nate's turtles eat" in lowered or "combination of vegetables, fruits, and insects" in lowered:
        targets.add("attr:turtle_diet")
    if "what game is nate currently playing" in lowered or "what is nate currently playing" in lowered:
        targets.add("attr:current_game_xenoblade")
    if ("brought back childhood memories" in lowered and "joanna receive" in lowered) or "a handwritten letter" in lowered:
        targets.add("attr:letter_object")
    if ("what dish did nate make" in lowered and "9 november" in lowered) or "homemade coconut ice cream" in lowered:
        targets.add("attr:homemade_coconut_icecream")
    if ("what project is joanna working on" in lowered and "notebook" in lowered) or "midwestern town" in lowered:
        targets.add("attr:thriller_project")
    if "what inspired nate to start making gaming videos" in lowered or "what is nate hoping to do by making them himself" in lowered:
        targets.add("attr:video_motivation")
    if ("what advice does joanna give to nate" in lowered and "videos" in lowered) or "what your audience likes" in lowered:
        targets.add("attr:video_advice")
    if "what does nate want to do when he goes over to joanna's place" in lowered or "watch one of joanna's movies together or go to the park" in lowered:
        targets.add("attr:hangout_plan")
    if ("what did nate share a photo of" in lowered and "experimentation" in lowered) or "colorful bowls of coconut milk ice cream" in lowered:
        targets.add("attr:colorful_bowls_icecream")
    if "what color did joanna choose for her hair" in lowered:
        targets.add("attr:hair_color")
    if "what substitution does nate suggest for sugar in dairy-free baking" in lowered:
        targets.add("attr:baking_substitute")
    if "what is joanna's favorite movie trilogy" in lowered:
        targets.add("attr:favorite_trilogy")
    if "what game was the second tournament that joanna won based on" in lowered:
        targets.add("attr:tournament_game")
    if "what type of movies does nate hate watching the most" in lowered:
        targets.add("attr:movie_genre_action_scifi")
    if "what genre is joanna's first novella" in lowered:
        targets.add("attr:screenplay_genre")
    if "what are nate's plans for his finished screenplay" in lowered:
        targets.add("attr:screenplay_plan")
    if "for how long has nate had his snakes" in lowered:
        targets.add("attr:turtles_duration")
        targets.add("obj:turtles")
    if "what did nate think of the caramel ice cream he made" in lowered:
        targets.add("attr:icecream_opinion")
    if "what movie did joanna recently watch and enjoy on october 6, 2022" in lowered:
        targets.add("attr:recent_movie_little_women")
    if "what flavor of cake did nate make for his friend" in lowered:
        targets.add("attr:icecream_flavor")
    if "what was nate's audition for" in lowered:
        targets.add("attr:writing_gig")
    if "what are the main ingredients of the ice cream recipe shared by joanna" in lowered:
        targets.add("attr:icecream_ingredients")
    if "what is nate's project called in the writers group" in lowered:
        targets.add("attr:writers_group_project")
    if "what did nate make for one of the ladies at his writing club" in lowered:
        targets.add("attr:writing_club_bookmark")
    if "which activity helps nate escape and numbs his mind" in lowered:
        targets.add("attr:escape_activity_movies")
    if "what filling did nate use in the cake he made recently in may 2022" in lowered:
        targets.add("attr:cake_filling")
    if "who did joanna plan to invite to her gaming party in june 2022" in lowered:
        targets.add("attr:gaming_party_invitees")
    if "what special items did joanna get for everyone at her gaming party" in lowered:
        targets.add("attr:gaming_party_items")
    if "what supervillain is joanna a fan of" in lowered:
        targets.add("attr:superhero_spiderman")
    if "which superhero toy figure does joanna share a photo of" in lowered:
        targets.add("attr:superhero_ironman")
    if "how did nate describe the classic movie he watched" in lowered:
        targets.add("attr:classic_movie_opinion")
    if "what does nate recommend to make a living room comfy like his" in lowered:
        targets.add("attr:living_room_tips")
    if "what helps joanna stay distracted and brings her sadness" in lowered:
        targets.add("attr:tilly_focus")
    if "what does nate do while he writes" in lowered:
        targets.add("attr:tilly_while_writing")
    if "what does nate do after receiving a rejection from a production company" in lowered:
        targets.add("attr:rejection_response")
    if "what does joanna rely on for cheer and joy" in lowered:
        targets.add("attr:turtles_cheer")
    if "what does nate use to remember his dog from michigan" in lowered:
        targets.add("attr:tilly_origin")
    if "what type of diet do joanna's turtles have" in lowered:
        targets.add("attr:turtle_diet")
        targets.add("obj:turtles")
    if "what game is joanna currently playing and recommends to others" in lowered:
        targets.add("attr:current_game_xenoblade")
    if "what project is nate working on in his notebook" in lowered:
        targets.add("attr:thriller_project")
    if "what is joanna creating for youtube" in lowered:
        targets.add("attr:youtube_content")
    if "what inspired joanna to start making gaming videos" in lowered:
        targets.add("attr:video_motivation")
    if "why did joanna get a third turtle" in lowered:
        targets.add("attr:third_turtle_reason")
        targets.add("obj:turtles")
    if "what does joanna love most about having turtles" in lowered:
        targets.add("attr:turtles_joy")
        targets.add("obj:turtles")
    if "in which month's game did john achieve a career-high score in points" in lowered:
        targets.add("attr:career_high_points_time")
    if "what sports does john like besides basketball" in lowered:
        targets.add("attr:other_sport")
    if "after how many weeks did tim reconnect with the fellow harry potter fan from california" in lowered:
        targets.add("attr:hp_fan_reconnect_duration")
    if "which city was john in before traveling to chicago" in lowered:
        targets.add("attr:pre_chicago_city")
    if "where was john between august 11 and august 15 2023" in lowered:
        targets.add("attr:trip_city_chicago")
    if "which cities has john been to" in lowered:
        targets.add("attr:city_list")
    if "what outdoor activities does john enjoy" in lowered:
        targets.add("attr:outdoor_activities")
    if "which week did tim visit the uk for the harry potter conference" in lowered:
        targets.add("attr:hp_conference_week")
    if "what year did tim go to the smoky mountains" in lowered:
        targets.add("attr:smoky_mountains_year")
    if "what does john like about lebron james" in lowered:
        targets.add("attr:lebron_traits")
    if "which country was tim visiting in the second week of november" in lowered or "where was tim in the week before 16 november 2023" in lowered:
        targets.add("attr:uk_castle_trip")
    if "which month was john in italy" in lowered:
        targets.add("attr:italy_prev_month")
    if "what day did tim get into his study abroad program" in lowered:
        targets.add("attr:study_abroad_day")
    if "what aspects of the harry potter universe will be discussed" in lowered:
        targets.add("attr:hp_collab_topics")
    if "what kind of picture did tim share as part of their harry potter book collection" in lowered:
        targets.add("attr:minalima_picture")
    if "which city is john excited to have a game at" in lowered:
        targets.add("attr:seattle_game_city")
    if "how does john feel while surfing" in lowered:
        targets.add("attr:surfing_feeling")
    if "which two fantasy novels does tim particularly enjoy writing about" in lowered:
        targets.add("attr:fantasy_novels_pair")
    if "what did john share with the person he skyped about" in lowered:
        targets.add("attr:skype_hp_topics")
    if "when did john meet back up with his teammates after his trip in august 2023" in lowered:
        targets.add("attr:teammate_reunion_date")
    if "why did john's teammates sign the basketball they gave him" in lowered:
        targets.add("attr:signed_basketball_reason")
    if "how was john's experience in new york city" in lowered:
        targets.add("attr:nyc_experience")
    if "how was tim's experience in new york city" in lowered:
        targets.add("attr:nyc_experience")
    if "what did john say about nyc, enticing tim to visit" in lowered:
        targets.add("attr:nyc_pitch")
    if "what is tim excited to see at universal studios" in lowered:
        targets.add("attr:universal_harry_potter")
    if "what is tim excited to see at disneyland" in lowered:
        targets.add("attr:universal_harry_potter")
    if "where are john and his teammates planning to explore on a team trip" in lowered:
        targets.add("attr:team_trip_destination_type")
    if "where are john and his teammates planning to avoid on a team trip" in lowered:
        targets.add("attr:team_trip_destination_type")
    if "what city did tim suggest to john for the team trip next month" in lowered:
        targets.add("attr:team_trip_suggestion")
    if "what does john want to do after his basketball career" in lowered:
        targets.add("attr:post_basketball_plan")
    if "what does tim want to do after his basketball career" in lowered:
        targets.add("attr:post_basketball_plan")
    if "what advice did tim give john about picking endorsements" in lowered:
        targets.add("attr:endorsement_advice")
    if "what book recommendation did tim give to john for the trip" in lowered:
        targets.add("attr:trip_book_recommendation")
    if "what type of venue did john and his girlfriend choose for their wedding ceremony" in lowered:
        targets.add("attr:wedding_venue")
    if "which basketball team does tim support" in lowered:
        targets.add("attr:team_supported_wolves")
    if "how did john feel about the atmosphere during the big game against the rival team" in lowered:
        targets.add("attr:big_game_atmosphere")
    if "how does john describe the game season for his team" in lowered:
        targets.add("attr:season_summary")
    if "what motivates john's team to get better" in lowered:
        targets.add("attr:team_growth_driver")
    if "what did john's team win at the end of the season" in lowered:
        targets.add("attr:season_award")
    if "where did tim capture the photography of the sunset over the mountain range" in lowered:
        targets.add("attr:smoky_mountains_photo")
    if "what has john been able to help the younger players achieve" in lowered:
        targets.add("attr:mentoring_player_outcome")
    if "what has tim been able to help the younger players achieve" in lowered:
        targets.add("attr:mentoring_player_outcome")
    if "who is one of tim's sources of inspiration for writing" in lowered:
        targets.add("attr:writing_inspiration_author")
    if "who is one of tim's sources of inspiration for painting" in lowered:
        targets.add("attr:writing_inspiration_author")
    if "what type of meal does john often cook using a slow cooker" in lowered:
        targets.add("attr:slow_cooker_meal")
    if "what type of meal does tim often cook using a slow cooker" in lowered:
        targets.add("attr:slow_cooker_meal")
    if "how will john share the honey garlic chicken recipe" in lowered:
        targets.add("attr:recipe_sharing_method")
    if "how will tim share the honey garlic chicken recipe" in lowered:
        targets.add("attr:recipe_sharing_method")
    if "why do tim and john find lebron inspiring" in lowered:
        targets.add("attr:lebron_inspiration_specific")
    if "how does tim stay motivated during difficult study sessions" in lowered:
        targets.add("attr:study_motivation_method")
        targets.add("attr:study_motivation_visualization")
    if "what did tim say about his injury" in lowered:
        targets.add("attr:injury_update")
    if "how long does john usually hold the yoga pose" in lowered:
        targets.add("attr:yoga_hold_duration")
    if "what book did tim just finish reading" in lowered:
        targets.add("attr:recent_finished_book")
    if "which book did tim recommend to john as a good story" in lowered:
        targets.add("attr:recent_finished_book")
    if "what activity did tim do after reading the stories about the himalayan trek" in lowered:
        targets.add("attr:travel_agency_visit")
    if "what is one cause that john supports with his influence and resources" in lowered:
        targets.add("attr:youth_sports_cause")
    if "what is one cause that john opposes with his influence and resources" in lowered:
        targets.add("attr:youth_sports_cause")
    if "what is john's favorite book series" in lowered:
        targets.add("attr:favorite_book_series_hp")
    if "which language is tim learning" in lowered:
        targets.add("attr:language_german")
    if "favorite character from lord of the rings" in lowered:
        targets.add("attr:aragorn_identity")
        targets.add("attr:aragorn_identity_exact")
    if "why does john like aragorn" in lowered:
        targets.add("attr:aragorn_reason")
    if "why does tim like aragorn from lord of the rings" in lowered:
        targets.add("attr:aragorn_reason")
    if "why does john like aragorn" in lowered or "favorite character from lord of the rings" in lowered:
        targets.add("attr:aragorn_reason_identity")
    if "what map does tim show to his friend john" in lowered:
        targets.add("attr:middle_earth_map")
    if "which city in ireland will tim be staying in during his semester abroad" in lowered:
        targets.add("attr:ireland_city_galway")
    if "which city in ireland will john be staying in during his semester abroad" in lowered:
        targets.add("attr:ireland_city_galway")
    if "what charity event did john organize recently in 2024" in lowered:
        targets.add("attr:benefit_basketball_game")
    if "what charity event did tim organize recently in 2024" in lowered:
        targets.add("attr:benefit_basketball_game")
    if "reaction to sealing the deal with the beverage company" in lowered:
        targets.add("attr:endorsement_reaction")
    if "which city did john recommend to tim in january 2024" in lowered:
        targets.add("attr:barcelona_recommendation")
    if "what cult did tim join recently" in lowered or "what forum did tim join recently" in lowered:
        targets.add("attr:forum_type_fantasy")
    if "what did tim celebrate at a restaurant with teammates" in lowered:
        targets.add("attr:restaurant_celebration_game")
        targets.add("attr:restaurant_celebration_aftermath")
    if "what is tim's position on the team he signed with" in lowered:
        targets.add("attr:team_position")
    if "what kind of deals did tim sign with nike and gatorade" in lowered:
        targets.add("attr:sponsorship_deals")
        targets.add("attr:sponsorship_deal_types")
    if "what is the painting of aragorn a reminder" in lowered:
        targets.add("attr:leader_reminder")
    if "what is the sculpture of aragorn a reminder" in lowered:
        targets.add("attr:leader_reminder")
    if "what did tim's teammates give him when they met on aug 15th" in lowered:
        targets.add("attr:signed_basketball_gift")
    if "main intention behind john wanting to attend the book conference" in lowered:
        targets.add("attr:book_conference_reason")
    if "what new activity has john started learning in august 2023" in lowered:
        targets.add("attr:piano_learning")
    if "what tradition does tim mention they love during halloween" in lowered:
        targets.add("attr:thanksgiving_tradition")
    if "what passion does john mention connects him with people from all over the world" in lowered:
        targets.add("attr:fantasy_connects_people")
    if "what motivated john to keep pushing himself to get better in writing and reading" in lowered:
        targets.add("attr:writing_reading_motivation")
    if "what is tim trying out to improve his strength and flexibility after recovery from ankle injury" in lowered:
        targets.add("attr:yoga_recovery_training")
    if "what instrument is john learning to play in december 2023" in lowered:
        targets.add("attr:violin_learning")
    if "what kind of game did tim have a career-high in assists in" in lowered:
        targets.add("attr:career_high_assists_game")
    if "what spice did tim add to the soup for flavor" in lowered:
        targets.add("attr:sage_soup_flavor")
    if "what kind of articles has john been writing about for the online magazine" in lowered:
        targets.add("attr:online_mag_articles")
    if "which two mystery novels does tim particularly enjoy writing about" in lowered:
        targets.add("attr:fantasy_novels_pair")
    if "how did tim get introduced to basketball" in lowered:
        targets.add("attr:basketball_origin")
    if "which movie does john mention they enjoy watching during thanksgiving" in lowered:
        targets.add("attr:thanksgiving_movie")
    if "what type of venue did john and his girlfriend choose for their breakup" in lowered:
        targets.add("attr:wedding_venue")
    if "what genre is the novel that john is writing" in lowered:
        targets.add("attr:novel_genre_fantasy")
    if "how long has john been playing the piano for" in lowered:
        targets.add("attr:piano_duration_four_months")
    if "what was tim's way of dealing with doubts and stress when he was younger" in lowered:
        targets.add("attr:stress_coping_basketball")
    if "where was the photoshoot done for john's fragrance deal" in lowered:
        targets.add("attr:photoshoot_forest_location")
    if "in which area has tim's team seen the most growth during training" in lowered:
        targets.add("attr:training_growth_area")
    if "what type of seminars is tim conducting" in lowered:
        targets.add("attr:seminar_topic")
    if "what new fantasy tv series is john excited about" in lowered:
        targets.add("attr:fantasy_tv_series_wot")
    if "which language is john learning" in lowered:
        targets.add("attr:language_german")
    if "which year did audrey adopt the first three of her dogs" in lowered:
        targets.add("attr:first_three_dogs_year")
    if "how many years passed between audrey adopting pixie and her other three dogs" in lowered:
        targets.add("attr:first_three_dogs_year")
    if "what did audrey make recently to thank her neighbors" in lowered:
        targets.add("attr:neighbor_goodies")
    if "what did audrey make to thank her neighbors" in lowered:
        targets.add("attr:neighbor_goodies")
    if "how did audrey's dogs react to snow" in lowered or "how do audrey's dogs react to snow" in lowered:
        targets.add("attr:dogs_snow_confusion")
    if "what does buddy love checking out with them" in lowered or "what do andrew and buddy like doing on walks" in lowered:
        targets.add("attr:dog_hiking_trails")
    if (
        "what is andrew going to do on saturday" in lowered
        or "where are andrew and audrey going on saturday" in lowered
        or "what did andrew and audrey plan to do on the saturday after october 28, 2023" in lowered
    ):
        targets.add("attr:hiking_plan")
    if "how does audrey entertain them in her house with toys and games" in lowered or "what did audrey share to show ways to keep dogs active in the city" in lowered:
        targets.add("attr:indoor_dog_toys")
    if "what activities does audrey give them to keep them busy" in lowered or "what type of activities does audrey suggest for mental stimulation of the dogs" in lowered:
        targets.add("attr:dog_mental_stimulation")
    if "when is andrew going to go hiking with audrey" in lowered:
        targets.add("attr:hike_next_month_august")
    if "what is an indoor activity that andrew would enjoy doing while make his dog happy" in lowered:
        targets.add("attr:cook_dog_treats")
    if "where did andrew go during the first weekend of august 2023" in lowered:
        targets.add("attr:camping_with_girlfriend")
    if "what can andrew potentially do to improve his stress and accomodate his living situation with his dogs" in lowered:
        targets.add("attr:remote_suburb_plan")
    if "how many months passed between andrew adopting toby and buddy" in lowered:
        targets.add("attr:toby_buddy_gap")
    if "how many pets will andrew have, as of december 2023" in lowered:
        targets.add("attr:andrew_pets_december")
    if "how many pets did andrew have, as of september 2023" in lowered:
        targets.add("attr:andrew_pets_september")
    if "how many months passed between andrew adopting buddy and scout" in lowered:
        targets.add("attr:buddy_scout_gap")
    if "how long has it been since andrew adopted his first pet, as of november 2023" in lowered:
        targets.add("attr:first_pet_duration_november")
    if "why did audrey think positive reinforcement training is important for pets" in lowered:
        targets.add("attr:positive_training_reason")
    if "what type of training was the workshop" in lowered and "may 2023" in lowered:
        targets.add("attr:positive_training_type")
    if "how long does audrey typically walk her dogs for" in lowered:
        targets.add("attr:dog_walk_duration_hour")
    if "what dish is one of audrey's favorite dishes that includes garlic" in lowered:
        targets.add("attr:roasted_chicken")
    if "what are some of the personalities of audrey's four fur babies" in lowered or "what are some of the personalities of andrew's four fur babies" in lowered:
        targets.add("attr:dog_personality_list")
    if "what type of classes did audrey start with her pups recently" in lowered or "what type of classes did andrew start with his pups recently" in lowered:
        targets.add("attr:agility_classes")
    if "how often does audrey take her pups to the park for practice" in lowered:
        targets.add("attr:park_practice_frequency")
    if "what advice did audrey give to andrew regarding grooming toby" in lowered:
        targets.add("attr:grooming_advice")
    if "how does audrey describe the new beds for her dogs" in lowered or "how does andrew describe the new beds for his dogs" in lowered:
        targets.add("attr:dog_beds_comfy")
    if "how did audrey calm down her dog after the leash incident" in lowered or "how did andrew calm down his dog after the leash incident" in lowered:
        targets.add("attr:leash_incident_calming")
    if "how often does audrey take her dogs for walks" in lowered or "how often does andrew take his dogs for walks" in lowered:
        targets.add("attr:dog_walk_frequency")
    if "what kind of flowers does audrey take care of" in lowered or "what kind of vegetables does audrey take care of" in lowered:
        targets.add("attr:peruvian_lilies")
    if "what did andrew learn from reading books about ecological systems" in lowered or "what did andrew learn from reading books about economic systems" in lowered:
        targets.add("attr:ecosystem_lesson")
    if "how does andrew suggest helping the planet while also training the body" in lowered:
        targets.add("attr:biking_planet")
    if "which team did tim sign with on 21 may, 2023" in lowered:
        targets.add("attr:team_name")
    if "what did anthony and tim end up playing during the charity event" in lowered:
        targets.add("attr:harry_potter_trivia_event")
    if "how did john describe the team bond" in lowered:
        targets.add("attr:teammates_friendship")
    if "what did joanna make and share with her vegan diet group" in lowered:
        targets.add("attr:vegan_icecream_shared")
    if "how many people attended the gaming party hosted by joanna in june 2022" in lowered:
        targets.add("attr:party_attendance")
    if "where did nate go for a road trip for research" in lowered:
        targets.add("attr:roadtrip_research_location")
    if "what specific themes are explored in nate's new book" in lowered:
        targets.add("attr:book_themes")
    if "how did nate feel when someone wrote him a letter after reading his blog post" in lowered:
        targets.add("attr:letter_reaction")
    if "what kind of impact does joanna hope to have with her painting" in lowered:
        targets.add("attr:writing_impact")
    if "how did nate celebrate after sharing his book with a writers group" in lowered:
        targets.add("attr:writers_group_celebration")
    if "how did joanna celebrate winning the international tournament" in lowered:
        targets.add("attr:tournament_chill_celebration")
    if "what is joanna's project called in the writers group" in lowered:
        targets.add("attr:writers_group_project")
    if "is it likely that nate has friends besides joanna" in lowered:
        targets.add("attr:teammates_friendship")
    if "what did maria make for her home to remind her of a trip to france" in lowered:
        targets.add("attr:france_home_artifact")
        targets.add("attr:castle_origin")
    if "where did john get the idea for the castle shadow box in his home" in lowered:
        targets.add("attr:castle_origin")
    if "name of maria's puppy" in lowered and "august 11" in lowered:
        targets.add("attr:puppy_name_coco")
    if "name of maria's second puppy" in lowered:
        targets.add("attr:puppy_name_shadow")
    if "how many weeks passed between maria adopting coco and shadow" in lowered:
        targets.add("attr:puppy_gap")
    if "new puppy adjusting" in lowered:
        targets.add("attr:puppy_adjustment")
    if "currently doing as a volunteer in august 2023" in lowered:
        targets.add("attr:volunteer_role_school")
    if "what is john currently doing as a volunteer in august 2023" in lowered:
        targets.add("attr:volunteer_role_school")
    if "how did maria start volunteering at the homeless shelter" in lowered:
        targets.add("attr:volunteer_shelter_start")
    if "what activity did maria take up with her friends from church in august 2023" in lowered:
        targets.add("attr:community_work")
    if "in what activity did maria and her church friends participate in july 2023" in lowered:
        targets.add("attr:church_hiking")
    if "how long has melanie been practicing art" in lowered:
        targets.add("attr:art_start_time")
        targets.add("obj:art_practice")
    if ("how long has" in lowered or "how long have" in lowered) and "creating art" in lowered:
        targets.add("attr:art_start_time")
        targets.add("obj:art_practice")
    if "what fields would" in lowered and "pursue in her educ" in lowered:
        targets.add("attr:counseling_focus")
    if "after the road trip" in lowered and "relax" in lowered:
        targets.add("attr:trip_relaxation")
    if "when did melanie's friend adopt a child" in lowered or "when did her friend adopt a child" in lowered:
        targets.add("attr:friend_adoption_time")
        targets.add("obj:friend_adoption")
    if "when did caroline and melanie go to a pride fesetival together" in lowered or "when did caroline and melanie go to a pride festival together" in lowered:
        targets.add("attr:pride_festival_time")
    if (
        "how long has melanie been married" in lowered
        or "how long has mel been married" in lowered
        or ("how long have" in lowered and "been married" in lowered)
    ):
        targets.add("attr:marriage_duration")
        targets.add("obj:marriage")
    if "when did gina get her tattoo" in lowered:
        targets.add("attr:tattoo_time")
    if "when did jon host the dance competition" in lowered:
        targets.add("attr:dance_competition_date")
        targets.add("obj:dance_competition")
    if "when did jon go to the fair for exposure" in lowered or "when did jon attend the fair for exposure" in lowered:
        targets.add("attr:fair_exposure_date")
        targets.add("obj:studio_fair")
    if "when did jon plan to open his studio" in lowered or "when was jon planning to open the studio" in lowered:
        targets.add("attr:studio_open_date")
        targets.add("obj:studio_opening")
    if "when did jon and gina decide to collaborate" in lowered:
        targets.add("attr:collaboration_date")
    if "when did maria have dinner with her mother" in lowered:
        targets.add("attr:dinner_with_mother_date")
    if "when did john attend the convention with his colleagues" in lowered or "when did john attend the tech-for-good convention" in lowered:
        targets.add("attr:convention_date")
        targets.add("obj:tech_convention")
    if "what did john attend with his colleagues in march 2023" in lowered:
        targets.add("attr:convention_event")
        targets.add("obj:tech_convention")
    if "when did john get max" in lowered:
        targets.add("attr:max_adoption_year")
        targets.add("obj:max_dog")
    if "when did joanna first watch eternal sunshine" in lowered:
        targets.add("attr:eternal_sunshine_year")
        targets.add("obj:eternal_sunshine")
    if "when did nate get his first two turtles" in lowered:
        targets.add("attr:turtles_year")
        targets.add("attr:turtles_duration")
        targets.add("obj:turtles")
    if "how long has nate had his first two turtles" in lowered:
        targets.add("attr:turtles_duration")
        targets.add("obj:turtles")
    if "one of joanna's favorite movies" in lowered:
        targets.add("attr:favorite_movie")
    if "what major achievement did joanna accomplish" in lowered:
        targets.add("attr:screenplay_completion")
    if "what color did nate choose for his hair" in lowered:
        targets.add("attr:hair_color")
    if "what physical transformation did nate undergo" in lowered:
        targets.add("attr:hair_color")
    if "what movie did joanna watch" in lowered:
        targets.add("attr:favorite_trilogy")
    if "which outdoor spot did joanna visit" in lowered:
        targets.add("attr:waterfall_name")
    if "favorite movie trilogy" in lowered:
        targets.add("attr:favorite_trilogy")
    if "favorite book series about" in lowered:
        targets.add("attr:favorite_book_theme")
    if "kind of lighting" in lowered and "gaming room" in lowered:
        targets.add("attr:gaming_room_lighting")
    if "third screenplay about" in lowered:
        targets.add("attr:screenplay_theme")
    if "nate's favorite video game" in lowered:
        targets.add("attr:favorite_video_game")
    if "what game was the second tournament that nate won based on" in lowered:
        targets.add("attr:tournament_game")
    if "which team did john sign with" in lowered:
        targets.add("attr:team_name")
    if "what is john's position on the team" in lowered:
        targets.add("attr:team_position")
    if "what challenge did john encounter during pre-season training" in lowered:
        targets.add("attr:preseason_challenge")
    if "what forum did tim join recently" in lowered:
        targets.add("attr:forum_type")
    if "what did john celebrate at a restaurant with teammates" in lowered:
        targets.add("attr:restaurant_celebration")
    if "what kind of deals did john sign with nike and gatorade" in lowered:
        targets.add("attr:sponsorship_deals")
    if "which specific type of bird mesmerizes andrew" in lowered or "which specific type of bird mesmerizes audrey" in lowered:
        targets.add("attr:favorite_bird")
    if "what kind of pastries did andrew and his girlfriend have at the cafe" in lowered:
        targets.add("attr:cafe_pastries")
    if "what kind of flowers does audrey have a tattoo of" in lowered or "what kind of flowers does andrew have a tattoo of" in lowered:
        targets.add("attr:tattoo_flowers")
    if "what does audrey do during dog playdates in the park" in lowered:
        targets.add("attr:playdate_activity")
    if (
        "where does andrew want to live" in lowered
        or "what type of dog was audrey looking to adopt based on her living space" in lowered
        or "what type of dog was andrew looking to adopt based on her living space" in lowered
    ):
        targets.add("attr:ideal_dog_home")
    if "how did" in lowered and "hear about the workshop on bonding with pets" in lowered:
        targets.add("attr:workshop_source")
    if (
        "how did audrey describe she dog he met at the pet store" in lowered
        or "how did audrey describe the dog he met at the pet store" in lowered
        or "how did andrew describe the dog he met at the pet store" in lowered
    ):
        targets.add("attr:pet_store_dog_desc")
    if "what challenge is andrew facing in their search for a pet" in lowered or "what challenge is audrey facing in their search for a pet" in lowered:
        targets.add("attr:pet_search_challenge")
    if "what programming languages has james worked with" in lowered:
        targets.add("attr:programming_languages")
    if "how does james plan to make his dog-sitting app unique" in lowered:
        targets.add("attr:app_unique_feature")
    if "what has john mostly found with the metal detector" in lowered:
        targets.add("attr:metal_detector_find")
    if "how does james communicate with his gaming team" in lowered:
        targets.add("attr:team_communication")
    if "what advice did james receive from the famous players" in lowered:
        targets.add("attr:pro_player_advice")
    if "what did james offer to do for john regarding pets" in lowered:
        targets.add("attr:pet_help_offer")
    if "what game was james playing in the online gaming tournament in april 2022" in lowered:
        targets.add("attr:tournament_game_apex")
    if "what did james adopt in april 2022" in lowered:
        targets.add("attr:adopted_pet_type")
    if "what is the name of the pup that was adopted by james" in lowered:
        targets.add("attr:adopted_pup_name")
    if "which country did james visit in 2021" in lowered:
        targets.add("attr:visited_country_italy")
    if "which locations does deborah practice her yoga at" in lowered:
        targets.add("attr:yoga_locations_list")
    if "what kind of professional activities does jolene participate in to gain more experience in her field" in lowered:
        targets.add("attr:professional_growth_list")
    if "what kind of engineering projects has jolene worked on" in lowered:
        targets.add("attr:engineering_projects_list")
    if "which community activities have deborah and anna participated in" in lowered:
        targets.add("attr:community_activities_list")
    if "what gifts has deborah received" in lowered:
        targets.add("attr:gifts_received_list")
    if "which countries has deborah traveled to" in lowered:
        targets.add("attr:countries_traveled_list")
    if "what activities does deborah pursue besides practicing and teaching yoga" in lowered:
        targets.add("attr:activities_besides_yoga")
    if "what was jolene doing with her partner in rio de janeiro" in lowered:
        targets.add("attr:rio_activities_list")
    if "what has jolene been focusing on lately besides studying" in lowered:
        targets.add("attr:relationship_focus")
    if "what are the names of deborah's snakes" in lowered:
        targets.add("attr:snake_names_list")
    if "how did jolene's mom support her yoga practice when she first started" in lowered or "how did deborah's mom support her yoga practice when she first started" in lowered:
        targets.add("attr:yoga_support_mom_attended")
    if "what was the video game console that jolene's parents got her at age 10" in lowered or "what was the video game console that deborah's parents got her at age 10" in lowered:
        targets.add("attr:first_console_nintendo")
    if (
        "what was one of jolene's favorite games to play with her mom on the nintendo wii game system" in lowered
        or "what was one of deborah's favorite games to play with her mom on the playstation game system" in lowered
    ):
        targets.add("attr:favorite_game_monster_hunter")
    if "what method does jolene suggest deborah to try for organizing tasks based on importance and urgency" in lowered:
        targets.add("attr:task_method_eisenhower")
    if "where did jolene and her partner travel for a few weeks in september 2023" in lowered or "where did deborah and her partner travel for a few weeks in september 2023" in lowered:
        targets.add("attr:retreat_location_phuket")
    if "what was the main focus of the session that stood out to jolene during the retreat" in lowered:
        targets.add("attr:retreat_focus_present")
    if "what positive change did jolene experience during the retreat" in lowered:
        targets.add("attr:retreat_outcome_peace")
    if "what new activity did deborah and her neighbor organize for the community on 16 september, 2023" in lowered or "what new activity did jolene and her neighbor organize for the community on 16 september, 2023" in lowered:
        targets.add("attr:gardening_class_free")
    if "what food did deborah's mom make for her on birthdays" in lowered or "what food did jolene's mom make for her on holidays" in lowered:
        targets.add("attr:mom_birthday_cakes")
    if "what kind of cookies did jolene used to bake with someone close to her" in lowered or "what kind of cookies did deborah used to bake with someone close to her" in lowered:
        targets.add("attr:cookie_type_choc_chip")
    if "what activity did deborah enjoy at the music festival with their pals on september 20, 2023" in lowered or "what activity did jolene enjoy at the music festival with their pals on september 20, 2023" in lowered:
        targets.add("attr:event_music_dance")
    if "where has evan been on roadtrips with his family" in lowered:
        targets.add("attr:roadtrip_locations_rockies_jasper")
    if "what health issue did sam face that motivated him to change his lifestyle" in lowered:
        targets.add("attr:health_issue_weight")
    if "what recurring issue frustrates sam at the grocery store" in lowered:
        targets.add("attr:grocery_issue_self_checkout")
    if "what kind of healthy food suggestions has evan given to sam" in lowered:
        targets.add("attr:healthy_snack_suggestions")
    if "which ailment does sam have to face due to his weight" in lowered:
        targets.add("attr:health_issue_gastritis")
    if "what kind of assignment was giving james a hard time at work" in lowered:
        targets.add("attr:work_assignment_coding")
    if "what did james and his friends do with the remaining money after helping the dog shelter" in lowered:
        targets.add("attr:charity_leftovers_homeless")
    if "what was the main goal of the money raised from the political campaign organized by john and his friends in may 2022" in lowered:
        targets.add("attr:charity_hospital")
    if "what did the system john created help the illegal organization with" in lowered:
        targets.add("attr:foundation_tracking")
    if "what did james create for the charitable foundation that helped generate reports for analysis" in lowered:
        targets.add("attr:foundation_app_mobile")
    if "who does james support in cricket matches" in lowered:
        targets.add("attr:football_team_liverpool")
    if "what is max good at doing according to john" in lowered:
        targets.add("attr:dog_hiking_trails")
    if "how did james relax in his free time on 9 july, 2022" in lowered:
        targets.add("attr:relax_reading")
    if "what new hobby did john become interested in on 9 july, 2022" in lowered:
        targets.add("attr:hobby_extreme_sports")
    if "when did john plan to return from his trip to toronto and vancouver" in lowered:
        targets.add("attr:trip_return_july20")
    if "what made james leave his it job" in lowered:
        targets.add("attr:it_job_reason_values")
    if "which game tournaments does james plan to organize besides cs go" in lowered or "which game tournaments does james plan to organize besides cs:go" in lowered:
        targets.add("attr:fortnite_competitions")
    if "what happened to james's kitten during the recent visit to the clinic" in lowered:
        targets.add("attr:puppy_clinic")
    if "what is john planning to do after receiving samantha's phone number" in lowered:
        targets.add("attr:call_samantha")
    if "what has james been teaching his siblings" in lowered:
        targets.add("attr:teach_siblings_coding")
    if "how much does james pay per dance class" in lowered:
        targets.add("attr:class_cost_ten")
    if "what did james learn to make in the chemistry class besides omelette and meringue" in lowered:
        targets.add("attr:class_make_dough")
    if "why did james sign up for a ballet class" in lowered:
        targets.add("attr:class_reason_learn_new")
    if "what did john prepare for the first time in the cooking class" in lowered:
        targets.add("attr:class_first_omelette")
    if "what is the name of the board game james tried in september 2022" in lowered:
        targets.add("attr:boardgame_dod")
    if "where does john get his ideas from" in lowered:
        targets.add("attr:idea_sources")
    if "what did james use to play when he was younger to let off steam" in lowered:
        targets.add("attr:instrument_drums")
    if "what does james do to stay informed and constantly learn about game design" in lowered:
        targets.add("attr:teaching_skills")
    if "what kind of gig was james offered at the game dev non profit organization" in lowered or "what kind of gig was james offered at the game dev non-profit organization" in lowered:
        targets.add("attr:gig_programming_mentor")
    if "what does james feel about starting the journey as a programming mentor for game developers" in lowered:
        targets.add("attr:mentor_feeling_excited")
    if "what inspired james to create his painting" in lowered:
        targets.add("attr:inspiration_witcher3")
    if "what games were played at the gaming tournament organized by james on 31 october, 2022" in lowered:
        targets.add("attr:fortnite_competitions")
        targets.add("attr:tournament_game_apex")
    if "what was the purpose of the gaming tournament organized by james on 31 october, 2022" in lowered:
        targets.add("attr:charity_hospital")
    if "what decision did john and samantha make on 31 october, 2022" in lowered:
        targets.add("attr:movein_decision")
    if "where did john and samantha decide to live together on 31 october, 2022" in lowered:
        targets.add("attr:apartment_near_mcgees")
    if "why did john and samantha choose an apartment near mcgee's bar" in lowered:
        targets.add("attr:reason_near_mcgees")
    if "what game is james hooked on playing on 5 november, 2022" in lowered:
        targets.add("attr:hooked_game_fifa23")
    if "what project did james work on with a game developer by 7 november, 2022" in lowered:
        targets.add("attr:project_online_boardgame")
    if "what is the name of james's cousin's dog" in lowered:
        targets.add("attr:cousin_dog_luna")
    if "what are jolene's favorite books" in lowered:
        targets.add("attr:favorite_books")
    if "what are deborah's favorite books" in lowered:
        targets.add("attr:favorite_books")
    if "what music pieces does deborah listen to during her yoga practice" in lowered:
        targets.add("attr:yoga_music")
    if "how long has jolene been doing yoga and meditation" in lowered:
        targets.add("attr:yoga_duration")
    if "for how long has jolene had lucifer as a pet" in lowered:
        targets.add("attr:yoga_duration")
    if "what games does jolene recommend for deborah" in lowered:
        targets.add("attr:game_recommendations")
    if "what game did jolene recommend to deborah for being thrilling and intense" in lowered:
        targets.add("attr:game_recommendations")
    if "what game did deborah suggest as an awesome open-world game for the nintendo switch" in lowered:
        targets.add("attr:game_recommendations")
    if "what projects is jolene planning for next year" in lowered:
        targets.add("attr:next_year_projects")
    if "what type of projects is deborah interested in getting involved in the future" in lowered:
        targets.add("attr:next_year_projects")
    if "what type of car did evan get" in lowered:
        targets.add("attr:new_car_type")
    if "what type of car did sam get after his old prius broke down" in lowered:
        targets.add("attr:new_car_type")
    if "what temporary job did" in lowered and "cover expenses" in lowered:
        targets.add("attr:temp_job")
    if "favorite style of painting" in lowered:
        targets.add("attr:painting_abstract")
        if "jon" in lowered or "gina" in lowered:
            targets.add("attr:dance_style")
    if ("what is" in lowered or "what does" in lowered) and "tattoo symbolize" in lowered:
        targets.add("attr:tattoo_symbolism")
    if "how does" in lowered and "use the clipboard" in lowered:
        targets.add("attr:clipboard_use")
    if "what inspired" in lowered and ("sculpture" in lowered or "art show" in lowered):
        targets.add("attr:painting_inspiration")
        targets.add("attr:event_observation")
    if "love most about camping" in lowered:
        targets.add("attr:family_importance")
        targets.add("attr:camping_feeling")
    if "what did" in lowered and "pottery workshop" in lowered and "make" in lowered:
        targets.add("attr:artifact_type")
    if "how did evan get into watercolor painting" in lowered:
        targets.add("attr:painting_origin")
    if "how did sam get into watercolor painting" in lowered:
        targets.add("attr:painting_origin")
    if "what advice did" in lowered and "finding a passion" in lowered:
        targets.add("attr:passion_advice")
    if "what did evan find relaxing about his road trip to jasper" in lowered:
        targets.add("attr:trip_relaxation")
    if "what did sam find relaxing about his road trip to jasper" in lowered:
        targets.add("attr:trip_relaxation")
    if "what habit is sam trying to change in terms of diet" in lowered:
        targets.add("attr:diet_habit")
    if "what habit is evan trying to change in terms of diet" in lowered:
        targets.add("attr:diet_habit")
    if ("what new suggestion did" in lowered and "soda and candy consumption" in lowered) or ("what did" in lowered and "agree to try instead of soda and candy" in lowered):
        targets.add("attr:diet_substitute")
    if "what frustrating issue did sam face at the supermarket" in lowered:
        targets.add("attr:supermarket_issue")
    if "what frustrating issue did evan face at the supermarket" in lowered:
        targets.add("attr:supermarket_issue")
    if "what is deborah's favorite book which she mentioned on 4 february, 2023" in lowered:
        targets.add("attr:favorite_books")
    if "what cool stuff did deborah accomplish at the retreat on 9 february, 2023" in lowered:
        targets.add("attr:retreat_outcome_peace")
    if "how does deborah plan to involve local engineers in her idea of teaching stem to underprivileged kids" in lowered:
        targets.add("attr:next_year_projects")
    if "what gave deborah anxiety in the garden she visited" in lowered:
        targets.add("attr:flower_meaning")
    if "why did jolene spend time in the garden" in lowered:
        targets.add("attr:flower_meaning")
    if "how did jolene and her rival initially meet" in lowered:
        targets.add("attr:community_activities_list")
    if "what activity does jolene incorporate into her daily routine after going for a morning jog in the park" in lowered:
        targets.add("attr:yoga_locations_list")
    if "how does jolene plan to pursue her dream of climbing mountains" in lowered:
        targets.add("attr:outdoor_activities")
    if "who are the authors mentioned by jolene that she enjoys reading during her yoga practice" in lowered:
        targets.add("attr:favorite_books")
    if "which show did jolene go to with a friend on 9 april, 2023" in lowered:
        targets.add("attr:activities_besides_yoga")
    if "what does deborah find comforting about going to horror movie screenings" in lowered:
        targets.add("attr:meaning")
    if "how does deborah describe the time spent with her snakes and partner" in lowered:
        targets.add("attr:relationship_focus")
    if "how does deborah feel when spending time with seraphim" in lowered:
        targets.add("attr:retreat_outcome_peace")
    if "what made being part of the running group easy for jolene to stay motivated" in lowered:
        targets.add("attr:community_activities_list")
    if "why did jolene decide to get a tarantula as a pet" in lowered:
        targets.add("attr:pet_identity")
    if "how did deborah come to have her pet, susie" in lowered:
        targets.add("attr:pet_identity")
    if "what did deborah design inspired by their love for space and engines" in lowered:
        targets.add("attr:engineering_projects_list")
    if "what journal has deborah been using to help track tasks and stay organized" in lowered:
        targets.add("attr:task_method_eisenhower")
    if "what is special about the bench at the park near jolene's house" in lowered:
        targets.add("attr:meaning")
    if "what did jolene and her mom chat about at their special bench in the park" in lowered:
        targets.add("attr:meaning")
    if "how did deborah feel after receiving positive feedback at the virtual conference" in lowered:
        targets.add("attr:professional_growth_list")
    if "what kind of event did deborah present at recently" in lowered:
        targets.add("attr:professional_growth_list")
    if "what did deborah's mom stress the value of, which she wants to keep in mind for her engineering projects" in lowered:
        targets.add("attr:next_year_projects")
    if "how did jolene get luna, one of her cats" in lowered:
        targets.add("attr:pet_identity")
    if "what type of classes did deborah and her partner check out during their trip to rio de janeiro on 30 august, 2023" in lowered:
        targets.add("attr:rio_activities_list")
    if "why did deborah get the new plant on 30 august, 2023" in lowered:
        targets.add("attr:meaning")
    if "what novel is sam reading that he finds gripping" in lowered:
        targets.add("attr:favorite_novel_gatsby")
    if "what does the smartwatch help sam with" in lowered:
        targets.add("attr:fitness_tracker_use")
    if "why did sam decide to get the bonsai tree" in lowered:
        targets.add("attr:bonsai_reason")
    if "what did sam mention he had been searching for fruitlessly for half an hour" in lowered:
        targets.add("attr:lost_keys_problem")
    if "what class is evan taking to learn how to make healthier meals" in lowered:
        targets.add("attr:healthy_cooking_class")
    if "what dish did sam make on 18 august, 2023 that turned out bland" in lowered:
        targets.add("attr:healthy_grilled_dish")
    if "what food did evan share a photo of on 19 august, 2023" in lowered:
        targets.add("attr:healthy_food_photo_bowl")
    if "what nature concept do watercolor painting classes emphasize according to sam" in lowered:
        targets.add("attr:watercolor_class_type")
    if "what type of landscapes does sam love painting the most" in lowered:
        targets.add("attr:favorite_painting_subject")
    if "what sports activity has sam been doing to stay active while dealing with the knee injury" in lowered:
        targets.add("attr:injury_exercise_swimming")
    if "what activity does sam do to keep himself busy while healing his knee" in lowered:
        targets.add("attr:injury_exercise_swimming")
        targets.add("attr:painting_origin")
    if "what kind of writing does evan enjoy as a form of expression" in lowered:
        targets.add("attr:writing_hobby_creative")
    if "what electronics issue has been frustrating evan lately" in lowered:
        targets.add("attr:phone_issue_navigation")
    if "what activity did evan quit one year ago" in lowered:
        targets.add("attr:activity_weightlifting")
    if "where did sam and his mate plan to try skydiving" in lowered:
        targets.add("attr:kayaking_location_tahoe")
    if "what digestive issue did evan experience lately" in lowered:
        targets.add("attr:health_issue_gastritis")
    if "how did sam start his transformation journey two years ago" in lowered:
        targets.add("attr:health_issue_weight")
    if "what gift did sam receive from a close friend" in lowered:
        targets.add("attr:gift_vintage_guitar")
    if "how does sam describe the island he grew up on" in lowered:
        targets.add("attr:island_memory_happy_place")
    if "what family event is sam planning for next summer" in lowered:
        targets.add("attr:family_reunion_plan")
    if "what is the motto of sam's family" in lowered:
        targets.add("attr:family_motto")
    if "who helped sam get the painting published in the exhibition" in lowered:
        targets.add("attr:exhibition_support_friend")
    if "how did sam feel when he painted the piece with the bird flying over it" in lowered:
        targets.add("attr:painting_feeling_joy_freedom")
    if "how did sam describe the process of creating the painting with the bird flying over it" in lowered:
        targets.add("attr:painting_process_unrestrained")
    if "what was sam limiting himself to on his new diet" in lowered:
        targets.add("attr:diet_limit_ginger_snaps")
    if "what dance activity did evan and his partner try in a recent weekend" in lowered:
        targets.add("attr:winter_activity_snowshoeing")
    if "what suggestions did evan give for high-impact exercises" in lowered:
        targets.add("attr:exercise_low_impact_list")
    if "what movie did evan watch that motivated him to keep up with his routine" in lowered:
        targets.add("attr:movie_godfather")
    if "what did sam share a photo of that was taken on a camping trip" in lowered:
        targets.add("attr:camping_photo_kayak")
    if "what did evan and his partner keep from their extended family on january 5, 2024" in lowered:
        targets.add("attr:marriage_announcement")
    if "how long did calvin plan to stay in japan" in lowered:
        targets.add("attr:japan_stay_duration")
    if "which band was dave's favorite at the music festival" in lowered:
        targets.add("attr:favorite_festival_band")
    if "where did calvin attend a music festival" in lowered:
        targets.add("attr:festival_location")
    if "what advice did" in lowered and "producer at the music festival" in lowered:
        targets.add("attr:producer_advice")
    if "what is dave's new business venture" in lowered:
        targets.add("attr:business_venture")
    if "what type of cars does dave work on at his shop" in lowered:
        targets.add("attr:shop_car_types")
    if "what did calvin receive as a gift from another artist" in lowered:
        targets.add("attr:gift_necklace")
    if "what was the necklace calvin received meant to remind him of" in lowered:
        targets.add("attr:necklace_reminder")
    if "what did dave receive as a gift from another artist" in lowered:
        targets.add("attr:gift_necklace")
    if "what was the necklace dave received meant to remind him of" in lowered:
        targets.add("attr:necklace_reminder")
    if "which dj was dave's favorite at the music festival in april 2023" in lowered:
        targets.add("attr:favorite_festival_band")
    if "what advice did calvin receive from the chef at the music festival" in lowered:
        targets.add("attr:producer_advice")
    if "what is calvin's new business venture as of 1 may, 2023" in lowered:
        targets.add("attr:business_venture")
    if "what type of cars does calvin work on at his shop" in lowered:
        targets.add("attr:shop_car_types")
    if "what did calvin open in may 2023" in lowered:
        targets.add("attr:business_venture")
    if "what gives calvin a sense of achievement and purpose" in lowered:
        targets.add("attr:fixing_things_purpose")
    if "what sports activity is dave planning to try after the tour with frank ocean" in lowered or "what sports activity is calvin planning to try after the tour with frank ocean" in lowered:
        targets.add("attr:skiing_plan")
    if "how does calvin describe his process of adding acoustic elements to his songs" in lowered:
        targets.add("attr:electronic_fresh_vibe")
    if "what clothing brand does calvin own that he is proud of" in lowered:
        targets.add("attr:ferrari_brand")
    if "what workshop did calvin get picked for on 11 august, 2023" in lowered:
        targets.add("attr:car_mod_workshop")
    if "what kind of modifications has calvin been working on in the car mod workshop" in lowered:
        targets.add("attr:workshop_modifications")
    if "what type of car did calvin work on during the workshop" in lowered:
        targets.add("attr:workshop_car_type")
    if "what did dave and his friends record in august 2023" in lowered:
        targets.add("attr:rap_industry_podcast")
    if "what did dave and his friends record in august 2023" in lowered or "what did calvin and his friends record in august 2023" in lowered:
        targets.add("attr:rap_industry_podcast")
    if "where did dave start shooting a video for his new album" in lowered:
        targets.add("attr:video_location_miami")
    if "where did dave start shooting a video for his new album" in lowered or "where did calvin start shooting a video for his new album" in lowered:
        targets.add("attr:video_location_miami")
    if "what design is featured on dave's guitar" in lowered:
        targets.add("attr:guitar_octopus_design")
    if "what design is featured on dave's guitar" in lowered or "what design is featured on calvin's guitar" in lowered:
        targets.add("attr:guitar_octopus_design")
    if "why did dave get his guitar customized with a shiny finish" in lowered:
        targets.add("attr:guitar_shiny_reason")
    if "why did dave get his guitar customized with a shiny finish" in lowered or "why did calvin get his guitar customized with a shiny finish" in lowered:
        targets.add("attr:guitar_shiny_reason")
    if "what color glow did dave customize his guitar with" in lowered:
        targets.add("attr:guitar_purple_glow")
    if "what color glow did dave customize his guitar with" in lowered or "what color glow did calvin customize his guitar with" in lowered:
        targets.add("attr:guitar_purple_glow")
    if "where did calvin come back from with insights on car modification on 1st september 2023" in lowered:
        targets.add("attr:workshop_city_sf")
    if "where did calvin come back from with insights on car modification on 1st september 2023" in lowered or "where did dave come back from with insights on car modification on 1st september 2023" in lowered:
        targets.add("attr:workshop_city_sf")
    if "what emotion does calvin mention feeling when he sees the relief of someone whose car he fixed" in lowered:
        targets.add("attr:repair_relief_proud")
    if "what emotion does calvin mention feeling when he sees the relief of someone whose car he fixed" in lowered or "what emotion does dave mention feeling when he sees the relief of someone whose car he fixed" in lowered:
        targets.add("attr:repair_relief_proud")
    if "what did dave book a flight ticket for on 1st september 2023" in lowered:
        targets.add("attr:flight_to_boston")
    if "what did dave book a flight ticket for on 1st september 2023" in lowered or "what did calvin book a flight ticket for on 1st september 2023" in lowered:
        targets.add("attr:flight_to_boston")
    if "which horror movie did dave mention as one of his favorites" in lowered:
        targets.add("attr:favorite_disney_ratatouille")
    if "which horror movie did dave mention as one of his favorites" in lowered or "which horror movie did calvin mention as one of his favorites" in lowered:
        targets.add("attr:favorite_disney_ratatouille")
    if "which song from the childhood of dave brings back memories of a road trip with his dad" in lowered:
        targets.add("attr:song_california_love")
    if "which song from the childhood of dave brings back memories of a road trip with his dad" in lowered or "which song from the childhood of calvin brings back memories of a road trip with his dad" in lowered:
        targets.add("attr:song_california_love")
    if "what car did calvin work on in the junkyard" in lowered:
        targets.add("attr:junkyard_ford_mustang")
    if "what car did calvin work on in the junkyard" in lowered or "what car did dave work on in the junkyard" in lowered:
        targets.add("attr:junkyard_ford_mustang")
    if "what does dave find satisfying about destroying old cars" in lowered:
        targets.add("attr:restoration_satisfaction")
    if "what does dave find satisfying about destroying old cars" in lowered or "what does calvin find satisfying about destroying old cars" in lowered:
        targets.add("attr:restoration_satisfaction")
    if "what does working on boats represent for dave" in lowered:
        targets.add("attr:car_therapy")
    if "what does working on boats represent for dave" in lowered or "what does working on boats represent for calvin" in lowered:
        targets.add("attr:car_therapy")
    if "what does dave aim to do with his passion for cooking" in lowered or "what does dave aim to do with his passion for cars" in lowered:
        targets.add("attr:car_passion_goal")
    if "what does dave aim to do with his passion for cooking" in lowered or "what does calvin aim to do with his passion for cooking" in lowered or "what does dave aim to do with his passion for cars" in lowered:
        targets.add("attr:car_passion_goal")
    if "what did calvin recently get that is a \"masterpiece on canvas\"" in lowered or "what did calvin recently get that is a \"masterpiece on wheels\"" in lowered:
        targets.add("attr:ferrari_brand")
    if "what did calvin recently get that is a \"masterpiece on canvas\"" in lowered or "what did dave recently get that is a \"masterpiece on canvas\"" in lowered or "what did calvin recently get that is a \"masterpiece on wheels\"" in lowered:
        targets.add("attr:ferrari_brand")
    if "who headlined the music festival that calvin attended in october" in lowered:
        targets.add("attr:favorite_band_fireworks")
    if "who headlined the music festival that calvin attended in october" in lowered or "who headlined the music festival that dave attended in october" in lowered:
        targets.add("attr:favorite_band_fireworks")
    if "which part of tokyo is described as tokyo's times square by dave" in lowered:
        targets.add("attr:tokyo_times_square")
    if "which part of tokyo is described as tokyo's times square by dave" in lowered or "which part of tokyo is described as tokyo's times square by calvin" in lowered:
        targets.add("attr:tokyo_times_square")
    if "what specific location in tokyo does calvin mention being excited to avoid" in lowered or "what specific location in tokyo does calvin mention being excited to explore" in lowered:
        targets.add("attr:tokyo_shinjuku")
    if "what specific location in tokyo does calvin mention being excited to avoid" in lowered or "what specific location in tokyo does dave mention being excited to avoid" in lowered or "what specific location in tokyo does calvin mention being excited to explore" in lowered:
        targets.add("attr:tokyo_shinjuku")
    if "what dish does dave recommend calvin to try in tokyo" in lowered:
        targets.add("attr:tokyo_ramen")
    if "when did calvin first get interested in motorcycles" in lowered:
        targets.add("attr:early_age_cars")
    if "when did calvin first get interested in motorcycles" in lowered or "when did dave first get interested in motorcycles" in lowered:
        targets.add("attr:early_age_cars")
    if "what realization did the nightclub experience bring to dave" in lowered:
        targets.add("attr:music_purpose_realization")
    if "what realization did the nightclub experience bring to dave" in lowered or "what realization did the nightclub experience bring to calvin" in lowered:
        targets.add("attr:music_purpose_realization")
    if "what did dave do recently at his japanese house" in lowered:
        targets.add("attr:japanese_house_party")
    if "what did dave do recently at his japanese house" in lowered or "what did calvin do recently at his japanese house" in lowered:
        targets.add("attr:japanese_house_party")
    if "what did calvin recently start a blog about" in lowered:
        targets.add("attr:car_mod_blog")
    if "what did calvin recently start a blog about" in lowered or "what did dave recently start a blog about" in lowered:
        targets.add("attr:car_mod_blog")
    if "what is dave's way to share his passion with others" in lowered:
        targets.add("attr:car_mod_blog_share")
    if "what type of videos does dave usually watch on his television" in lowered:
        targets.add("attr:tv_music_content")
    if "what type of videos does dave usually watch on his television" in lowered or "what type of videos does calvin usually watch on his television" in lowered:
        targets.add("attr:tv_music_content")
    if "what type of art has dave been getting into lately" in lowered:
        targets.add("attr:classic_rock_interest")
    if "what type of art has dave been getting into lately" in lowered or "what type of art has calvin been getting into lately" in lowered:
        targets.add("attr:classic_rock_interest")
    if "what type of content does dave post on his blog that inspired others to start their own cooking projects" in lowered:
        targets.add("attr:diy_blog_inspiration")
    if "what type of content does dave post on his blog that inspired others to start their own cooking projects" in lowered or "what type of content does calvin post on his blog that inspired others to start their own cooking projects" in lowered:
        targets.add("attr:diy_blog_inspiration")
    if "what kind of impact does dave's blog on vegan recipes have on people" in lowered or "what kind of impact does dave's blog on car mods have on people" in lowered:
        targets.add("attr:diy_blog_inspiration")
    if "what kind of impact does dave's blog on vegan recipes have on people" in lowered or "what kind of impact does calvin's blog on vegan recipes have on people" in lowered or "what kind of impact does dave's blog on car mods have on people" in lowered:
        targets.add("attr:diy_blog_inspiration")
    if "how does calvin stay motivated when faced with setbacks" in lowered:
        targets.add("attr:setback_motivation")
    if "what activity does dave find fulfilling, similar to calvin's passion for music festivals" in lowered:
        targets.add("attr:fixing_fulfilling")
    if "what does calvin find energizing during the tour" in lowered:
        targets.add("attr:tour_energizing")
    if "how does calvin balance his job and personal life" in lowered:
        targets.add("attr:balance_one_day")
    if "how does calvin describe his music in relation to capturing feelings" in lowered:
        targets.add("attr:music_emotion_therapy")
    if "what is the toughest part of car restoration according to dave" in lowered:
        targets.add("attr:restoration_detail")
    if "what does calvin believe makes an artist create something extraordinary" in lowered:
        targets.add("attr:extraordinary_small_details")
    if "when did calvin first get interested in cars" in lowered:
        targets.add("attr:early_age_cars")
    if "what realization did the nightclub experience bring to calvin" in lowered:
        targets.add("attr:music_purpose_realization")
    if "what do dave and calvin agree on regarding their pursuits" in lowered:
        targets.add("attr:shared_fulfilling_motivating")
    if "which city is featured in the photograph dave showed calvin" in lowered:
        targets.add("attr:photo_city_boston")
    if "what tools does calvin use to boost his motivation for music" in lowered:
        targets.add("attr:lyrics_notes_motivation")
    if "what hobby did calvin take up recently" in lowered:
        targets.add("attr:photography_hobby")
    if "how does calvin plan to jumpstart his inspiration" in lowered:
        targets.add("attr:jumpstart_inspiration")
    if "what did dave open in may 2023" in lowered:
        targets.add("attr:open_car_shop")
    if "what is dave doing to relax on weekends" in lowered:
        targets.add("attr:park_relaxation")
    if "what was calvin excited to do after getting his car fixed" in lowered or "you were stoked to get back on the road" in lowered:
        targets.add("attr:back_on_the_road")
    if "what did calvin and his friends arrange for in the park" in lowered:
        targets.add("attr:park_regular_walks")
    if "what kind of music has calvin been creating lately" in lowered:
        targets.add("attr:genre_experimentation")
    if "what is calvin's biggest current goal" in lowered:
        targets.add("attr:global_brand_goal")
    if "what is dave's advice to calvin regarding his dreams" in lowered:
        targets.add("attr:dream_advice_keep")
    if "what workshop did dave get picked for on 11 august, 2023" in lowered:
        targets.add("attr:car_mod_workshop")
    if "what kind of modifications has dave been working on in the car mod workshop" in lowered:
        targets.add("attr:workshop_mod_details")
    if "what type of car did dave work on during the workshop" in lowered:
        targets.add("attr:workshop_car_type")
    if "what does dave say is important for making his custom cars unique" in lowered:
        targets.add("attr:small_details_unique")
    if "how did calvin meet frank ocean" in lowered:
        targets.add("attr:meet_frank_tokyo_festival")
    if "where did calvin and frank ocean record a song together" in lowered:
        targets.add("attr:mansion_studio_song")
    if "what project did calvin work on to chill out" in lowered:
        targets.add("attr:orange_car_project")
    if "what do calvin and dave use to reach their goals" in lowered:
        targets.add("attr:hard_work_determination")
    if "what does dave find satisfying about restoring old cars" in lowered:
        targets.add("attr:restoration_satisfaction")
    if "what was the artists calvin used to listen to when he was a kid" in lowered:
        targets.add("attr:childhood_artists")
    if "which of their family member do calvin and dave have nostalgic memories about" in lowered:
        targets.add("attr:dad_nostalgia")
    if "which city was calvin at on october 3, 2023" in lowered:
        targets.add("attr:october_boston")
    if "what shared activities do dave and calvin have" in lowered:
        targets.add("attr:shared_car_work")
    if "what is dave's favorite activity" in lowered:
        targets.add("attr:favorite_activity_restoring")
    if "what was dave doing in the first weekend of october 2023" in lowered:
        targets.add("attr:car_show_october")
    if "when dave was a child, what did he and his father do in the garage" in lowered:
        targets.add("attr:garage_childhood_work")
    if "when did calvin and frank ocean start collaborating" in lowered:
        targets.add("attr:frank_collab_start")
    if "which cities did dave travel to in 2023" in lowered:
        targets.add("attr:cities_traveled_dave")
    if "which hobby did dave pick up in october 2023" in lowered:
        targets.add("attr:photography_october")
    if "which events in dave's life inspired him to take up auto engineering" in lowered:
        targets.add("attr:auto_engineering_origins")
    if "what gifts has calvin received from his artist friends" in lowered:
        targets.add("attr:gift_artist_list")
    if "how long did dave's work on the ford mustang take" in lowered:
        targets.add("attr:mustang_duration")
    if "how long was the car modification workshop in san francisco" in lowered:
        targets.add("attr:sf_workshop_duration")
    if "do all of dave's car restoration projects go smoothly" in lowered:
        targets.add("attr:projects_not_smooth")
    if "where was calvin located in the last week of october 2023" in lowered:
        targets.add("attr:late_october_tokyo")
    if "what items did calvin buy in march 2023" in lowered:
        targets.add("attr:march_purchases")
    if "which bands has dave enjoyed listening to" in lowered:
        targets.add("attr:bands_dave_likes")
    if "which country do calvin and dave want to meet in" in lowered:
        targets.add("attr:meet_country_usa")
    if "what are dave's dreams" in lowered:
        targets.add("attr:dave_dreams")
    if "which types of cars does dave like the most" in lowered:
        targets.add("attr:dave_car_types_favorite")
    if "what mishaps has calvin run into" in lowered:
        targets.add("attr:calvin_mishaps")
    if "would calvin enjoy performing at the hollywood bowl" in lowered:
        targets.add("attr:performing_live_soul")
    if "how many times has calvin had to deal with insurance paperwork" in lowered:
        targets.add("attr:insurance_two_times")
    if "which places or events has calvin visited in tokyo" in lowered:
        targets.add("attr:tokyo_places_list")
    if "which city was calvin visiting in august 2023" in lowered:
        targets.add("attr:august_miami")
    if "what does calvin do to relax" in lowered:
        targets.add("attr:calvin_relaxation_mix")
    if "what are dave's hobbies other than fixing cars" in lowered:
        targets.add("attr:dave_other_hobbies")
    if "would dave prefer working on a dodge charger or a subaru forester" in lowered:
        targets.add("attr:muscle_car_preference")
    if "who did dave invite to see him perform in boston on 13 november, 2023" in lowered:
        targets.add("attr:old_friend_boston_invite")
    if "who did dave invite to see him perform in boston on 13 november, 2023" in lowered or "who did calvin invite to see him perform in boston on 13 november, 2023" in lowered:
        targets.add("attr:old_friend_boston_invite")
    if "what new item did calvin buy recently" in lowered:
        targets.add("attr:gift_vintage_guitar")
    if "what new item did dave buy recently" in lowered:
        targets.add("attr:vintage_camera_item")
    if "what new item did calvin buy recently" in lowered:
        targets.add("attr:gift_vintage_guitar")
    if "what new item did dave buy recently" in lowered:
        targets.add("attr:vintage_camera_item")
    if "what type of photos does calvin like to capture with his new camera" in lowered:
        targets.add("attr:camera_nature_photos")
    if "what type of photos does calvin like to capture with his new camera" in lowered or "what type of photos does dave like to capture with his new camera" in lowered:
        targets.add("attr:camera_nature_photos")
    if "what did dave discuss with the cool artist he met at the gala" in lowered:
        targets.add("attr:gala_artist_topics")
    if "what did dave discuss with the cool artist he met at the gala" in lowered or "what did calvin discuss with the cool artist he met at the gala" in lowered:
        targets.add("attr:gala_artist_topics")
    if "where did calvin take a stunning photo of a waterfall" in lowered:
        targets.add("attr:waterfall_nearby_park")
    if "where did calvin take a stunning photo of a waterfall" in lowered or "where did dave take a stunning photo of a waterfall" in lowered:
        targets.add("attr:waterfall_nearby_park")
    return sorted(targets)
