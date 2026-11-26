-- Supabase hardening for the production database (Supabase only: the anon
-- and authenticated roles do not exist on a local Postgres).
--
-- Supabase publishes every table in the public schema through its Data API
-- (PostgREST) and, by default, grants its anon and authenticated roles full
-- rights on them. The app never uses that API: it connects as the table owner
-- (postgres) through Hyperdrive or the pooler, which these changes do not
-- affect (an owner bypasses row-level security). Without this, anyone holding
-- the project's anon key, which Supabase treats as public, could read and
-- change every table over HTTPS.
--
-- Safe to re-run. Run after any migration that adds tables:
--   psql "<session URL with sslmode=verify-full and Supabase's root CA>" -f scripts/supabase-lockdown.sql
begin;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;

-- Tables, sequences and functions that migrations create later (as postgres).
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated;

-- Defence in depth: row-level security on, with no policies, so even a
-- future grant exposes no rows to the API roles.
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end $$;

commit;
