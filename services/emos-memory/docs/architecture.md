# Architecture Notes

## Engineering Translation Of The Original Idea

The original PDF describes a memory-product direction, not a production-ready repository layout. The current engineering translation uses four memory layers:

1. Semantic memory
   User profile, long-term interests, keyword accumulation, and stable facts.
2. Episodic memory
   User-specific event traces tied to sessions and timestamps.
3. Emotional memory
   Emotion labels, trigger words, and emotional salience for commit and recall.
4. Reflection memory
   Periodic dream-style summaries that compress recent trajectories.

## Workflow

Each turn follows the same canonical pipeline:

1. Observe
   Accept user input and current session context.
2. Tag Emotion
   Detect emotion and trigger words.
3. Commit Memory
   Persist salient turns into long-term memory.
4. Recall
   Retrieve related memories from history.
5. Reflect
   Periodically generate a higher-level summary.

## Why The API Is Not A Last-Minute Wrapper

If core logic lives directly inside `final.py` and the API is added only at the end, projects usually drift into duplicated business logic, inconsistent persistence, and benchmark code that cannot reuse the same memory pipeline.

The current repository keeps `workflow.py` as the canonical pipeline and treats CLI, API, benchmark, and scripts as outer adapters. That makes evaluation, debugging, and delivery much cleaner.

## Retrieval Stack

The retrieval layer now supports four backends:

- `lexical`: direct token overlap and concept hits
- `semantic`: semantic-counter similarity over aliases, tokens, and character n-grams
- `hybrid`: lexical + semantic + fuzzy matching with recency/profile reranking
- `embedding_rerank`: hashed dense embedding retrieval followed by feature-aware reranking

This gives the project a baseline backend, two strong sparse/dense variants, and a delivery-ready default backend.
