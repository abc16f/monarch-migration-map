-- Cleaned iNaturalist sightings: one row per sighting, with proper columns,
-- a map point, and readable tag columns. Built from the raw table.
{{ config(
    materialized='table',
    indexes=[
      {'columns': ['geom'], 'type': 'gist'},
      {'columns': ['observed_on']},
      {'columns': ['subject']}
    ]
) }}

with source as (
    select * from {{ source('raw', 'inat_observations') }}
),

-- One row per tag, labeled from the lookup table. Tags the community voted
-- down are dropped. Within each sighting and question, tags are ranked by
-- votes so single-answer questions can keep only the top answer.
labeled as (
    select
        s.observation_id,
        (a->>'controlled_attribute_id')::int as attribute_id,
        t.value_label,
        row_number() over (
            partition by s.observation_id, (a->>'controlled_attribute_id')::int
            order by coalesce((a->>'vote_score')::int, 0) desc
        ) as vote_rank
    from source s
    cross join lateral jsonb_array_elements(
        coalesce(s.payload->'annotations', '[]'::jsonb)
    ) as a
    join {{ ref('inat_annotation_terms') }} t
      on t.attribute_id = (a->>'controlled_attribute_id')::int
     and t.value_id     = (a->>'controlled_value_id')::int
    where coalesce((a->>'vote_score')::int, 0) >= 0
),

-- One column per tag question. IDs come from the lookup table.
-- Life stage, alive or dead, and sex take a single answer: the top-voted one.
-- Flowering and leaf condition can have several answers, so all are kept,
-- listed alphabetically and separated by commas.
tags as (
    select
        observation_id,
        max(value_label) filter (where attribute_id = 1  and vote_rank = 1) as life_stage,
        max(value_label) filter (where attribute_id = 17 and vote_rank = 1) as alive_or_dead,
        max(value_label) filter (where attribute_id = 9  and vote_rank = 1) as sex,
        string_agg(distinct value_label, ', ' order by value_label)
            filter (where attribute_id = 12)                                as flowering_stage,
        string_agg(distinct value_label, ', ' order by value_label)
            filter (where attribute_id = 36)                                as leaf_condition
    from labeled
    group by observation_id
)

select
    -- Identity
    s.observation_id,
    s.subject,

    -- What was seen
    (s.payload->'taxon'->>'id')::int                    as taxon_id,
    s.payload->'taxon'->>'name'                         as scientific_name,
    s.payload->'taxon'->>'preferred_common_name'        as common_name,
    s.payload->'taxon'->>'rank'                         as taxon_rank,

    -- When
    (s.payload->>'observed_on')::date                   as observed_on,
    (s.payload->>'time_observed_at')::timestamptz       as observed_at,

    -- Where (iNaturalist stores coordinates as longitude, then latitude)
    (s.payload->'geojson'->'coordinates'->>1)::float    as latitude,
    (s.payload->'geojson'->'coordinates'->>0)::float    as longitude,
    st_setsrid(
        st_makepoint(
            (s.payload->'geojson'->'coordinates'->>0)::float,
            (s.payload->'geojson'->'coordinates'->>1)::float
        ), 4326
    )::geometry(Point, 4326)                            as geom,
    (s.payload->>'public_positional_accuracy')::numeric as location_accuracy_m,
    (s.payload->>'obscured')::boolean                   as is_location_obscured,
    s.payload->>'geoprivacy'                            as geoprivacy,
    s.payload->>'taxon_geoprivacy'                      as taxon_geoprivacy,

    -- How trustworthy
    s.payload->>'quality_grade'                         as quality_grade,
    (s.payload->>'captive')::boolean                    as is_captive,

    -- Tags (sex applies to monarchs only; plant sex tags are blanked)
    tags.life_stage,
    tags.alive_or_dead,
    case when s.subject = 'monarch' then tags.sex end   as sex,
    tags.flowering_stage,
    tags.leaf_condition,

    -- Credit and licensing
    (s.payload->'user'->>'id')::int                     as observer_id,
    s.payload->'user'->>'login'                         as observer_login,
    s.payload->>'license_code'                          as license_code,
    s.payload->>'uri'                                   as inat_url,

    -- Bookkeeping
    (s.payload->>'created_at')::timestamptz             as created_at,
    s.source_updated_at,
    s.run_date

from source s
left join tags using (observation_id)