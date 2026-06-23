# Subagent: builder-data

Owns `app/db/` and `db/schema.sql`. Implements the Supabase client wrapper, `leads` and `human_followup` insert helpers, and any future migration scripts. Uses `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` from `app/config.py`.
