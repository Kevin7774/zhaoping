# Lessons

## 2026-06-09: Do not assume PostgreSQL-only aggregate functions in route fixes

When optimizing SQLAlchemy routes in this project, verify the test database dialect before choosing database-specific functions. The API tests use SQLite in memory, so helpers must avoid PostgreSQL-only constructs such as `array_agg` unless there is an explicit PostgreSQL-only requirement and a matching test setup.

Rule: for route-level rollups that must pass the existing test suite, prefer portable grouped counts/averages plus Python-side status aggregation over dialect-specific aggregate arrays.
