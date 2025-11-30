-- Supabase Database Schema for External Hours Cache
-- 
-- This table stores cached monthly external hours data to improve dashboard performance.
-- The data is automatically refreshed from Odoo when missing or when explicitly requested.

-- Create the table for storing monthly external hours data
CREATE TABLE IF NOT EXISTS external_hours_monthly_cache (
    id BIGSERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    total_external_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_subscription_used_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_used_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_monthly_subscription_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_sold_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure uniqueness: one record per year-month combination
    UNIQUE(year, month)
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_external_hours_cache_year_month ON external_hours_monthly_cache(year, month);
CREATE INDEX IF NOT EXISTS idx_external_hours_cache_updated_at ON external_hours_monthly_cache(updated_at);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_external_hours_cache_updated_at()
RETURNS TRIGGER 
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Create a trigger to automatically update updated_at on row updates
CREATE TRIGGER trigger_update_external_hours_cache_updated_at
    BEFORE UPDATE ON external_hours_monthly_cache
    FOR EACH ROW
    EXECUTE FUNCTION update_external_hours_cache_updated_at();

-- Enable Row Level Security (RLS) - adjust policies based on your security requirements
ALTER TABLE external_hours_monthly_cache ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows all operations (adjust based on your security needs)
-- For production, you should restrict this based on authenticated users or service roles
CREATE POLICY "Allow all operations for service role"
    ON external_hours_monthly_cache
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Optional: Create a view for easier querying
-- Using SECURITY INVOKER to ensure it uses the permissions of the querying user
CREATE OR REPLACE VIEW external_hours_monthly_cache_view
WITH (security_invoker = true) AS
SELECT 
    id,
    year,
    month,
    total_external_hours,
    total_subscription_used_hours,
    total_used_hours,
    total_monthly_subscription_hours,
    total_sold_hours,
    cached_at,
    updated_at,
    TO_CHAR(TO_DATE(year || '-' || LPAD(month::TEXT, 2, '0') || '-01', 'YYYY-MM-DD'), 'Mon') AS month_label
FROM external_hours_monthly_cache
ORDER BY year DESC, month DESC;

-- ============================================================================
-- Supabase Database Schema for Sales Orders Monthly Cache
-- 
-- This table stores cached monthly Sales Orders totals (AED value) to improve 
-- dashboard performance. The data is automatically refreshed from Odoo when 
-- missing or when explicitly requested.
-- ============================================================================

-- Create the table for storing monthly Sales Orders totals
CREATE TABLE IF NOT EXISTS monthly_sales_orders_totals (
    id BIGSERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    total_amount_aed NUMERIC(15, 2) NOT NULL DEFAULT 0,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure uniqueness: one record per year-month combination
    UNIQUE(year, month)
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_sales_orders_totals_year_month ON monthly_sales_orders_totals(year, month);
CREATE INDEX IF NOT EXISTS idx_sales_orders_totals_updated_at ON monthly_sales_orders_totals(updated_at);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_sales_orders_totals_updated_at()
RETURNS TRIGGER 
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Create a trigger to automatically update updated_at on row updates
CREATE TRIGGER trigger_update_sales_orders_totals_updated_at
    BEFORE UPDATE ON monthly_sales_orders_totals
    FOR EACH ROW
    EXECUTE FUNCTION update_sales_orders_totals_updated_at();

-- Enable Row Level Security (RLS) - adjust policies based on your security requirements
ALTER TABLE monthly_sales_orders_totals ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows all operations (adjust based on your security needs)
-- For production, you should restrict this based on authenticated users or service roles
CREATE POLICY "Allow all operations for service role"
    ON monthly_sales_orders_totals
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Optional: Create a view for easier querying
-- Using SECURITY INVOKER to ensure it uses the permissions of the querying user
CREATE OR REPLACE VIEW monthly_sales_orders_totals_view
WITH (security_invoker = true) AS
SELECT 
    id,
    year,
    month,
    total_amount_aed,
    cached_at,
    updated_at,
    TO_CHAR(TO_DATE(year || '-' || LPAD(month::TEXT, 2, '0') || '-01', 'YYYY-MM-DD'), 'Mon') AS month_label
FROM monthly_sales_orders_totals
ORDER BY year DESC, month DESC;

