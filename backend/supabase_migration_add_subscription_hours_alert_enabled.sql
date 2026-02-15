-- Migration: Add subscription_hours_alert_enabled column to email_settings table
-- Run this SQL in your Supabase SQL Editor if the column doesn't exist

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
        
        RAISE NOTICE 'Column subscription_hours_alert_enabled added successfully';
    ELSE
        RAISE NOTICE 'Column subscription_hours_alert_enabled already exists';
    END IF;
END $$;
