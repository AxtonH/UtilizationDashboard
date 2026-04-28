-- BU/SBU/Pod columns for monthly utilization cache (April 2026+ assignment model).
-- Legacy months continue to use market_slug / pool_name only.

ALTER TABLE monthly_utilization_cache
    ADD COLUMN IF NOT EXISTS business_unit TEXT,
    ADD COLUMN IF NOT EXISTS sub_business_unit TEXT,
    ADD COLUMN IF NOT EXISTS pod TEXT;

COMMENT ON COLUMN monthly_utilization_cache.business_unit IS 'BU label(s) for that calendar month when using Odoo assignment slots';
COMMENT ON COLUMN monthly_utilization_cache.sub_business_unit IS 'SBU label(s) for that calendar month';
COMMENT ON COLUMN monthly_utilization_cache.pod IS 'Pod label(s) for that calendar month';
