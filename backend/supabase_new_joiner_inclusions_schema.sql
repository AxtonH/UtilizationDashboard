-- New joiner utilization inclusions: employees inside their 3-month ramp whose
-- hours SHOULD count toward utilization (toggled on the dashboard card pill).
-- No row = default behavior (ramp hours excluded).

CREATE TABLE IF NOT EXISTS new_joiner_inclusions (
    employee_id INTEGER PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_new_joiner_inclusions_updated_at()
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

DROP TRIGGER IF EXISTS trigger_new_joiner_inclusions_updated_at ON new_joiner_inclusions;
CREATE TRIGGER trigger_new_joiner_inclusions_updated_at
    BEFORE UPDATE ON new_joiner_inclusions
    FOR EACH ROW
    EXECUTE FUNCTION update_new_joiner_inclusions_updated_at();

ALTER TABLE new_joiner_inclusions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all operations for service role" ON new_joiner_inclusions;
CREATE POLICY "Allow all operations for service role"
    ON new_joiner_inclusions
    FOR ALL
    USING (true)
    WITH CHECK (true);
