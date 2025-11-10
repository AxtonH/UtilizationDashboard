# Supabase Setup Guide for External Hours Cache

This guide will help you set up Supabase to cache monthly external hours data, significantly improving dashboard performance.

## Step 1: Create a Supabase Project

1. Go to [https://supabase.com](https://supabase.com) and sign up or log in
2. Click "New Project"
3. Fill in the project details:
   - **Name**: Choose a name (e.g., "UTDashboardCache")
   - **Database Password**: Choose a strong password (save this!)
   - **Region**: Choose the region closest to your server
   - **Pricing Plan**: Free tier is sufficient for this use case
4. Click "Create new project" and wait for it to initialize (takes 1-2 minutes)

## Step 2: Get Your Supabase Credentials

1. Once your project is ready, go to **Settings** → **API**
2. Find the following values:
   - **Project URL**: Copy this (looks like `https://xxxxx.supabase.co`)
   - **Service Role Key**: Copy this (starts with `eyJ...` - keep this secret!)
   
   ⚠️ **Important**: Use the **Service Role Key**, not the anon key. The service role key has full database access and is safe for server-side use.

## Step 3: Create the Database Table

1. In your Supabase dashboard, go to **SQL Editor**
2. Click "New Query"
3. Copy and paste the entire contents of `backend/supabase_schema.sql`
4. Click "Run" (or press Ctrl+Enter)
5. Verify the table was created:
   - Go to **Table Editor**
   - You should see `external_hours_monthly_cache` table

## Step 4: Configure Environment Variables

Add the following environment variables to your `.env` file (or your environment configuration):

```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Replace:
- `SUPABASE_URL` with your Project URL from Step 2
- `SUPABASE_KEY` with your Service Role Key from Step 2

## Step 5: Install Dependencies

Install the Supabase Python client:

```bash
pip install -r backend/requirements.txt
```

Or install directly:

```bash
pip install supabase==2.3.4
```

## Step 6: Verify Setup

1. Start your Flask application
2. Load the dashboard - it should work normally
3. Check your Supabase dashboard → **Table Editor** → `external_hours_monthly_cache`
4. After loading the dashboard, you should see rows appearing in the table (one per month)

## How It Works

### Automatic Caching
- When the dashboard loads, it checks Supabase for cached monthly data
- If data exists for a month, it uses the cached version (fast!)
- If data is missing, it fetches from Odoo and saves to Supabase
- The current month is **always** refreshed from Odoo to ensure freshness

### Refresh Button
- Click the refresh button (🔄) next to the Used/Sold toggle
- This forces a refresh of **all** months from Odoo
- Useful when you need the latest data immediately

### Performance Benefits
- **First load**: Fetches all months from Odoo (same as before)
- **Subsequent loads**: Loads instantly from Supabase cache
- **Current month**: Always fresh from Odoo
- **Manual refresh**: Refresh button for on-demand updates

## Troubleshooting

### Dashboard still slow
- Check that `SUPABASE_URL` and `SUPABASE_KEY` are set correctly
- Check Flask logs for Supabase connection errors
- Verify the table exists in Supabase

### No data in Supabase table
- Check Flask logs for errors
- Verify Odoo connection is working
- Try clicking the refresh button to force data fetch

### Supabase connection errors
- Verify your Service Role Key is correct (not the anon key)
- Check that your Supabase project is active
- Ensure your server can reach Supabase (network/firewall)

### Data seems stale
- The current month is always refreshed on dashboard load
- Use the refresh button to update all months
- Old months remain cached unless manually refreshed

## Security Notes

- The Service Role Key has full database access - keep it secret!
- Never commit `.env` files with credentials to version control
- Use environment variables or a secrets manager in production
- The RLS policy allows all operations - adjust if you need stricter access control

## Optional: Adjust RLS Policies

If you want stricter security, you can modify the RLS policy in `supabase_schema.sql`:

```sql
-- Example: Only allow service role
CREATE POLICY "Allow service role only"
    ON external_hours_monthly_cache
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
```

## Support

If you encounter issues:
1. Check Flask application logs
2. Check Supabase dashboard logs (Settings → Logs)
3. Verify all environment variables are set correctly
4. Ensure the table schema matches `supabase_schema.sql`









