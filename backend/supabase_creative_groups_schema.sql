-- Supabase Database Schema for Creative Groups
-- 
-- This table stores user-created groups of creatives for filtering and organization.

-- Create the table for storing creative groups
CREATE TABLE IF NOT EXISTS creative_groups (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    creative_ids INTEGER[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure group names are unique
    UNIQUE(name)
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_creative_groups_name ON creative_groups(name);
CREATE INDEX IF NOT EXISTS idx_creative_groups_created_at ON creative_groups(created_at);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_creative_groups_updated_at()
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
CREATE TRIGGER trigger_update_creative_groups_updated_at
    BEFORE UPDATE ON creative_groups
    FOR EACH ROW
    EXECUTE FUNCTION update_creative_groups_updated_at();

-- Enable Row Level Security (RLS)
ALTER TABLE creative_groups ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows all operations (adjust based on your security needs)
CREATE POLICY "Allow all operations for service role"
    ON creative_groups
    FOR ALL
    USING (true)
    WITH CHECK (true);

