-- JalanLens Supabase schema for hack MVP
-- Portable to Huawei Cloud RDS/Postgres later.

create extension if not exists pgcrypto;

create table if not exists public.streets (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  name text not null,
  geometry jsonb not null,
  midpoint_lng double precision not null,
  midpoint_lat double precision not null,
  direction_bearing_deg double precision not null,
  desired_orientation text not null default 'road_right',
  length_m double precision not null,
  metrics jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.street_parts (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  street_id uuid null references public.streets(id) on delete cascade,
  route_segment_ids text[] not null default '{}',
  geometry jsonb not null,
  midpoint_lng double precision not null,
  midpoint_lat double precision not null,
  direction_bearing_deg double precision not null,
  desired_orientation text not null default 'road_right',
  length_m double precision not null,
  metrics jsonb not null default '{}',
  active_photo_id uuid null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.street_parts
  add column if not exists street_id uuid null references public.streets(id) on delete cascade;

create table if not exists public.street_photos (
  id uuid primary key default gen_random_uuid(),
  external_id text unique null,
  street_part_id uuid not null references public.street_parts(id) on delete cascade,
  street_view_node_id uuid null,
  source text not null check (source in ('mapillary','crowd')),
  source_image_id text null,
  image_url text null,
  storage_path text null,
  captured_at timestamptz null,
  submitted_at timestamptz not null default now(),
  submitted_by uuid null,
  lng double precision not null,
  lat double precision not null,
  compass_angle_deg double precision null,
  matched_heading_deg double precision null,
  heading_role text null,
  desired_orientation text null,
  direction_valid boolean not null default false,
  direction_confidence double precision null,
  road_on_right_score double precision null,
  quality_score double precision null,
  is_pano boolean not null default false,
  is_active boolean not null default false,
  validation_status text not null default 'needs_review',
  selected_reason text null,
  superseded_by uuid null references public.street_photos(id),
  replaces_photo_id uuid null references public.street_photos(id),
  metadata jsonb not null default '{}'
);

alter table public.street_photos
  add column if not exists external_id text unique,
  add column if not exists street_view_node_id uuid null,
  add column if not exists validation_status text not null default 'needs_review',
  add column if not exists matched_heading_deg double precision null,
  add column if not exists heading_role text null,
  add column if not exists desired_orientation text null,
  add column if not exists selected_reason text null,
  add column if not exists replaces_photo_id uuid null references public.street_photos(id);

alter table public.street_parts
  drop constraint if exists street_parts_active_photo_id_fkey;

alter table public.street_parts
  add constraint street_parts_active_photo_id_fkey
  foreign key (active_photo_id) references public.street_photos(id) deferrable initially deferred;

create table if not exists public.street_view_nodes (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  street_part_id uuid not null references public.street_parts(id) on delete cascade,
  street_id uuid null references public.streets(id) on delete cascade,
  active_photo_id uuid null references public.street_photos(id),
  sequence_id text null,
  sequence_index integer null,
  lng double precision not null,
  lat double precision not null,
  canonical_heading_deg double precision not null,
  desired_orientation text not null default 'road_right',
  prev_node_external_id text null,
  next_node_external_id text null,
  left_node_external_id text null,
  right_node_external_id text null,
  coverage_status text not null default 'missing',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.street_view_nodes
  add column if not exists street_id uuid null references public.streets(id) on delete cascade;

alter table public.street_photos
  drop constraint if exists street_photos_street_view_node_id_fkey;

alter table public.street_photos
  add constraint street_photos_street_view_node_id_fkey
  foreign key (street_view_node_id) references public.street_view_nodes(id) on delete set null;

create table if not exists public.accessibility_features (
  id uuid primary key default gen_random_uuid(),
  external_id text unique null,
  kind text not null,
  name text null,
  geometry jsonb not null,
  source text not null default 'lta_osm_proxy',
  properties jsonb not null default '{}'
);

create table if not exists public.photo_feature_instances (
  id uuid primary key default gen_random_uuid(),
  photo_id uuid not null references public.street_photos(id) on delete cascade,
  feature_id uuid not null references public.accessibility_features(id) on delete cascade,
  street_part_id uuid not null references public.street_parts(id) on delete cascade,
  visible boolean not null default true,
  pixel_x double precision null,
  pixel_y double precision null,
  bbox jsonb null,
  detection_method text not null default 'geo_projection',
  detection_model text null,
  detection_label text null,
  confidence double precision not null default 0,
  created_at timestamptz not null default now(),
  unique(photo_id, feature_id)
);

alter table public.photo_feature_instances
  add column if not exists detection_model text null,
  add column if not exists detection_label text null;

create table if not exists public.feedback_threads (
  id uuid primary key default gen_random_uuid(),
  street_part_id uuid not null references public.street_parts(id) on delete cascade,
  feature_id uuid null references public.accessibility_features(id) on delete set null,
  created_by uuid null,
  title text not null,
  body text not null,
  status text not null default 'open',
  priority_score double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.feedback_votes (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.feedback_threads(id) on delete cascade,
  user_id uuid not null,
  vote_type text not null default 'upvote',
  created_at timestamptz not null default now(),
  unique(thread_id, user_id)
);

create table if not exists public.feedback_comments (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.feedback_threads(id) on delete cascade,
  user_id uuid null,
  role text not null check (role in ('public','authority','system')),
  body text not null,
  created_at timestamptz not null default now()
);

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

create index if not exists app_users_role_active_idx on public.app_users (role, is_active);

create table if not exists public.persona_journey_runs (
  id uuid primary key default gen_random_uuid(),
  persona text not null,
  start_node_external_id text not null,
  end_node_external_id text not null,
  route_node_external_ids text[] not null default '{}',
  journey_score integer not null,
  blockers jsonb not null default '[]',
  summary text not null,
  created_by uuid null,
  created_at timestamptz not null default now()
);

create table if not exists public.authority_recommendations (
  id uuid primary key default gen_random_uuid(),
  journey_run_id uuid null references public.persona_journey_runs(id) on delete set null,
  street_part_id uuid not null references public.street_parts(id) on delete cascade,
  feature_id uuid null references public.accessibility_features(id) on delete set null,
  kind text not null,
  before_score integer not null,
  after_score_estimate integer not null,
  estimated_cost_band text not null,
  practicality text not null,
  notes text not null,
  status text not null default 'pending_authority_review',
  created_at timestamptz not null default now()
);

create index if not exists streets_midpoint_idx on public.streets (midpoint_lng, midpoint_lat);
create index if not exists street_parts_street_idx on public.street_parts (street_id);
create index if not exists street_parts_midpoint_idx on public.street_parts (midpoint_lng, midpoint_lat);
create index if not exists street_photos_part_active_idx on public.street_photos (street_part_id, is_active);
create index if not exists street_nodes_street_idx on public.street_view_nodes (street_id);
create index if not exists street_nodes_part_idx on public.street_view_nodes (street_part_id);
create index if not exists feedback_threads_part_idx on public.feedback_threads (street_part_id, status);

-- Live synthetic persona-agent simulation. Agent feedback is stored separately
-- from real public feedback, then combined in the authority/public dashboard.
create table if not exists public.persona_types (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  label text not null,
  category text not null check (category in ('disabled','access_relevant','general')),
  color text not null,
  description text not null,
  mobility_profile jsonb not null default '{}',
  schedule_profile jsonb not null default '{}',
  source_notes jsonb not null default '[]',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.persona_agents (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  display_name text not null,
  persona_type_id uuid null references public.persona_types(id) on delete set null,
  persona_type_external_id text not null,
  resident_status text not null check (resident_status in ('resident','visitor','worker_student_inbound')),
  age_band text not null,
  sex text null,
  home_subzone text null,
  baseline_speed_mps double precision not null,
  routine_seed integer not null,
  traits jsonb not null default '{}',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.simulation_runs (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  status text not null default 'running' check (status in ('running','paused','stopped','replay')),
  sim_timezone text not null default 'Asia/Singapore',
  tick_seconds integer not null default 10,
  config jsonb not null default '{}',
  started_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.agent_live_states (
  agent_id uuid primary key references public.persona_agents(id) on delete cascade,
  simulation_run_id uuid null references public.simulation_runs(id) on delete cascade,
  sim_time timestamptz not null default now(),
  activity text not null,
  lng double precision not null,
  lat double precision not null,
  street_part_id uuid null references public.street_parts(id) on delete set null,
  street_part_external_id text null,
  street_view_node_id uuid null references public.street_view_nodes(id) on delete set null,
  current_trip jsonb not null default '{}',
  route_plan jsonb not null default '{}',
  state jsonb not null default '{}',
  updated_at timestamptz not null default now()
);

create table if not exists public.agent_events (
  id uuid primary key default gen_random_uuid(),
  simulation_run_id uuid null references public.simulation_runs(id) on delete cascade,
  agent_id uuid null references public.persona_agents(id) on delete set null,
  agent_external_id text null,
  persona_type text not null,
  event_type text not null,
  street_part_id uuid null references public.street_parts(id) on delete set null,
  street_part_external_id text null,
  feature_id uuid null references public.accessibility_features(id) on delete set null,
  occurred_at timestamptz not null default now(),
  severity double precision not null default 0,
  payload jsonb not null default '{}'
);

create table if not exists public.agent_feedback_threads (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid null references public.persona_agents(id) on delete set null,
  agent_external_id text not null,
  agent_name text not null,
  persona_type text not null,
  event_id uuid null references public.agent_events(id) on delete set null,
  street_part_id uuid null references public.street_parts(id) on delete cascade,
  street_part_external_id text null,
  feature_id uuid null references public.accessibility_features(id) on delete set null,
  event_type text not null,
  title text not null,
  body text not null,
  status text not null default 'open',
  priority_score double precision not null default 0,
  severity double precision not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(agent_external_id, street_part_external_id, event_type, persona_type, created_at)
);

create table if not exists public.street_part_agent_counts (
  street_part_id uuid null references public.street_parts(id) on delete cascade,
  street_part_external_id text not null,
  simulation_run_id uuid null references public.simulation_runs(id) on delete cascade,
  bucket_started_at timestamptz not null default date_trunc('minute', now()),
  persona_counts jsonb not null default '{}',
  total_count integer not null default 0,
  weather_snapshot jsonb not null default '{}',
  transit_snapshot jsonb not null default '{}',
  primary key (street_part_external_id, bucket_started_at)
);

create table if not exists public.environment_observations (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  observed_at timestamptz not null,
  lng double precision null,
  lat double precision null,
  kind text not null,
  value double precision null,
  unit text null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create table if not exists public.transit_stops (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  stop_type text not null check (stop_type in ('bus_stop','mrt_station','taxi_stand')),
  name text not null,
  lng double precision not null,
  lat double precision not null,
  metadata jsonb not null default '{}'
);

create table if not exists public.transit_arrivals (
  id uuid primary key default gen_random_uuid(),
  stop_external_id text not null,
  service_no text null,
  observed_at timestamptz not null,
  eta_seconds integer null,
  load text null,
  wheelchair_bay_proxy text null,
  payload jsonb not null default '{}'
);

alter table public.app_users
  add column if not exists public_persona_type text null,
  add column if not exists demographic_profile jsonb not null default '{}',
  add column if not exists company_external_id text null,
  add column if not exists managed_by_user_external_id text null,
  add column if not exists employee_id text null,
  add column if not exists full_name text null,
  add column if not exists department text null,
  add column if not exists position_title text null,
  add column if not exists salutation text null,
  add column if not exists platform_purpose text null,
  add column if not exists is_company_admin boolean not null default false;

alter table public.feedback_threads
  add column if not exists source text not null default 'public',
  add column if not exists public_user_external_id text null,
  add column if not exists public_user_name text null,
  add column if not exists persona_type text null,
  add column if not exists original_language text null,
  add column if not exists original_text text null,
  add column if not exists english_translation text null,
  add column if not exists translation_status text not null default 'not_required',
  add column if not exists translation_provider text null,
  add column if not exists translation_model text null,
  add column if not exists speech_transcript_original text null,
  add column if not exists input_modality text not null default 'typed';

create index if not exists persona_agents_type_idx on public.persona_agents (persona_type_external_id, is_active);
create index if not exists agent_live_states_part_idx on public.agent_live_states (street_part_external_id, updated_at desc);
create index if not exists agent_events_part_time_idx on public.agent_events (street_part_external_id, occurred_at desc);
create index if not exists agent_feedback_part_time_idx on public.agent_feedback_threads (street_part_external_id, created_at desc);
create index if not exists agent_feedback_persona_idx on public.agent_feedback_threads (persona_type, created_at desc);
create index if not exists public_feedback_source_idx on public.feedback_threads (source, persona_type, created_at desc);
create index if not exists feedback_threads_translation_idx on public.feedback_threads (original_language, translation_status, created_at desc);

create table if not exists public.app_notifications (
  id uuid primary key default gen_random_uuid(),
  external_id text unique not null,
  source text not null default 'system' check (source in ('system','public','agent_simulation')),
  title text not null,
  body text not null default '',
  street_part_id uuid null references public.street_parts(id) on delete set null,
  street_part_external_id text null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists app_notifications_created_idx on public.app_notifications (created_at desc);
create index if not exists app_notifications_part_idx on public.app_notifications (street_part_external_id, created_at desc);

grant select, insert, update on public.app_notifications to anon, authenticated;

create table if not exists public.photo_review_jobs (
  id uuid primary key default gen_random_uuid(),
  photo_id uuid null references public.street_photos(id) on delete cascade,
  submitted_by_user_external_id text null,
  company_external_id text null,
  street_part_external_id text null,
  review_stage text not null default 'cv_first_review' check (review_stage in ('uploaded','cv_first_review','staff_review','approved','rejected')),
  cv_review_status text not null default 'pending',
  human_review_status text not null default 'pending',
  assigned_staff_external_ids text[] not null default '{}',
  progress_payload jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists app_users_company_idx on public.app_users (company_external_id, role, is_active);
create index if not exists photo_review_jobs_company_stage_idx on public.photo_review_jobs (company_external_id, review_stage, created_at desc);

grant select, insert, update on public.photo_review_jobs to anon, authenticated;
