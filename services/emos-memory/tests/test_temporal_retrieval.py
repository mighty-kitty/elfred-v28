from src.memory_system.workflow import build_default_agent


def test_when_query_prefers_relative_event_over_generic_same_month_memory():
    agent = build_default_agent()
    user_id = "pytest-temporal-user"
    session_id = "pytest-temporal-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[7:55 pm on 9 June, 2023] Caroline: I wanted to tell you about my school event last week. I gave a talk about my transgender journey.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[10:37 am on 27 June, 2023] Caroline: Lately, I've been looking into counseling and mental health as a career.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="When did Caroline give a speech at a school?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "school event last week" in result.recalled_memory.text.lower()


def test_how_long_query_prefers_duration_memory():
    agent = build_default_agent()
    user_id = "pytest-duration-user"
    session_id = "pytest-duration-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[7:55 pm on 9 June, 2023] Caroline: I've known these friends for 4 years, since I moved from my home country.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[8:18 pm on 6 July, 2023] Caroline: My friends and family helping with my transition make all the difference.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="How long has Caroline had her current group of friends for?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "4 years" in result.recalled_memory.text.lower()


def test_singular_pet_query_prefers_subject_owned_pet_memory():
    agent = build_default_agent()
    user_id = "pytest-pet-user"
    session_id = "pytest-pet-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[4:33 pm on 12 July, 2023] Melanie: Luna and Oliver are so sweet and playful.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[3:31 pm on 23 August, 2023] Caroline: And yup, I do- Oscar, my guinea pig.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What pet does Caroline have?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "guinea pig" in result.recalled_memory.text.lower()


def test_motivation_query_prefers_counseling_journey_memory():
    agent = build_default_agent()
    user_id = "pytest-motivation-user"
    session_id = "pytest-motivation-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[4:33 pm on 12 July, 2023] Melanie: Your experience really brought you to where you need to be. You're gonna make a huge difference!",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[10:37 am on 27 June, 2023] Caroline: My own journey and the support I got made a huge difference. I saw how counseling and support groups improved my life, so I started caring more about mental health.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What motivated Caroline to pursue counseling?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "support groups improved my life" in result.recalled_memory.text.lower()


def test_relax_after_road_trip_prefers_follow_up_answer():
    agent = build_default_agent()
    user_id = "pytest-roadtrip-user"
    session_id = "pytest-roadtrip-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[6:55 pm on 20 October, 2023] Melanie: Been running longer since our last chat - a great way to destress and clear my mind.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[9:55 am on 22 October, 2023] Caroline: Did you all go on that nature walk after the road trip?",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[9:55 am on 22 October, 2023] Melanie: Thanks, Caroline! Yup, we just did it yesterday! The kids loved it and it was a nice way to relax after the road trip.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What did Melanie do after the road trip to relax?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "relax after the road trip" in result.recalled_memory.text.lower()


def test_charity_race_awareness_prefers_race_memory_over_generic_mental_health_memory():
    agent = build_default_agent()
    user_id = "pytest-charity-user"
    session_id = "pytest-charity-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[10:37 am on 27 June, 2023] Caroline: I'm looking into counseling and mental health as a career.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[1:14 pm on 25 May, 2023] Melanie: I ran a charity race for mental health last Saturday - it was really rewarding.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What did the charity race raise awareness for?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "charity race for mental health" in result.recalled_memory.text.lower()


def test_october_painting_query_prefers_pink_sky_painting():
    agent = build_default_agent()
    user_id = "pytest-paint-user"
    session_id = "pytest-paint-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[10:31 am on 13 October, 2023] Melanie: I painted it because it was calming. I've done an abstract painting too, take a look!",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[10:31 am on 13 October, 2023] Melanie: Here's one I did last week. It's inspired by the sunsets. image: a photo of a painting of a sunset with a pink sky query: landscape painting vibrant purple sunset autumn",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What painting did Melanie show to Caroline on October 13, 2023?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "pink sky" in result.recalled_memory.text.lower() or "inspired by the sunsets" in result.recalled_memory.text.lower()


def test_seen_music_artists_query_prefers_actual_seen_performer_memory():
    agent = build_default_agent()
    user_id = "pytest-music-user"
    session_id = "pytest-music-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text='[3:19 pm on 28 August, 2023] Melanie: I am a fan of both classical like Bach and Mozart, as well as modern music like Ed Sheeran\'s "Perfect".',
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text='[3:19 pm on 28 August, 2023] Melanie: "Summer Sounds" got everyone dancing and singing. It was so fun and lively!',
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What musical artists/bands has Melanie seen?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "summer sounds" in result.recalled_memory.text.lower()


