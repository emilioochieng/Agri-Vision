Farm registration, crop management, harvest records, and expense/income
tracking, with JWT auth. Built and tested with Flask + SQLite for local
development; `schema.sql` is the PostgreSQL schema for when you deploy.

## Run it locally

```bash
pip install flask pyjwt
python app.py
```

Serves on `http://localhost:5000`. First run creates `agrovision.db`
(SQLite) automatically from the schema in `database.py`.

## Try it

```bash
# Register
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Jane Wanjiru","email":"jane@example.com","password":"secret123"}'

# Use the returned token for everything else
curl http://localhost:5000/api/farms -H "Authorization: Bearer <token>"
```

See the route list at the top of `app.py` for the full API surface:
auth, farms, crops, harvests, and expense/income records — all scoped
so a farmer only sees their own farms, while `agronomist`/`admin`
accounts can see everything.

## Connecting the front end

In `agrovision.html`, point the login/register/dashboard forms at
`http://localhost:5000/api/...` and store the returned token
(e.g. in a JS variable held in app state — **not** localStorage, since
that's disabled in the Claude artifact sandbox). I can wire this up
directly next if you'd like.

## Moving to production Postgres (Aiven)

The data model in `database.py` mirrors `schema.sql` table-for-table.
To switch:

1. Create the tables on your Aiven Postgres instance:
   ```bash
   psql "$AIVEN_DATABASE_URL" -f schema.sql
   ```
2. Replace the `sqlite3` calls in `database.py` with `psycopg2`
   (`pip install psycopg2-binary`), reading the connection string from
   an environment variable (`DATABASE_URL`) rather than hardcoding it.
3. `?` placeholders become `%s` in psycopg2; `lastrowid` becomes
   `RETURNING id` in your `INSERT` statements. Everything else in
   `app.py` — routes, auth, ownership checks — stays the same.
4. Move `SECRET_KEY` in `app.py` into an environment variable before
   deploying (to Render or Railway, per your stack).

## Not in this phase yet

Worker management and field-image uploads (listed under Farm
Management in the original brief) — natural additions once Phase 3's
dashboard is wired to real data.
