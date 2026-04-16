create table orders (
  id bigserial primary key,
  retailcrm_id text unique not null,
  external_id text,
  first_name text,
  last_name text,
  phone text,
  email text,
  total_sum numeric not null default 0,
  status text,
  order_type text,
  order_method text,
  city text,
  created_at timestamptz not null default now(),
  synced_at timestamptz default now(),
  raw_data jsonb
);

-- Индексы для дашборда
create index idx_orders_created_at on orders(created_at desc);
create index idx_orders_total_sum on orders(total_sum);

-- RLS: публичное чтение для дашборда, запись только через service key
alter table orders enable row level security;

create policy "public read" on orders
  for select using (true);