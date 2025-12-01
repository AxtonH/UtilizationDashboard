-- Verification and Fix Script for monthly_sales_orders_totals table
-- Run this in Supabase SQL Editor to verify the table exists and refresh the schema cache

-- 1. Check if table exists and show its structure
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_sales_orders_totals'
ORDER BY ordinal_position;

-- 2. If table doesn't exist or is missing columns, recreate it
-- (This will only create if it doesn't exist due to IF NOT EXISTS)
CREATE TABLE IF NOT EXISTS monthly_sales_orders_totals (
    id BIGSERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    total_amount_aed NUMERIC(15, 2) NOT NULL DEFAULT 0,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(year, month)
);

-- 3. Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_sales_orders_totals_year_month ON monthly_sales_orders_totals(year, month);
CREATE INDEX IF NOT EXISTS idx_sales_orders_totals_updated_at ON monthly_sales_orders_totals(updated_at);

-- 4. Refresh PostgREST schema cache by notifying PostgREST
-- This forces PostgREST to reload the schema
NOTIFY pgrst, 'reload schema';

-- 5. Verify the table is accessible
SELECT COUNT(*) as row_count FROM monthly_sales_orders_totals;

-- 6. Test insert (you can delete this row after testing)
INSERT INTO monthly_sales_orders_totals (year, month, total_amount_aed)
VALUES (2025, 1, 1000.00)
ON CONFLICT (year, month) DO UPDATE SET total_amount_aed = EXCLUDED.total_amount_aed;

-- 7. Verify the insert worked
SELECT * FROM monthly_sales_orders_totals WHERE year = 2025 AND month = 1;

-- 8. Clean up test data (uncomment to delete test row)
-- DELETE FROM monthly_sales_orders_totals WHERE year = 2025 AND month = 1;




