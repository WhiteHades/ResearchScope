-- Load only into a disposable local database initialized by the API.
INSERT INTO papers (id, title, tags, authors, source, source_type, year, paper_score, conference_rank)
SELECT source_type || '-' || label, 'Fixture ' || label, tags::jsonb,
       '[]'::jsonb, 'fixture', source_type, 2026, 10,
       CASE WHEN source_type = 'conference' THEN 'A*' END
FROM (VALUES
    ('ir-short', '["IR"]'),
    ('ir-long', '["Information Retrieval"]'),
    ('ir-both', '["IR","Information Retrieval"]'),
    ('asr-short', '["ASR"]'),
    ('asr-long', '["Speech Recognition"]'),
    ('asr-case', '["Speech recognition"]'),
    ('tts-short', '["TTS"]'),
    ('tts-long', '["Speech Synthesis"]'),
    ('tts-case', '["Speech synthesis"]'),
    ('nlg-short', '["NLG"]'),
    ('nlg-long', '["Natural Language Generation"]'),
    ('llm-short', '["LLMs"]'),
    ('llm-long', '["Large Language Models"]'),
    ('speech-only', '["Speech"]'),
    ('separation-only', '["Speech separation"]'),
    ('constructor-only', '["constructor"]')
) AS labels(label, tags)
CROSS JOIN (VALUES ('preprint'), ('conference'), ('journal')) AS sources(source_type);
