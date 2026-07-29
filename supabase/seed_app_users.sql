-- AccessTwin demo users for public and authority-facing platforms.
-- This is intentionally lightweight for the hack MVP: real auth can later map
-- these profiles to Supabase Auth users via auth_user_id.
begin;

create table if not exists public.app_users (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  username text unique null,
  password_hash text null,
  display_name text not null,
  role text not null check (role in ('public','authority')),
  organization text null,
  persona_hint text null,
  auth_user_id uuid null,
  is_active boolean not null default true,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.app_users add column if not exists username text unique;
alter table public.app_users add column if not exists password_hash text;

insert into public.app_users (external_id, username, password_hash, display_name, role, organization, persona_hint, metadata) values
  ('public_wheelchair_commuter', 'nurul.public', 'demo-password-public', 'Nurul, wheelchair commuter', 'public', 'Clementi resident', 'wheelchair_user', '{"demo_user":true,"needs":"kerb ramps, clear width, obstruction-free paths"}'::jsonb),
  ('public_senior_walker', 'tan.public', 'demo-password-public', 'Mr Tan, senior with walker', 'public', 'Clementi resident', 'senior_walker', '{"demo_user":true,"needs":"shorter walks, rests, smoother surfaces"}'::jsonb),
  ('public_low_vision_commuter', 'aisha.public', 'demo-password-public', 'Aisha, visually impaired commuter', 'public', 'SMU volunteer tester', 'visually_impaired', '{"demo_user":true,"needs":"tactile continuity, safer crossings, wayfinding"}'::jsonb),
  ('authority_lta_planner', 'lta.planner', 'demo-password-authority', 'LTA accessibility planner', 'authority', 'Land Transport Authority', 'wheelchair_user', '{"demo_user":true,"scope":"transport accessibility prioritisation"}'::jsonb),
  ('authority_town_council', 'towncouncil.officer', 'demo-password-authority', 'Town council estate officer', 'authority', 'Clementi Town Council', 'senior_walker', '{"demo_user":true,"scope":"estate maintenance and obstruction triage"}'::jsonb),
  ('authority_sbs_operator', 'sbs.operator', 'demo-password-authority', 'SBS Transit operations reviewer', 'authority', 'SBS Transit', 'pma_user', '{"demo_user":true,"scope":"bus stop approach and interchange access"}'::jsonb)
on conflict (external_id) do update set
  username=excluded.username,
  password_hash=coalesce(public.app_users.password_hash, excluded.password_hash),
  display_name=excluded.display_name,
  role=excluded.role,
  organization=excluded.organization,
  persona_hint=excluded.persona_hint,
  metadata=excluded.metadata,
  is_active=true,
  updated_at=now();

commit;
