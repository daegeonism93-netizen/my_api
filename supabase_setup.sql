-- Supabase 대시보드 > SQL Editor 에 붙여넣고 Run 하세요
create table if not exists public.todos (
  id bigint generated always as identity primary key,
  title text not null,
  done boolean not null default false,
  created_at timestamptz not null default now()
);

-- 백엔드는 secret key(RLS 우회)로 접근하므로, 브라우저(anon key)의 직접 접근은 막아 둡니다
alter table public.todos enable row level security;
