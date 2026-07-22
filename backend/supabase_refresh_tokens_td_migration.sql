-- Adds storage for the Odoo trusted-device key (auth_totp 'td_id') to
-- refresh tokens, so auto-login can silently re-authenticate accounts that
-- have two-factor authentication enabled (no TOTP prompt on every visit).
-- The key is encrypted with the refresh token, same scheme as
-- encrypted_password. Code tolerates this column being absent, but 2FA
-- users will be asked to log in manually once their Flask session expires
-- until it exists.
--
-- NOTE: if this Supabase project is shared with Nasma, its
-- supabase_refresh_tokens_td_migration.sql may already have added this
-- column; running this again is harmless (IF NOT EXISTS).

ALTER TABLE refresh_tokens
    ADD COLUMN IF NOT EXISTS encrypted_td TEXT;
