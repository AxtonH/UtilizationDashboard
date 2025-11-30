-- Cleanup script to remove unused columns from monthly_sales_orders_totals table
-- This removes amount_aed and order_count columns that are not used by the code

-- Step 1: Check current columns
SELECT 
    column_name, 
    data_type
FROM information_schema.columns
WHERE table_name = 'monthly_sales_orders_totals'
ORDER BY ordinal_position;

-- Step 2: Drop unused columns (if they exist)
-- These columns are not used by the application code
ALTER TABLE monthly_sales_orders_totals 
DROP COLUMN IF EXISTS amount_aed;

ALTER TABLE monthly_sales_orders_totals 
DROP COLUMN IF EXISTS order_count;

-- Step 3: Verify the final structure (should only have: id, year, month, total_amount_aed, cached_at, updated_at)
SELECT 
    column_name, 
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_sales_orders_totals'
ORDER BY ordinal_position;

-- Step 4: Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';

-- Step 5: Test insert to verify everything works
INSERT INTO monthly_sales_orders_totals (year, month, total_amount_aed)
VALUES (2025, 1, 1234.56)
ON CONFLICT (year, month) DO UPDATE SET total_amount_aed = EXCLUDED.total_amount_aed;

-- Step 6: Verify the insert worked
SELECT * FROM monthly_sales_orders_totals WHERE year = 2025 AND month = 1;

-- Step 7: Clean up test data
DELETE FROM monthly_sales_orders_totals WHERE year = 2025 AND month = 1;

