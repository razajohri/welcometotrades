# Launch checklist — Welcome to Trades

## Locked product decisions

| Item | Value |
|------|--------|
| Domain | welcometotrades.com |
| Geography | USA + Canada + city filters |
| Work type | On-site mining/trades |
| Monetization | Later — `/search` free now |
| TikTok | https://www.tiktok.com/@rigtimmins |

## Infra (new only)

1. Supabase project → run `db/schema.sql`
2. Railway project from this repo
3. Env from `.env.example` (`CANONICAL_HOST=www.welcometotrades.com`)
4. Namecheap DNS → Railway
5. `python scripts/update_jobs_cache.py`

## Smoke test

- [ ] `/` shows Welcome to Trades
- [ ] `/search` works without login
- [ ] Category + city filters work
- [ ] TikTok → @rigtimmins
- [ ] Mobile OK