def test_personality_traits_query_prefers_trait_bearing_memory():
    agent = build_default_agent()
    user_id = "pytest-personality-user"
    session_id = "pytest-personality-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[12:09 am on 13 September, 2023] Melanie: Woah, Caroline, it sounds like you're doing some impressive work.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[12:09 am on 13 September, 2023] Melanie: You're so thoughtful!",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What personality traits might Melanie say Caroline has?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "thoughtful" in result.recalled_memory.text.lower()


def test_pet_location_query_prefers_bone_hiding_memory():
    agent = build_default_agent()
    user_id = "pytest-petloc-user"
    session_id = "pytest-petloc-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[3:31 pm on 23 August, 2023] Melanie: Oliver's hilarious! He hid his bone in my slipper once!",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[3:31 pm on 23 August, 2023] Caroline: Oscar is my guinea pig.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="Where did Oscar hide his bone once?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "slipper" in result.recalled_memory.text.lower()


def test_activity_with_dad_query_prefers_horseback_memory():
    agent = build_default_agent()
    user_id = "pytest-dad-user"
    session_id = "pytest-dad-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[3:31 pm on 23 August, 2023] Caroline: I used to go horseback riding with my dad when I was a kid.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What activity did Melanie used to do with her dad?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "horseback riding" in result.recalled_memory.text.lower()


def test_love_most_about_camping_query_prefers_presence_memory():
    agent = build_default_agent()
    user_id = "pytest-campingfeel-user"
    session_id = "pytest-campingfeel-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[1:51 pm on 15 July, 2023] Melanie: We even went on another camping trip in the forest.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[6:55 pm on 20 October, 2023] Melanie: It's a chance to be present and together. We bond over stories, campfires and nature. It always refreshes my soul.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What does Caroline love most about camping with her family?",
        persist=False,
    )

    assert result.recalled_memory is not None
    lowered = result.recalled_memory.text.lower()
    assert "present and together" in lowered or "refreshes my soul" in lowered


def test_church_hiking_query_prefers_hiking_memory():
    agent = build_default_agent()
    user_id = "pytest-church-hike-user"
    session_id = "pytest-church-hike-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[3:34 pm on 17 July, 2023] Maria: I had a great experience last weekend hiking with my church friends. It felt so refreshing!",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="In what activity did Maria and her church friends participate in July 2023?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "hiking" in result.recalled_memory.text.lower()


def test_community_work_query_prefers_community_work_memory():
    agent = build_default_agent()
    user_id = "pytest-community-work-user"
    session_id = "pytest-community-work-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[3:14 pm on 13 August, 2023] Maria: Yesterday, I took up some community work with my friends from church. It was super rewarding!",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What activity did Maria take up with her friends from church in August 2023?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "community work" in result.recalled_memory.text.lower()


def test_library_frequency_query_prefers_few_times_a_week_memory():
    agent = build_default_agent()
    user_id = "pytest-library-user"
    session_id = "pytest-library-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[9:36 am on 2 April, 2023] John: Yeah, we go a few times a week. It's great for family bonding.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="How often does John take his kids to the library?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "few times a week" in result.recalled_memory.text.lower()


def test_how_long_query_prefers_turtle_duration_memory():
    agent = build_default_agent()
    user_id = "pytest-turtle-duration-user"
    session_id = "pytest-turtle-duration-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[2:11 pm on 25 October, 2022] Nate: I've had them for 3 years now and they bring me tons of joy!",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[2:15 pm on 25 October, 2022] Nate: I was bored today, so I just took my turtles out for a walk.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="How long has Nate had his first two turtles?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "3 years" in result.recalled_memory.text.lower()


def test_major_achievement_query_prefers_screenplay_completion_memory():
    agent = build_default_agent()
    user_id = "pytest-screenplay-user"
    session_id = "pytest-screenplay-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[8:20 pm on 21 January, 2022] Joanna: Woo! I finally finished my first full screenplay and printed it last Friday.",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[7:55 pm on 23 January, 2022] Joanna: I am all about dramas and romcoms.",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What major achievement did Joanna accomplish in January 2022?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "finished my first full screenplay" in result.recalled_memory.text.lower()
