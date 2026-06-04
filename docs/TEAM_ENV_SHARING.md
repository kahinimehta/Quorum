---
layout: default
title: Team env sharing
parent: Developer reference
nav_order: 10
---

# Sharing credentials with the team

**Never commit** `.env`, `personal/team-keys-for-sharing.txt`, or database passwords to GitHub.

## Your local checklist

1. Fill [`../.env`](../.env) (copy from [`.env.example`](../.env.example)).
2. Regenerate the share file:
   ```bash
   python3 scripts/export_team_keys.py
   ```
3. Open **`personal/team-keys-for-sharing.txt`** (gitignored) and copy the right section to each teammate.

## Who gets which keys

| Teammate | Share |
|----------|--------|
| **Everyone** (agents + backend) | `SUPABASE_DATABASE_URL` |
| **Person 2** (API) | `SUPABASE_DATABASE_URL` only |
| **Person 4** (agents 2–6) | `SUPABASE_DATABASE_URL` |
| **Person 5** (Next.js UI) | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` |
| **You** (literature pull) | Keep `NEBIUS_*` yourself or share if others run `cli.py pull` |
| **Optional** (server routes) | `SUPABASE_SERVICE_ROLE_KEY` from Supabase → Settings → API |

## Where to find missing keys

| Variable | Location |
|----------|----------|
| `SUPABASE_DATABASE_URL` | Supabase → Project Settings → Database → Connection string → URI |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://YOUR_REF.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase → Settings → API → publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Settings → API → `service_role` (secret) |
| `NEBIUS_*` | Nebius AI Studio dashboard |

## After sharing

Tell teammates:

```bash
cd neurodiscover   # or Quorum/neurodiscover
cp .env.example .env
# paste keys you sent
pip install -r requirements.txt
python3 cli.py validate
python3 cli.py show
```

See also [`SUPABASE.md`](SUPABASE.md) and [`PERSON2_BACKEND.md`](PERSON2_BACKEND.md).
