-- Migration: store Sales whitelist flag at refresh-token issue time.
-- Used by backend AuthTokenService when revoking remember-me after a user loses Sales access
-- (especially when the Flask session cookie expired but nasma_refresh_token is still valid).
--
-- Run in Supabase SQL Editor (or any Postgres client connected to your project).

ALTER TABLE refresh_tokens
  ADD COLUMN IF NOT EXISTS sales_eligible_at_issue BOOLEAN NULL;

COMMENT ON COLUMN refresh_tokens.sales_eligible_at_issue IS
  'Whether the user was on DASHBOARD_ALLOWED_EMAILS when this token was created; used to detect Sales whitelist removal across session expiry.';
