-- Four-step crowd-photo workflow:
-- upload -> CV passed -> staff review -> approved active evidence.

alter table public.photo_review_jobs
  add column if not exists reviewer_external_id text null,
  add column if not exists review_comment text null,
  add column if not exists reviewed_at timestamptz null;

create table if not exists public.photo_review_comments (
  id uuid primary key default gen_random_uuid(),
  review_job_id uuid not null references public.photo_review_jobs(id) on delete cascade,
  photo_id uuid not null references public.street_photos(id) on delete cascade,
  author_external_id text null,
  author_role text not null default 'authority'
    check (author_role in ('public','authority','system')),
  body text not null check (char_length(body) between 1 and 2000),
  created_at timestamptz not null default now()
);

create index if not exists photo_review_comments_job_idx
  on public.photo_review_comments (review_job_id, created_at asc);

alter table public.photo_review_comments enable row level security;

drop policy if exists "public read photo review comments"
  on public.photo_review_comments;
create policy "public read photo review comments"
  on public.photo_review_comments for select using (true);

grant select on public.photo_review_comments to anon, authenticated;

drop policy if exists "public insert accepted crowd photos"
  on public.street_photos;
drop policy if exists "public insert pending crowd photos"
  on public.street_photos;
create policy "public insert pending crowd photos"
  on public.street_photos for insert with check (
    submitted_by is null
    and source = 'crowd'
    and validation_status = 'needs_review'
    and is_active = false
  );

create or replace function public.review_photo_submission(
  p_job_id uuid,
  p_decision text,
  p_reviewer_external_id text,
  p_comment text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job public.photo_review_jobs%rowtype;
  v_photo public.street_photos%rowtype;
begin
  if p_decision not in ('approved', 'rejected') then
    raise exception 'Decision must be approved or rejected';
  end if;

  select * into v_job
  from public.photo_review_jobs
  where id = p_job_id
  for update;

  if not found then
    raise exception 'Photo review job not found';
  end if;
  if v_job.review_stage <> 'staff_review'
     or v_job.cv_review_status <> 'passed'
     or v_job.human_review_status <> 'pending' then
    raise exception 'Photo is not awaiting staff review';
  end if;

  select * into v_photo
  from public.street_photos
  where id = v_job.photo_id
  for update;

  if not found then
    raise exception 'Submitted photo not found';
  end if;

  if p_decision = 'approved' then
    update public.street_photos
    set
      validation_status = 'accepted',
      is_active = false,
      selected_reason = 'crowd_upload_staff_approved',
      superseded_by = null
    where id = v_photo.id;
  else
    update public.street_photos
    set
      validation_status = 'rejected',
      is_active = false,
      selected_reason = 'crowd_upload_staff_rejected'
    where id = v_photo.id;
  end if;

  update public.photo_review_jobs
  set
    review_stage = p_decision,
    human_review_status = p_decision,
    reviewer_external_id = nullif(trim(p_reviewer_external_id), ''),
    review_comment = nullif(trim(p_comment), ''),
    reviewed_at = now(),
    updated_at = now()
  where id = v_job.id;

  if nullif(trim(p_comment), '') is not null then
    insert into public.photo_review_comments (
      review_job_id,
      photo_id,
      author_external_id,
      author_role,
      body
    ) values (
      v_job.id,
      v_photo.id,
      nullif(trim(p_reviewer_external_id), ''),
      'authority',
      trim(p_comment)
    );
  end if;

  return jsonb_build_object(
    'job_id', v_job.id,
    'photo_id', v_photo.id,
    'decision', p_decision,
    'street_part_id', v_photo.street_part_id
  );
end;
$$;

revoke all on function public.review_photo_submission(uuid, text, text, text)
  from public;
grant execute on function public.review_photo_submission(uuid, text, text, text)
  to anon, authenticated;

create table if not exists public.photo_activation_events (
  id uuid primary key default gen_random_uuid(),
  street_part_id uuid not null references public.street_parts(id) on delete cascade,
  previous_photo_id uuid null references public.street_photos(id) on delete set null,
  activated_photo_id uuid not null references public.street_photos(id) on delete cascade,
  actor_external_id text null,
  created_at timestamptz not null default now()
);

create index if not exists photo_activation_events_part_idx
  on public.photo_activation_events (street_part_id, created_at desc);

alter table public.photo_activation_events enable row level security;

drop policy if exists "public read photo activation events"
  on public.photo_activation_events;
create policy "public read photo activation events"
  on public.photo_activation_events for select using (true);

grant select on public.photo_activation_events to anon, authenticated;

create or replace function public.activate_approved_photo(
  p_photo_id uuid,
  p_actor_external_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_photo public.street_photos%rowtype;
  v_previous_photo_id uuid;
begin
  select * into v_photo
  from public.street_photos
  where id = p_photo_id
  for update;

  if not found then
    raise exception 'Approved photo not found';
  end if;
  if v_photo.validation_status <> 'accepted' then
    raise exception 'Only an approved photo can be made active';
  end if;

  select active_photo_id into v_previous_photo_id
  from public.street_parts
  where id = v_photo.street_part_id
  for update;

  if v_previous_photo_id = v_photo.id and v_photo.is_active then
    return jsonb_build_object(
      'street_part_id', v_photo.street_part_id,
      'previous_photo_id', v_previous_photo_id,
      'activated_photo_id', v_photo.id,
      'unchanged', true
    );
  end if;

  update public.street_photos
  set
    is_active = false,
    superseded_by = v_photo.id
  where street_part_id = v_photo.street_part_id
    and is_active = true
    and id <> v_photo.id;

  update public.street_photos
  set
    is_active = true,
    superseded_by = null,
    selected_reason = 'authority_confirmed_active_replacement'
  where id = v_photo.id;

  update public.street_parts
  set
    active_photo_id = v_photo.id,
    updated_at = now()
  where id = v_photo.street_part_id;

  insert into public.photo_activation_events (
    street_part_id,
    previous_photo_id,
    activated_photo_id,
    actor_external_id
  ) values (
    v_photo.street_part_id,
    v_previous_photo_id,
    v_photo.id,
    nullif(trim(p_actor_external_id), '')
  );

  return jsonb_build_object(
    'street_part_id', v_photo.street_part_id,
    'previous_photo_id', v_previous_photo_id,
    'activated_photo_id', v_photo.id,
    'unchanged', false
  );
end;
$$;

revoke all on function public.activate_approved_photo(uuid, text) from public;
grant execute on function public.activate_approved_photo(uuid, text)
  to anon, authenticated;
