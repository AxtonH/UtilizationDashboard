-- Per-creative monthly hour overrides (Odoo hr.employee id + fixed hours/month for dashboard availability).

CREATE TABLE IF NOT EXISTS creative_hour_adjustments (
    employee_id INTEGER PRIMARY KEY,
    monthly_hours NUMERIC(10, 2) NOT NULL CHECK (monthly_hours >= 0 AND monthly_hours <= 400),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_creative_hour_adjustments_updated_at()
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

DROP TRIGGER IF EXISTS trigger_creative_hour_adjustments_updated_at ON creative_hour_adjustments;
CREATE TRIGGER trigger_creative_hour_adjustments_updated_at
    BEFORE UPDATE ON creative_hour_adjustments
    FOR EACH ROW
    EXECUTE FUNCTION update_creative_hour_adjustments_updated_at();

ALTER TABLE creative_hour_adjustments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all operations for service role" ON creative_hour_adjustments;
CREATE POLICY "Allow all operations for service role"
    ON creative_hour_adjustments
    FOR ALL
    USING (true)
    WITH CHECK (true);
