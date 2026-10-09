-- =====================================================================
-- BuildrBank schema.
--
-- Copied verbatim from the cohort's own setup notebook:
--   agentic-ai-cohort-01-phase-01 - branch week-06
--   Week 06/notebooks/00_setup_supabase.ipynb  (Step 3)
--
-- HOW TO RUN IT
--   Supabase dashboard -> SQL Editor -> New query
--   -> paste this whole file -> Run
--
-- It is safe to run more than once.
-- It creates the tables and search functions but loads NO data;
-- `python scripts/seed.py` does that afterwards.
-- =====================================================================

-- ==================================================
-- WEEK 06 · BUILDRBANK AGENTIC MEMORY — FULL SCHEMA
-- Idempotent: safe on a fresh project AND on re-runs.
-- ==================================================

-- ============ EXTENSION ============
create extension if not exists vector;

-- Heal earlier schema versions: remove vector indexes if present.
-- (IVFFlat built on empty tables has untrained centroids — with the default
--  probes=1, similarity queries can return ZERO rows despite seeded data.)
drop index if exists idx_mem_facts_vec;
drop index if exists idx_mem_episodes_vec;
drop index if exists idx_mem_procedures_vec;
drop index if exists idx_kb_chunks_vec;
drop index if exists idx_cag_cache_vec;

-- NOTE: no vector indexes (IVFFlat/HNSW) at class scale — ON PURPOSE.
-- pgvector answers similarity queries EXACTLY without an index, and at
-- <10k rows that takes microseconds.
-- Production recipe: bulk-load FIRST, then
--   create index on kb_chunks using ivfflat (embedding vector_cosine_ops)
--     with (lists = <~sqrt(row_count)>);
-- and tune ivfflat.probes for the recall you need.

-- ============ TIER 1 · SHORT-TERM MEMORY ============
create table if not exists st_turns (
  id          uuid primary key default gen_random_uuid(),
  user_id     text not null,
  session_id  text not null,
  role        text not null check (role in ('user','assistant','system')),
  content     text not null,
  created_at  timestamptz not null default now(),
  ttl_at      timestamptz not null default now() + interval '24 hours'
);
create index if not exists idx_st_turns_lookup on st_turns (user_id, session_id, created_at desc);
create index if not exists idx_st_turns_ttl on st_turns (ttl_at);

-- ============ TIER 2 · SEMANTIC MEMORY ============
create table if not exists mem_facts (
  id           uuid primary key default gen_random_uuid(),
  user_id      text not null,
  fact         text not null,
  embedding    vector(1536) not null,
  score        real not null default 0.5,
  tags         jsonb default '[]',
  created_at   timestamptz not null default now(),
  last_used_at timestamptz not null default now(),
  ttl_at       timestamptz not null default now() + interval '90 days',
  pinned       boolean not null default false,
  deleted      boolean not null default false
);
create index if not exists idx_mem_facts_user on mem_facts (user_id);

-- ============ TIER 3 · EPISODIC MEMORY ============
create table if not exists mem_episodes (
  id                uuid primary key default gen_random_uuid(),
  user_id           text not null,
  session_id        text not null,
  summary           text not null,
  summary_embedding vector(1536) not null,
  topic_tags        jsonb default '[]',
  started_at        timestamptz,
  ended_at          timestamptz,
  turn_count        integer,
  turns             jsonb not null
);
create index if not exists idx_mem_episodes_user on mem_episodes (user_id);

-- ============ TIER 4 · PROCEDURAL MEMORY ============
create table if not exists mem_procedures (
  id           uuid primary key default gen_random_uuid(),
  name         text not null unique,
  description  text not null,
  context_when text,
  steps        jsonb not null,
  conditions   jsonb default '[]',
  examples     jsonb default '[]',
  embedding    vector(1536) not null,
  category     text,
  active       boolean not null default true,
  version      integer not null default 1
);

-- ============ RAG KNOWLEDGE BASE ============
create table if not exists kb_chunks (
  id          uuid primary key default gen_random_uuid(),
  source      text not null,
  chunk_index integer not null,
  content     text not null,
  embedding   vector(1536) not null,
  created_at  timestamptz not null default now()
);

-- ============ CAG SEMANTIC CACHE ============
create table if not exists cag_cache (
  id              uuid primary key default gen_random_uuid(),
  query           text not null,
  query_embedding vector(1536) not null,
  answer          text not null,
  hit_count       integer not null default 0,
  created_at      timestamptz not null default now(),
  ttl_at          timestamptz not null default now() + interval '7 days'
);

-- ==================================================
-- CRM SYSTEM (BuildrBank)
-- ==================================================

