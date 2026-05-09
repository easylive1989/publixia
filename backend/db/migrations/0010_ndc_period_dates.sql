-- 0010_ndc_period_dates.sql
--
-- NDC (景氣對策信號) is a monthly indicator, but the daily-cron fetcher
-- wrote one row per fetch_day with `date` defaulting to "today" — so the
-- chart ended up with ~daily resolution showing the same period's value
-- repeated across many dates. Going forward the fetcher passes
-- date=YYYY-MM-01 derived from the period; this migration collapses
-- the existing rows into the same shape.
--
-- Step 1: keep only the latest fetch row per period (highest id).
-- Step 2: rewrite surviving rows so date + timestamp align with the
--         period (YYYY/MM in extra_json → YYYY-MM-01).

DELETE FROM indicator_snapshots
WHERE indicator = 'ndc' AND id NOT IN (
    SELECT MAX(id) FROM indicator_snapshots
    WHERE indicator = 'ndc' AND extra_json IS NOT NULL
    GROUP BY json_extract(extra_json, '$.period')
);

UPDATE indicator_snapshots
SET date = substr(json_extract(extra_json, '$.period'), 1, 4) || '-' ||
           substr(json_extract(extra_json, '$.period'), 6, 2) || '-01',
    timestamp = substr(json_extract(extra_json, '$.period'), 1, 4) || '-' ||
                substr(json_extract(extra_json, '$.period'), 6, 2) || '-01T00:00:00'
WHERE indicator = 'ndc' AND extra_json IS NOT NULL;
