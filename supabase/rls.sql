-- JalanLens Supabase RLS starter policies.
-- Tighten roles once real authority accounts are created.

alter table public.streets enable row level security;
alter table public.street_parts enable row level security;
alter table public.street_photos enable row level security;
alter table public.street_view_nodes enable row level security;
alter table public.accessibility_features enable row level security;
alter table public.photo_feature_instances enable row level security;
alter table public.feedback_threads enable row level security;
alter table public.feedback_votes enable row level security;
alter table public.feedback_comments enable row level security;
alter table public.app_users enable row level security;
alter table public.persona_journey_runs enable row level security;
alter table public.authority_recommendations enable row level security;
alter table public.persona_types enable row level security;
alter table public.persona_agents enable row level security;
alter table public.simulation_runs enable row level security;
alter table public.agent_live_states enable row level security;
alter table public.agent_events enable row level security;
alter table public.agent_feedback_threads enable row level security;
alter table public.street_part_agent_counts enable row level security;
alter table public.environment_observations enable row level security;
alter table public.transit_stops enable row level security;
alter table public.transit_arrivals enable row level security;
alter table public.app_notifications enable row level security;

-- Public read for map/demo data.
drop policy if exists "public read streets" on public.streets;
create policy "public read streets" on public.streets for select using (true);

drop policy if exists "public read street parts" on public.street_parts;
create policy "public read street parts" on public.street_parts for select using (true);

drop policy if exists "public read active photos" on public.street_photos;
create policy "public read active photos" on public.street_photos
  for select using (
    is_active = true
    or validation_status in ('accepted', 'needs_review')
    or auth.uid() = submitted_by
  );

drop policy if exists "public read street nodes" on public.street_view_nodes;
create policy "public read street nodes" on public.street_view_nodes for select using (true);

drop policy if exists "public read features" on public.accessibility_features;
create policy "public read features" on public.accessibility_features for select using (true);

drop policy if exists "public read feature instances" on public.photo_feature_instances;
create policy "public read feature instances" on public.photo_feature_instances for select using (true);

drop policy if exists "public read feedback" on public.feedback_threads;
create policy "public read feedback" on public.feedback_threads for select using (true);

drop policy if exists "public read comments" on public.feedback_comments;
create policy "public read comments" on public.feedback_comments for select using (true);

drop policy if exists "public read feedback votes" on public.feedback_votes;
create policy "public read feedback votes" on public.feedback_votes for select using (true);

-- Public crowd-photo contributions. The frontend runs without login for the
-- hack demo, so accepted crowd uploads are inserted with submitted_by = null.
drop policy if exists "public insert accepted crowd photos" on public.street_photos;
create policy "public insert accepted crowd photos" on public.street_photos
  for insert with check (
    submitted_by is null
    and source = 'crowd'
    and validation_status = 'accepted'
    and is_active = true
  );

drop policy if exists "auth insert crowd photos" on public.street_photos;
create policy "auth insert crowd photos" on public.street_photos
  for insert with check (auth.uid() = submitted_by and source = 'crowd');

-- Public uploads write to Supabase Storage first, then street_photos.image_url.
insert into storage.buckets (id, name, public)
values ('street-photos', 'street-photos', true)
on conflict (id) do update set public = excluded.public;

drop policy if exists "public read street photo objects" on storage.objects;
create policy "public read street photo objects" on storage.objects
  for select using (bucket_id = 'street-photos');

drop policy if exists "public insert street photo objects" on storage.objects;
create policy "public insert street photo objects" on storage.objects
  for insert with check (bucket_id = 'street-photos');

drop policy if exists "public read demo users" on public.app_users;
create policy "public read demo users" on public.app_users for select using (is_active = true);

drop policy if exists "public update demo profiles" on public.app_users;
create policy "public update demo profiles" on public.app_users
  for update using (is_active = true)
  with check (is_active = true and role in ('public','authority'));

drop policy if exists "public signup demo users" on public.app_users;
create policy "public signup demo users" on public.app_users
  for insert with check (is_active = true and role in ('public','authority'));

-- Demo/anon feedback from the map UI (no auth yet).
drop policy if exists "public insert feedback threads" on public.feedback_threads;
create policy "public insert feedback threads" on public.feedback_threads
  for insert with check (created_by is null);

drop policy if exists "auth insert feedback threads" on public.feedback_threads;
create policy "auth insert feedback threads" on public.feedback_threads
  for insert with check (auth.uid() = created_by);

drop policy if exists "public insert feedback votes" on public.feedback_votes;
create policy "public insert feedback votes" on public.feedback_votes
  for insert with check (vote_type = 'upvote');

drop policy if exists "auth insert feedback votes" on public.feedback_votes;
create policy "auth insert feedback votes" on public.feedback_votes
  for insert with check (auth.uid() = user_id);

drop policy if exists "auth delete own feedback votes" on public.feedback_votes;
create policy "auth delete own feedback votes" on public.feedback_votes
  for delete using (auth.uid() = user_id);

drop policy if exists "auth insert comments" on public.feedback_comments;
create policy "auth insert comments" on public.feedback_comments
  for insert with check (auth.uid() = user_id and role = 'public');

-- Authority/admin writes should be done through service role or later replaced
-- with a custom JWT claim policy, e.g. auth.jwt()->>'role' = 'authority'.

-- Synthetic-agent simulation data: public/demo users can read combined map state,
-- while writes are intended for the service-role worker on the VPS.
drop policy if exists "public read persona types" on public.persona_types;
create policy "public read persona types" on public.persona_types for select using (true);

drop policy if exists "public read persona agents" on public.persona_agents;
create policy "public read persona agents" on public.persona_agents for select using (is_active = true);

drop policy if exists "public read simulation runs" on public.simulation_runs;
create policy "public read simulation runs" on public.simulation_runs for select using (true);

drop policy if exists "public read live agent states" on public.agent_live_states;
create policy "public read live agent states" on public.agent_live_states for select using (true);

drop policy if exists "public read agent events" on public.agent_events;
create policy "public read agent events" on public.agent_events for select using (true);

drop policy if exists "public read agent feedback" on public.agent_feedback_threads;
create policy "public read agent feedback" on public.agent_feedback_threads for select using (true);

drop policy if exists "public read street agent counts" on public.street_part_agent_counts;
create policy "public read street agent counts" on public.street_part_agent_counts for select using (true);

drop policy if exists "public read environment observations" on public.environment_observations;
create policy "public read environment observations" on public.environment_observations for select using (true);

drop policy if exists "public read transit stops" on public.transit_stops;
create policy "public read transit stops" on public.transit_stops for select using (true);

drop policy if exists "public read transit arrivals" on public.transit_arrivals;
create policy "public read transit arrivals" on public.transit_arrivals for select using (true);

drop policy if exists "public read app notifications" on public.app_notifications;
create policy "public read app notifications" on public.app_notifications for select using (true);

drop policy if exists "public insert app notifications" on public.app_notifications;
create policy "public insert app notifications" on public.app_notifications
  for insert with check (source in ('system','public','agent_simulation'));

grant select, insert, update on public.app_notifications to anon, authenticated;
