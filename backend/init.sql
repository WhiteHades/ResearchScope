-- Run this once on your Railway PostgreSQL database after first deploy.
-- The FastAPI app creates the tables automatically via SQLAlchemy on startup.
-- This script adds the full-text search trigger.

CREATE OR REPLACE FUNCTION papers_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.title, '') || ' ' || coalesce(NEW.abstract, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS papers_search_vector_trigger ON papers;
CREATE TRIGGER papers_search_vector_trigger
BEFORE INSERT OR UPDATE ON papers
FOR EACH ROW EXECUTE FUNCTION papers_search_vector_update();
