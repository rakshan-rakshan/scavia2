-- Brigade Gateway Voice Agent — Supabase schema (PRD §7, source of truth).
-- Service key is used server-side only. RLS on; no anon writes.
-- Apply via: Supabase SQL editor, or `supabase db push`, or psql.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- leads: one row per qualified lead, captured incrementally by capture_lead.
-- ---------------------------------------------------------------------------
create table if not exists leads (
  id                 uuid primary key default gen_random_uuid(),
  source             text default 'voice_agent',
  name               text,
  email              text,
  phone              text,
  job                text,
  purpose            text,        -- self-use | investment | both | other
  budget_band        text,        -- '5-6 Cr' | '6-7 Cr' | '7-8 Cr' | '8 Cr+'
  timeline           text,        -- 'within 30 days' | '1-3 months' | 'after 3 months'
  visit_datetime     timestamptz,
  preferred_language text default 'english',
  outcome            text,        -- visit_booked | callback | not_interested | do_not_contact
  created_at         timestamptz default now(),
  updated_at         timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- call_logs: one row per session, with the full transcript + guardrail trail.
-- ---------------------------------------------------------------------------
create table if not exists call_logs (
  id               uuid primary key default gen_random_uuid(),
  lead_id          uuid references leads(id),
  channel          text,          -- 'browser' | 'acefone'
  transcript       jsonb,         -- ordered turns
  duration_seconds int,
  language_path    text[],        -- e.g. {english, hindi}
  guardrail_flags  jsonb,         -- any deflections/refusals fired
  created_at       timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- human_followup: queue of unknowns the bot deflected to a human (D9).
-- ---------------------------------------------------------------------------
create table if not exists human_followup (
  id         uuid primary key default gen_random_uuid(),
  lead_id    uuid references leads(id),
  question   text,
  context    text,
  status     text default 'open',  -- open | resolved
  created_at timestamptz default now()
);

create index if not exists leads_phone_idx           on leads (phone);
create index if not exists leads_outcome_idx         on leads (outcome);
create index if not exists call_logs_lead_idx        on call_logs (lead_id);
create index if not exists human_followup_status_idx on human_followup (status);

-- Auto-update leads.updated_at on change.
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

drop trigger if exists leads_updated_at on leads;
create trigger leads_updated_at before update on leads
  for each row execute function set_updated_at();

-- RLS: enabled with no policies => service key (which bypasses RLS) is the
-- only writer. No anon/auth client can read or write.
alter table leads          enable row level security;
alter table call_logs      enable row level security;
alter table human_followup enable row level security;
