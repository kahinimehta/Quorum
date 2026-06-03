# Person 2 API Endpoints

This backend API connects the frontend dashboard to the shared Supabase/Postgres database.

## Safety

The API is SELECT-only by default. It does not call `cli.py build`, does not truncate tables, and does not modify the shared Supabase database.

## Environment

The backend reads the database connection from:

```text
SUPABASE_DATABASE_URL