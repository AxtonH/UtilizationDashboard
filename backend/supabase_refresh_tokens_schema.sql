-- Refresh Tokens Table Schema for Supabase
-- This table stores refresh tokens for JWT-based authentication

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    username VARCHAR(255) NOT NULL,
    encrypted_password TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE NULL,
    -- Set at token creation; see supabase_migration_refresh_tokens_sales_eligible_at_issue.sql for existing DBs
    sales_eligible_at_issue BOOLEAN NULL,
    
    -- Indexes for faster lookups
    CONSTRAINT refresh_tokens_token_hash_unique UNIQUE (token_hash)
);

-- Existing databases created before sales_eligible_at_issue was added (safe to re-run)
ALTER TABLE refresh_tokens
  ADD COLUMN IF NOT EXISTS sales_eligible_at_issue BOOLEAN NULL;

-- Index for user_id lookups
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);

-- Index for token_hash lookups (already covered by unique constraint, but explicit for clarity)
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

-- Index for finding active (non-revoked) tokens
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active ON refresh_tokens(user_id, revoked_at) WHERE revoked_at IS NULL;

-- Enable Row Level Security (RLS)
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role full access (drop first so this script is re-runnable)
-- Note: Your backend uses SUPABASE_SERVICE_ROLE which bypasses RLS,
-- but this policy is good practice for explicit permissions
DROP POLICY IF EXISTS "Service role can manage all tokens" ON refresh_tokens;
CREATE POLICY "Service role can manage all tokens"
ON refresh_tokens
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Comments for documentation
COMMENT ON TABLE refresh_tokens IS 'Stores refresh tokens for JWT-based authentication. Tokens are hashed before storage.';
COMMENT ON COLUMN refresh_tokens.token_hash IS 'SHA-256 hash of the refresh token';
COMMENT ON COLUMN refresh_tokens.user_id IS 'User ID from Odoo system';
COMMENT ON COLUMN refresh_tokens.username IS 'Username from Odoo system';
COMMENT ON COLUMN refresh_tokens.encrypted_password IS 'Encrypted password (XOR encrypted with refresh token as key)';
COMMENT ON COLUMN refresh_tokens.created_at IS 'Timestamp when token was created';
COMMENT ON COLUMN refresh_tokens.revoked_at IS 'Timestamp when token was revoked (NULL if still active)';
COMMENT ON COLUMN refresh_tokens.sales_eligible_at_issue IS 'Whether the user was on DASHBOARD_ALLOWED_EMAILS when this token was created';
