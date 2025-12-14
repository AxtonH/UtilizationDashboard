-- Fix Script for monthly_sales_orders_totals table
-- This will check the current state and fix any issues

-- Step 1: Check what columns currently exist
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_sales_orders_totals'
ORDER BY ordinal_position;

-- Step 2: Drop the table if it exists (this will delete any existing data)
-- Uncomment the next line if you want to recreate the table from scratch
-- DROP TABLE IF EXISTS monthly_sales_orders_totals CASCADE;

-- Step 3: Create the table with the correct schema
CREATE TABLE IF NOT EXISTS monthly_sales_orders_totals (
    id BIGSERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    total_amount_aed NUMERIC(15, 2) NOT NULL DEFAULT 0,
    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(year, month)
);

-- Step 4: If the column is missing, add it (in case table exists but column doesn't)
-- This is a safety check - if the column already exists, it will error but that's okay
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'monthly_sales_orders_totals' 
        AND column_name = 'total_amount_aed'
    ) THEN
        ALTER TABLE monthly_sales_orders_totals 
        ADD COLUMN total_amount_aed NUMERIC(15, 2) NOT NULL DEFAULT 0;
    END IF;
END $$;

-- Step 5: Create indexes
CREATE INDEX IF NOT EXISTS idx_sales_orders_totals_year_month ON monthly_sales_orders_totals(year, month);
CREATE INDEX IF NOT EXISTS idx_sales_orders_totals_updated_at ON monthly_sales_orders_totals(updated_at);

-- Step 6: Create the trigger function
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

-- Step 7: Create the trigger
DROP TRIGGER IF EXISTS trigger_update_sales_orders_totals_updated_at ON monthly_sales_orders_totals;
CREATE TRIGGER trigger_update_sales_orders_totals_updated_at
    BEFORE UPDATE ON monthly_sales_orders_totals
    FOR EACH ROW
    EXECUTE FUNCTION update_sales_orders_totals_updated_at();

-- Step 8: Enable RLS and create policy
ALTER TABLE monthly_sales_orders_totals ENABLE ROW LEVEL SECURITY;

-- Drop existing policy if it exists
DROP POLICY IF EXISTS "Allow all operations for service role" ON monthly_sales_orders_totals;

-- Create the policy
CREATE POLICY "Allow all operations for service role"
    ON monthly_sales_orders_totals
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Step 9: Verify the table structure again
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'monthly_sales_orders_totals'
ORDER BY ordinal_position;

-- Step 10: Test insert
INSERT INTO monthly_sales_orders_totals (year, month, total_amount_aed)
VALUES (2025, 1, 1000.00)
ON CONFLICT (year, month) DO UPDATE SET total_amount_aed = EXCLUDED.total_amount_aed;

-- Step 11: Verify the insert worked
SELECT * FROM monthly_sales_orders_totals WHERE year = 2025 AND month = 1;

-- Step 12: Clean up test data
DELETE FROM monthly_sales_orders_totals WHERE year = 2025 AND month = 1;

-- Step 13: Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
















