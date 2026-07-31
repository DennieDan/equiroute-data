-- JalanLens feedback reply threads: public/authority/agent responses.

create table if not exists public.feedback_replies (
  id uuid primary key default gen_random_uuid(),
  parent_source text not null check (parent_source in ('public','agent_simulation')),
  parent_thread_id uuid null references public.feedback_threads(id) on delete cascade,
  parent_agent_thread_id uuid null references public.agent_feedback_threads(id) on delete cascade,
  author_role text not null check (author_role in ('public','authority','agent','system')),
  author_external_id text null,
  author_name text not null default 'JalanLens user',
  body text not null,
  original_language text null,
  original_text text null,
  english_translation text null,
  translation_status text not null default 'not_required',
  translation_provider text null,
  translation_model text null,
  input_modality text not null default 'typed',
  created_at timestamptz not null default now(),
  constraint feedback_replies_exactly_one_parent check (
    (parent_source = 'public' and parent_thread_id is not null and parent_agent_thread_id is null)
    or (parent_source = 'agent_simulation' and parent_agent_thread_id is not null and parent_thread_id is null)
  )
);

create index if not exists feedback_replies_public_parent_idx on public.feedback_replies (parent_thread_id, created_at asc);
create index if not exists feedback_replies_agent_parent_idx on public.feedback_replies (parent_agent_thread_id, created_at asc);
create index if not exists feedback_replies_role_time_idx on public.feedback_replies (author_role, created_at desc);

alter table public.feedback_replies enable row level security;

drop policy if exists "public read feedback replies" on public.feedback_replies;
create policy "public read feedback replies" on public.feedback_replies for select using (true);

drop policy if exists "public insert feedback replies" on public.feedback_replies;
create policy "public insert feedback replies" on public.feedback_replies
  for insert with check (author_role in ('public','authority','agent','system'));

grant select, insert on public.feedback_replies to anon, authenticated;
notify pgrst, 'reload schema';
