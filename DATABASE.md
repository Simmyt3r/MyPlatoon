# Database Design

PostgreSQL in production (Neon), SQLite fallback for local development/tests. All access
goes through SQLAlchemy ORM models in `app/models/`.

## Tables

### `users`
Authentication and role. One-to-one with `profiles`.

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| public_id | String(36) unique | UUID, not the primary key, for external reference |
| full_name | String(120) | |
| email | String(255) unique, indexed | |
| password_hash | String(255) | Werkzeug-hashed, never plaintext |
| role | String(20) | `admin` or `member` |
| is_active_account | Boolean | |
| is_suspended | Boolean | |
| created_at / updated_at / last_login_at | DateTime | |

### `profiles`
Personal, professional, business-adjacent, and privacy data. One-to-one with `users`.

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| slug | String(36) unique | Public-facing identifier (not the DB id) |
| user_id | FK -> users.id, unique | |
| nickname, gender, state_of_origin, lga, phone_number, whatsapp_number, current_location, address | | Personal info |
| profession, course_of_study, institution, graduation_year, certifications, biography | | Professional info |
| website, facebook, instagram, tiktok, twitter_x | | Social links |
| profile_visibility, phone_visibility, whatsapp_visibility, address_visibility | String(20) | `public`/`platoon`/`private` (address also has `general`) |
| status | String(20), indexed | `draft`/`pending`/`approved`/`rejected`/`suspended` |
| rejection_reason | Text | |
| reviewed_by_id | FK -> users.id | admin who last reviewed |
| reviewed_at | DateTime | |
| photo_url, photo_public_id | String | Cloudinary URL + asset id (for deletion) |

Indexes on `state_of_origin`, `lga`, `profession`, `status` support directory search/filtering.

### `skills` / `profile_skills`
Many-to-many. `skills.name` is unique; `profile_skills` is the join table.

### `businesses`
Belongs to a `profile` (one member can register multiple businesses).

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| profile_id | FK -> profiles.id | cascades on profile delete |
| category_id | FK -> business_categories.id | |
| name, description, logo_url, logo_public_id, address, phone, whatsapp, email, website, facebook, instagram, tiktok, twitter_x | | |
| is_active | Boolean | |
| created_at / updated_at | DateTime | |

### `business_categories`
Seeded with the 17 default categories from the spec (Technology, Fashion, Food, etc., Other).
Admin-manageable; cannot be deleted while businesses reference it.

### `album_versions`
One row per generated PDF album.

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| version_label | String(20) | e.g. `1.0`, `1.1` |
| pdf_data | LargeBinary | **Source of truth.** The actual PDF bytes, served directly for every download -- this never depends on Cloudinary being configured, reachable, or willing to deliver PDF/raw files (see SECURITY.md) |
| pdf_url, pdf_public_id | String | Best-effort *secondary* copy on Cloudinary (e.g. for sharing a link outside the app). May be empty if Cloudinary isn't configured or the upload fails -- downloads are unaffected either way |
| member_count | Integer | Snapshot count at generation time |
| generated_by_id | FK -> users.id | |
| status | String(20) | `draft`/`published`/`archived` |
| download_count | Integer | |
| generated_at | DateTime | |

### `announcements`
Simple admin-authored announcements shown on the landing page.

### `audit_logs`
Append-only record of security/administrative actions (login, approvals, rejections,
suspensions, deletions, category/announcement changes, album generation, data export).

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| user_id | FK -> users.id, nullable | null for pre-auth events (e.g. failed login) |
| action | String(80), indexed | dotted action name, e.g. `profile.approve` |
| target_type, target_id | String | what was acted on |
| detail | Text | free-form context, never secrets |
| ip_address | String(64) | |
| created_at | DateTime, indexed | |

### `notifications`
In-app notifications per user (profile approved/rejected, submission received, etc.).

### `dating_personas` / `dating_matches`
Entirely separate from `profiles` -- a user opts in explicitly (see SECURITY.md for why
this is kept isolated from the main directory/search/album). `dating_personas` holds the
persona itself (display name, gender, interested-in, bio, interests, status, report
flags). `dating_matches` stores one row per *pair* of personas ever ranked against each
other, holding each side's rank of the other and a computed compatibility score; a row
only becomes a notified "match" once both sides have ranked each other in their own top
N. See `app/services/dating_service.py` for the scoring and matching logic.

## Relationships Summary

```
User 1---1 Profile 1---N Business N---1 BusinessCategory
Profile N---N Skill (via profile_skills)
User 1---N Notification
User 1---N AuditLog (as actor)
User 1---N AlbumVersion (as generator)
User 1---N Announcement (as author)
```

## Schema Creation & Migrations

**Missing tables are created automatically at application startup** (see
`app/__init__.py::_ensure_database_schema`, controlled by the `AUTO_CREATE_TABLES` env
var, default on). This uses SQLAlchemy's `db.create_all()`, which only issues `CREATE
TABLE` for tables that don't already exist — it never alters an existing table's columns,
so it's safe to leave on permanently and won't conflict with Alembic-managed migrations.

For actual schema **changes** to existing tables (new/renamed columns, etc.), use
Flask-Migrate (Alembic) as usual:

```bash
flask db init        # once, creates migrations/
flask db migrate -m "message"
flask db upgrade
```

See `DEPLOYMENT.md` for the Neon-specific note on using the unpooled connection string
for migrations.

## Indexing Rationale

Search-heavy columns (`state_of_origin`, `lga`, `profession`, `status`, skill names,
business names/categories) are indexed to keep the directory responsive as membership
grows into the hundreds/thousands, per the performance requirements in the spec.