create table if not exists customers (
  customer_id  text primary key,
  full_name    text not null,
  email        text not null unique,
  phone        text,
  segment      text not null check (segment in ('retail','vip','business')),
  risk_profile text check (risk_profile in ('conservative','moderate','aggressive')),
  kyc_status   text not null default 'verified',
  created_at   timestamptz not null default now(),
  active       boolean not null default true
);

create table if not exists branches (
  branch_id      text primary key,
  name           text not null,
  address        text,
  city           text,
  tz             text default 'Asia/Colombo',
  phone          text,
  extended_hours boolean not null default false,
  active         boolean not null default true
);

create table if not exists relationship_managers (
  rm_id     text primary key,
  full_name text not null,
  branch_id text references branches(branch_id),
  email     text,
  phone     text,
  active    boolean not null default true
);

create table if not exists accounts (
  account_id   text primary key,
  customer_id  text not null references customers(customer_id),
  account_type text not null check (account_type in
    ('savings','checking','business_checking','fixed_deposit','foreign_currency')),
  balance      numeric(14,2) not null default 0,
  currency     text not null default 'LKR',
  opened_at    timestamptz not null default now(),
  status       text not null default 'active'
);

create table if not exists transactions (
  tx_id        text primary key,
  account_id   text not null references accounts(account_id),
  tx_type      text not null check (tx_type in
    ('wire_outgoing','wire_incoming','card_purchase','atm_withdrawal',
     'salary_credit','loan_disbursement','utility_payment')),
  amount       numeric(14,2) not null,
  currency     text not null default 'LKR',
  counterparty text,
  status       text not null check (status in
    ('submitted','in_review','processing','settled','returned')),
  reference    text unique,
  created_at   timestamptz not null default now(),
  notes        text
);
create index if not exists idx_tx_account on transactions (account_id, created_at desc);

create table if not exists appointments (
  appointment_id text primary key,
  customer_id    text not null references customers(customer_id),
  rm_id          text references relationship_managers(rm_id),
  branch_id      text references branches(branch_id),
  reason         text,
  start_at       timestamptz,
  end_at         timestamptz,
  status         text not null default 'confirmed' check (status in
    ('pending','confirmed','cancelled','rescheduled','no_show','completed')),
  source         text default 'agent'
);

-- ==================================================
-- VECTOR-SEARCH FUNCTIONS (called via client.rpc)
-- ==================================================

create or replace function match_facts(
  query_embedding vector(1536),
  match_user_id   text,
  match_count     int default 5
) returns table (id uuid, fact text, score real, similarity float)
language sql stable as $$
  select f.id, f.fact, f.score,
         1 - (f.embedding <=> query_embedding) as similarity
  from mem_facts f
  where f.user_id = match_user_id
    and not f.deleted
    and (f.pinned or f.ttl_at > now())
  order by f.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function match_episodes(
  query_embedding vector(1536),
  match_user_id   text,
  match_count     int default 3
) returns table (id uuid, summary text, turns jsonb, ended_at timestamptz, similarity float)
language sql stable as $$
  select e.id, e.summary, e.turns, e.ended_at,
         1 - (e.summary_embedding <=> query_embedding) as similarity
  from mem_episodes e
  where e.user_id = match_user_id
  order by e.summary_embedding <=> query_embedding
  limit match_count;
$$;

create or replace function match_procedures(
  query_embedding vector(1536),
  match_count     int default 1
) returns table (id uuid, name text, description text, steps jsonb, similarity float)
language sql stable as $$
  select p.id, p.name, p.description, p.steps,
         1 - (p.embedding <=> query_embedding) as similarity
  from mem_procedures p
  where p.active
  order by p.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function match_kb_chunks(
  query_embedding vector(1536),
  match_count     int default 3
) returns table (id uuid, content text, source text, similarity float)
language sql stable as $$
  select k.id, k.content, k.source,
         1 - (k.embedding <=> query_embedding) as similarity
  from kb_chunks k
  order by k.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function match_cache(
  query_embedding vector(1536)
) returns table (id uuid, query text, answer text, similarity float)
language sql stable as $$
  select c.id, c.query, c.answer,
         1 - (c.query_embedding <=> query_embedding) as similarity
  from cag_cache c
  where c.ttl_at > now()
  order by c.query_embedding <=> query_embedding
  limit 1;
$$;

create or replace function cleanup_expired()
returns table (st_deleted bigint, cache_deleted bigint)
language plpgsql as $$
declare a bigint; b bigint;
begin
  delete from st_turns where ttl_at < now();
  get diagnostics a = row_count;
  delete from cag_cache where ttl_at < now();
  get diagnostics b = row_count;
  return query select a, b;
end $$;
