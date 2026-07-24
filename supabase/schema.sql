-- AccessTwin Supabase schema for hack MVP
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
