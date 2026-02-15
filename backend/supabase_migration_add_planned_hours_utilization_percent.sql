-- Migration: Add planned_hours and utilization_percent to monthly_utilization_cache
-- 
-- This migration adds two new columns to the monthly_utilization_cache table:
-- 1. planned_hours: NUMERIC(12, 2) - Planned hours for the creative in this month
-- 2. utilization_percent: NUMERIC(5, 2) - Utilization percentage (logged_hours / available_hours * 100)

-- Add planned_hours column (nullable initially to allow migration of existing data)
ALTER TABLE monthly_utilization_cache
ADD COLUMN IF NOT EXISTS planned_hours NUMERIC(12, 2);

-- Add utilization_percent column (nullable initially to allow migration of existing data)
ALTER TABLE monthly_utilization_cache
ADD COLUMN IF NOT EXISTS utilization_percent NUMERIC(5, 2);

-- Add comment to document the columns
COMMENT ON COLUMN monthly_utilization_cache.planned_hours IS 'Planned hours for the creative in this month';
COMMENT ON COLUMN monthly_utilization_cache.utilization_percent IS 'Utilization percentage calculated as (logged_hours / available_hours * 100)';
