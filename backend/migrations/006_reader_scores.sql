-- Preserve the two reader scores when papers are written to PostgreSQL.
-- Existing rows remain NULL because their original scores are unavailable.
ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS read_first_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS content_potential_score DOUBLE PRECISION;
