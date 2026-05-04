-- Manual Strategy& external hours (dashboard Ext Hrs SOLD / Used), keyed by calendar month.

CREATE TABLE IF NOT EXISTS strategy_and_external_hours (
    year INTEGER NOT NULL CHECK (year >= 2000 AND year <= 2100),
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    external_hours_sold NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (external_hours_sold >= 0 AND external_hours_sold <= 10000000),
    external_hours_used NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (external_hours_used >= 0 AND external_hours_used <= 10000000),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (year, month)
);

CREATE OR REPLACE FUNCTION update_strategy_and_external_hours_updated_at()
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

DROP TRIGGER IF EXISTS trigger_strategy_and_external_hours_updated_at ON strategy_and_external_hours;
CREATE TRIGGER trigger_strategy_and_external_hours_updated_at
    BEFORE UPDATE ON strategy_and_external_hours
    FOR EACH ROW
    EXECUTE FUNCTION update_strategy_and_external_hours_updated_at();

ALTER TABLE strategy_and_external_hours ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all operations for service role" ON strategy_and_external_hours;
CREATE POLICY "Allow all operations for service role"
    ON strategy_and_external_hours
    FOR ALL
    USING (true)
    WITH CHECK (true);
