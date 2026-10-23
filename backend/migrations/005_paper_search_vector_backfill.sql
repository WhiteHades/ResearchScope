-- Run during a planned deployment window because this updates every missing
-- paper search vector and can generate substantial table and index writes.
UPDATE papers
SET search_vector = to_tsvector(
    'english', coalesce(title, '') || ' ' || coalesce(abstract, '')
)
WHERE search_vector IS NULL;

-- Preserve the recorded extractor for documents that were already processed.
ALTER TABLE paper_documents
    ALTER COLUMN extractor_version SET DEFAULT 'pymupdf-hybrid-v2';
