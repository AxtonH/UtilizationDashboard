-- Supabase Database Schema for Monthly Utilization Cache
-- 
-- This table stores cached monthly utilization data per creative to improve dashboard performance.
-- The data is automatically refreshed from Odoo when missing or when explicitly requested.
--
-- Columns:
-- - id: Primary key (auto-incrementing)
-- - year: Year (e.g., 2025)
-- - month: Month (1-12)
-- - creative_id: ID of the creative employee
-- - available_hours: Available hours for the creative in this month
-- - logged_hours: Logged hours for the creative in this month
-- - planned_hours: Planned hours for the creative in this month
-- - utilization_percent: Utilization percentage (logged_hours / available_hours * 100)
-- - market_slug: Market slug (e.g., 'ksa', 'uae', 'shared') - nullable
-- - pool_name: Pool name - nullable
-- - cached_at: Timestamp when the data was cached

-- Create the table for storing monthly utilization data per creative
CREATE TABLE IF NOT EXISTS monthly_utilization_cache (
    id BIGSERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    creative_id INTEGER NOT NULL,
    available_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    logged_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    planned_hours NUMERIC(12, 2),
    utilization_percent NUMERIC(5, 2),
    market_slug TEXT,
    pool_name TEXT,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure uniqueness: one record per creative per year-month combination
    UNIQUE(year, month, creative_id)
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_monthly_utilization_cache_year_month ON monthly_utilization_cache(year, month);
CREATE INDEX IF NOT EXISTS idx_monthly_utilization_cache_creative_id ON monthly_utilization_cache(creative_id);
CREATE INDEX IF NOT EXISTS idx_monthly_utilization_cache_year_month_creative ON monthly_utilization_cache(year, month, creative_id);
CREATE INDEX IF NOT EXISTS idx_monthly_utilization_cache_cached_at ON monthly_utilization_cache(cached_at);
CREATE INDEX IF NOT EXISTS idx_monthly_utilization_cache_market_slug ON monthly_utilization_cache(market_slug) WHERE market_slug IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_monthly_utilization_cache_pool_name ON monthly_utilization_cache(pool_name) WHERE pool_name IS NOT NULL;

-- Add comments to document the columns
COMMENT ON TABLE monthly_utilization_cache IS 'Cached monthly utilization data per creative to improve dashboard performance';
COMMENT ON COLUMN monthly_utilization_cache.id IS 'Primary key (auto-incrementing)';
COMMENT ON COLUMN monthly_utilization_cache.year IS 'Year (e.g., 2025)';
COMMENT ON COLUMN monthly_utilization_cache.month IS 'Month (1-12)';
COMMENT ON COLUMN monthly_utilization_cache.creative_id IS 'ID of the creative employee';
COMMENT ON COLUMN monthly_utilization_cache.available_hours IS 'Available hours for the creative in this month';
COMMENT ON COLUMN monthly_utilization_cache.logged_hours IS 'Logged hours for the creative in this month';
COMMENT ON COLUMN monthly_utilization_cache.planned_hours IS 'Planned hours for the creative in this month';
COMMENT ON COLUMN monthly_utilization_cache.utilization_percent IS 'Utilization percentage calculated as (logged_hours / available_hours * 100)';
COMMENT ON COLUMN monthly_utilization_cache.market_slug IS 'Market slug (e.g., ksa, uae, shared)';
COMMENT ON COLUMN monthly_utilization_cache.pool_name IS 'Pool name';
COMMENT ON COLUMN monthly_utilization_cache.cached_at IS 'Timestamp when the data was cached';

-- Enable Row Level Security (RLS) - adjust policies based on your security requirements
ALTER TABLE monthly_utilization_cache ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows all operations (adjust based on your security needs)
-- For production, you should restrict this based on authenticated users or service roles
CREATE POLICY "Allow all operations for service role"
    ON monthly_utilization_cache
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Optional: Create a view for easier querying with calculated fields
-- Using SECURITY INVOKER to ensure it uses the permissions of the querying user
CREATE OR REPLACE VIEW monthly_utilization_cache_view
WITH (security_invoker = true) AS
SELECT 
    id,
    year,
    month,
    creative_id,
    available_hours,
    logged_hours,
    planned_hours,
    utilization_percent,
    market_slug,
    pool_name,
    cached_at,
    TO_CHAR(TO_DATE(year || '-' || LPAD(month::TEXT, 2, '0') || '-01', 'YYYY-MM-DD'), 'Mon') AS month_label,
    CASE 
        WHEN available_hours > 0 THEN ROUND((planned_hours / available_hours * 100.0)::NUMERIC, 2)
        ELSE NULL
    END AS planned_utilization_percent
FROM monthly_utilization_cache
ORDER BY year DESC, month DESC, creative_id;
