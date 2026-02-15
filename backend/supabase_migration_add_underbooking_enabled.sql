-- Migration: Add underbooking_enabled column to email_settings table
-- Run this SQL in your Supabase SQL Editor if the column doesn't exist

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
        
        RAISE NOTICE 'Column underbooking_enabled added successfully';
    ELSE
        RAISE NOTICE 'Column underbooking_enabled already exists';
    END IF;
END $$;
