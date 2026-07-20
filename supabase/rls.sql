-- AccessTwin Supabase RLS starter policies.
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
alter table public.persona_journey_runs enable row level security;
alter table public.authority_recommendations enable row level security;

-- Public read for map/demo data.
drop policy if exists "public read streets" on public.streets;
create policy "public read streets" on public.streets for select using (true);

drop policy if exists "public read street parts" on public.street_parts;
create policy "public read street parts" on public.street_parts for select using (true);

drop policy if exists "public read active photos" on public.street_photos;
create policy "public read active photos" on public.street_photos for select using (is_active = true or auth.uid() = submitted_by);

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

-- Authenticated public contributions.
drop policy if exists "auth insert crowd photos" on public.street_photos;
create policy "auth insert crowd photos" on public.street_photos
  for insert with check (auth.uid() = submitted_by and source = 'crowd');

drop policy if exists "auth insert feedback threads" on public.feedback_threads;
create policy "auth insert feedback threads" on public.feedback_threads
  for insert with check (auth.uid() = created_by);

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
