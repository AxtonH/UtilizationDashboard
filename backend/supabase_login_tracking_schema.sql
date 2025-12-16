-- Login Tracking Table Schema for Supabase
-- This table tracks user login events for analytics and auditing

CREATE TABLE IF NOT EXISTS login_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    username VARCHAR(255) NOT NULL,
    login_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT
);

-- Index for user_id lookups (most common query)
CREATE INDEX IF NOT EXISTS idx_login_events_user_id ON login_events(user_id);

-- Index for timestamp-based queries (recent logins, login history)
CREATE INDEX IF NOT EXISTS idx_login_events_timestamp ON login_events(login_timestamp DESC);

-- Composite index for user login history queries
CREATE INDEX IF NOT EXISTS idx_login_events_user_timestamp ON login_events(user_id, login_timestamp DESC);

-- Index for username lookups
CREATE INDEX IF NOT EXISTS idx_login_events_username ON login_events(username);

-- Enable Row Level Security (RLS)
ALTER TABLE login_events ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role full access
CREATE POLICY "Service role can manage all login events"
ON login_events
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Comments for documentation
COMMENT ON TABLE login_events IS 'Tracks user login events for analytics and auditing purposes';
COMMENT ON COLUMN login_events.user_id IS 'User ID from Odoo system';
COMMENT ON COLUMN login_events.username IS 'Username (email) from Odoo system';
COMMENT ON COLUMN login_events.login_timestamp IS 'Timestamp when the login occurred';
COMMENT ON COLUMN login_events.ip_address IS 'IP address of the user (optional, for security auditing)';
COMMENT ON COLUMN login_events.user_agent IS 'User agent string from browser (optional, for analytics)';
