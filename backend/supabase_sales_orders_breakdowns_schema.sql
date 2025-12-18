-- Supabase cache for monthly sales orders breakdowns (filterable)
create table if not exists public.monthly_sales_orders_breakdowns (
  id bigserial primary key,
  year integer not null,
  month smallint not null check (month between 1 and 12),
  market text not null default 'Unknown',
  agreement_type text not null default 'Unknown',
  account_type text not null default 'non-key',
  amount_aed numeric(18,2) not null default 0,
  order_count integer not null default 0,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint monthly_sales_orders_breakdowns_uq unique (year, month, market, agreement_type, account_type)
);

create index if not exists idx_monthly_sales_orders_breakdowns_year_month
  on public.monthly_sales_orders_breakdowns (year, month);

create index if not exists idx_monthly_sales_orders_breakdowns_dims
  on public.monthly_sales_orders_breakdowns (
    year,
    month,
    lower(market),
    lower(agreement_type),
    lower(account_type)
  );
