-- Supabase Database Schema for Email Settings
-- 
-- This table stores email configuration for the alert scheduler.

-- Create the table for storing email settings
CREATE TABLE IF NOT EXISTS email_settings (
    id BIGSERIAL PRIMARY KEY,
    recipients TEXT[] NOT NULL DEFAULT '{}',
    cc_recipients TEXT[] NOT NULL DEFAULT '{}',
    send_date DATE,
    send_time TIME,
    enabled BOOLEAN NOT NULL DEFAULT true,
    internal_external_imbalance_enabled BOOLEAN NOT NULL DEFAULT false,
    overbooking_enabled BOOLEAN NOT NULL DEFAULT false,
    underbooking_enabled BOOLEAN NOT NULL DEFAULT false,
    subscription_hours_alert_enabled BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Ensure only one configuration exists
    CONSTRAINT single_email_settings CHECK (id = 1)
);

-- Add internal_external_imbalance_enabled column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'email_settings' 
        AND column_name = 'internal_external_imbalance_enabled'
    ) THEN
        ALTER TABLE email_settings 
        ADD COLUMN internal_external_imbalance_enabled BOOLEAN NOT NULL DEFAULT false;
    END IF;
END $$;

-- Add overbooking_enabled column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'email_settings' 
        AND column_name = 'overbooking_enabled'
    ) THEN
        ALTER TABLE email_settings 
        ADD COLUMN overbooking_enabled BOOLEAN NOT NULL DEFAULT false;
    END IF;
END $$;

-- Add underbooking_enabled column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'email_settings' 
        AND column_name = 'underbooking_enabled'
    ) THEN
        ALTER TABLE email_settings 
        ADD COLUMN underbooking_enabled BOOLEAN NOT NULL DEFAULT false;
    END IF;
END $$;

-- Add subscription_hours_alert_enabled column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'email_settings' 
        AND column_name = 'subscription_hours_alert_enabled'
    ) THEN
        ALTER TABLE email_settings 
        ADD COLUMN subscription_hours_alert_enabled BOOLEAN NOT NULL DEFAULT false;
    END IF;
END $$;

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_email_settings_enabled ON email_settings(enabled);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_email_settings_updated_at()
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

-- Drop trigger if it exists, then create it
DROP TRIGGER IF EXISTS trigger_update_email_settings_updated_at ON email_settings;
CREATE TRIGGER trigger_update_email_settings_updated_at
    BEFORE UPDATE ON email_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_email_settings_updated_at();

-- Enable Row Level Security (RLS)
ALTER TABLE email_settings ENABLE ROW LEVEL SECURITY;

-- Drop policy if it exists, then create it
DROP POLICY IF EXISTS "Allow all operations for service role" ON email_settings;
CREATE POLICY "Allow all operations for service role"
    ON email_settings
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Insert a default row (will be updated, not inserted)
INSERT INTO email_settings (id, recipients, cc_recipients, enabled, internal_external_imbalance_enabled, overbooking_enabled, underbooking_enabled, subscription_hours_alert_enabled)
VALUES (1, ARRAY[]::TEXT[], ARRAY[]::TEXT[], false, false, false, false, false)
ON CONFLICT (id) DO NOTHING;
