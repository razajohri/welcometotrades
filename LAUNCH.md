# Launch checklist — Welcome to Trades

## Locked product decisions

| Item | Value |
|------|--------|
| Domain | welcometotrades.com |
| Geography | USA + Canada + city filters |
| Work type | On-site mining/trades |
| Monetization | Stripe Pro — from $5.99/week |
| TikTok | https://www.tiktok.com/@rigtimmins |

## Infra (new only)

1. Supabase project → run `db/schema.sql`
2. Railway project from this repo
3. Env from `.env.example` (`CANONICAL_HOST=www.welcometotrades.com`, `TEST_MODE=false`, Stripe + auth redirect)
4. Namecheap DNS → Railway
5. Stripe webhook → `https://www.welcometotrades.com/webhook`
6. `python scripts/update_jobs_cache.py`

## Smoke test

- [ ] `/` shows Welcome to Trades + paid CTA
- [ ] Anonymous `/search` redirects to login
- [ ] Login → unpaid user redirected to `/subscribe`
- [ ] Checkout + webhook grants `/search`
- [ ] Category + city filters work
- [ ] TikTok → @rigtimmins
- [ ] Mobile OK
