-- Creates the area and table that hold untouched iNaturalist sightings.
-- Safe to run more than once.
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.inat_observations (
    observation_id     BIGINT PRIMARY KEY,                  -- iNaturalist's sighting ID
    subject            TEXT NOT NULL
                       CHECK (subject IN ('monarch', 'milkweed')),
    source_updated_at  TIMESTAMPTZ NOT NULL,                -- when iNaturalist last changed it
    payload            JSONB NOT NULL,                      -- the full original record
    run_date           DATE NOT NULL,                       -- which harvest run it came from
    loaded_at          TIMESTAMPTZ NOT NULL DEFAULT now()   -- when it entered this table
);