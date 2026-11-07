# MyPlatoon: Production Readiness, Product Audit and Revenue Plan
Reviewed: 2026-11-07
Repository: Simmyt3r/MyPlatoon (main)

## Scope and evidence
This is a source-level review, **not** a successful production smoke test. Reviewed the Flask app factory, configuration, digital-games service/routes/model/tests, school recruiting tests, learning-certificate generator, README, and deployment instructions. Tests have not been executed in this review; live Aiven/Vercel settings and real traffic have not been independently verified.

## Existing features (avoid duplicating them)
- Ten digital interplatoon activities have an append-only activity table and a member/day/round uniqueness constraint. Their service excludes ineligible profiles and competitions outside the specified date windows.
- Games have quiz/verification/tap tasks, a standings page, a cohort-specific leaderboard and positive-tie ranking. Prior leader-entered result routes return HTTP 410.
- Elections use two-week leadership terms, one member ballot per term, and same-platoon eligibility.
- Academy has admin course management, embedded YouTube lessons, watch-time tracking and PDF certificates.
- Employer/school recruitment has scoped applications management tests, including negative cross-school access checks.
- Account creation and profile-upload behaviour have test files, but must be tested in the live deployment.
- Existing gig deals do **not** process money: their payment-acknowledgment records are user attestations, not escrow or bank verification.

## Findings, ordered by operational risk

### P0 — production gates before a public launch
1. **Shared rate limiting is optional in production.** `app/config.py` defaults `RATELIMIT_STORAGE_URI` to `memory://`; `REQUIRE_SHARED_RATELIMIT` defaults false. `app/__init__.py` only warns when Redis is absent. Per-process counters on Vercel cannot guarantee a global throttle. Provision shared Redis, set `RATELIMIT_STORAGE_URI=rediss://...` and `REQUIRE_SHARED_RATELIMIT=true`, then deploy and confirm the app boots and rate limits across concurrent requests. Do not place credentials in the repo.
2. **Schema readiness must be verified.** Production defaults `AUTO_CREATE_TABLES=false`; that is correct, but missing migrations break live workflows. Back up Aiven, run reviewed forward migrations via the supported /setup or production workflow, and verify the Alembic revision and all core tables (including platoon_game_activities) before inviting users.
3. **Live functionality remains unverified.** Run a real registration → login → profile/photo → course → certificate → game → school applications → logout smoke test on Vercel with separate ordinary, school and admin accounts. Verify CSRF and setup behavior with actual HTTPS cookies and domain.
4. **Secrets and environment.** Confirm `SECRET_KEY` is stable and unique (32+ chars), `FLASK_ENV=production`, the Aiven database is the intended `myplatoon` database with TLS, `AUTO_CREATE_TABLES=false`, and Cloudinary credentials are configured. Restrict setup/bootstrap access, remove one-time setup credentials when no longer needed, and avoid logging secret values.

### P1 — gameplay fairness and integrity
5. **Population bias.** Digital standings rank by raw participation totals. A platoon with substantially more eligible members can dominate. Choose an explicit scoring policy: qualified unique participants / eligible verified members with a minimum headcount and anti-abuse controls. Keep absolute counts visible for transparency. Any change needs versioned rules and regression tests rather than an unannounced mid-season edit.
6. **Quiz answer predictability.** The small fixed question bank and deterministic date rotations make quizzes repeatable and guessable. Expand question banks, randomize per-member questions server-side, and do not issue points twice. A correctness check alone is not proctoring.
7. **Activity quality.** Daily login, GOAL taps and cheers are easy engagement tasks but have weak educational value and can be gamed using extra accounts. Weight meaningful learning and verified work more strongly, create abuse flags, and use account eligibility checks; avoid defining the whole product around button tapping.
8. **Operational exception behavior.** If the games migration is missing, automatic scoring fails closed and returns false while logging a warning. This preserves login but hides missing scoring from affected members. Add a health alert for this condition and resolve migration before launch.
9. **Leaderboard privacy.** Maintain cohort isolation. Ensure no private profiles, phone numbers or sensitive onboarding documents appear in any public result, certificate verifier or competition export.

### P1 — product usability and role separation
10. School accounts should land directly in their recruitment workspace with relevant actions: create vacancy, review applications, shortlist, message, update status, and reports. Hide unrelated community navigation from school-role UI, but **enforce resource authorization on the server**, not only via menus.
11. Give members a simplified path: onboarding → assigned platoon → feed/games → learning → jobs. A PCM should not be forced to invent a camp assignment; keep clear waiting-state messaging.
12. Give admins a central operations panel covering onboarding funnel, appeals, fraud reports, course approvals, activity moderation, employer approvals, jobs, support cases, and finance reporting; every operational mutation should be auditable.
13. Measure API p95 latency, database errors, upload failures, academy completion errors, failed migrations, game ledger failures and registration conversion, with privacy-preserving logging.

### P2 — documentation and maintainability
14. `DEPLOYMENT.md` includes stale migration revision references, leftover Neon instructions and a contradictory startup/auto-create explanation. Make `SETUP.md` the current canonical runbook, update migration references from the actual head, and clarify that production does not silently alter schemas.
15. Keep `README.md` aligned with live feature availability; distinguish source-complete, tested, staged, and production-verified capabilities.
16. Academy certificate issuer had a typographic discrepancy (`SILAB` versus `SILABS`). Corrected in `app/services/learning_certificate.py` on 2026-11-07; generated files still need a test/download review.

## Revenue model: monetize institutions and clear value, not basic NYSC access
**Business principle:** MyPlatoon is an independent community platform, not an official NYSC portal. Never charge users for government placement, NYSC registration, officially guaranteed posting or access to their own basic account.

Suggested **hypotheses to validate** (not existing pricing or guaranteed forecasts):
| Product | Proposed pilot price | Who pays | Preconditions |
| --- | --- | --- | --- |
| School/employer Starter hiring workspace | Free, limited listings | Employer | Clear trust labeling and privacy controls |
| School/employer Pro hiring workspace | ₦5,000–₦15,000 per month | Employer | Proven applicant flow, shortlist/export, responsive support |
| Featured employer listing | ₦2,000–₦5,000 per 14 days | Approved employer | Marked sponsored, reviewed for scams, never override relevance/safety |
| Academy certification for optional advanced training | ₦1,000–₦3,000 per course | Learner or sponsor | High-value curriculum, disclosed issuer and assessment quality; keep foundational courses free |
| Institution cohort analytics | Custom organizational quote | Partner school/employer | Aggregated consent-respecting reporting; no sale of member contact lists |

**Illustrative gross monthly scenario, not a forecast:**
- 10 paying employer workspaces × ₦7,500 = ₦75,000.
- 20 sponsored listings × ₦2,500 = ₦50,000.
- 40 optional course purchases × ₦1,500 = ₦60,000.
- **Total hypothetical gross: ₦185,000/month**, before gateway fees, SMS/email, Redis, Aiven, Cloudinary, customer support, marketing, taxation, refunds and implementation overhead. Do not represent this as real revenue without production payment records.

### Important commercial controls
- No paid functionality should be described as launched until payment collection, webhook signature verification, ledger idempotency, refunds, receipts, and admin reconciliation are built and tested.
- Never imply a certificate is an accredited professional credential or NYSC certification; describe exactly what completion and assessments verify.
- Do not take a fee on off-platform gig payments without an enforceable, transparent mechanism and legal/product review. Employer subscriptions are easier to measure and reconcile as a first pilot.
- Separate revenue by source (subscriptions, listings, academy, partnerships), gross/refunds/net, and store only real settled receipts as revenue; do not count unfunded deals or self-reported payments.

## Implementation queue (sequential)
1. **Stabilize:** production environment gates, Redis-backed limits, current Alembic schema, smoke tests and error visibility.
2. **Make roles deliberate:** school-only navigation with server-enforced tenancy and admin insight/appeal routes.
3. **Make games defensible:** cohort-size normalized scoring policy, bot/duplicate-account detection, richer quizzes, transparent scoring rules and automated tests.
4. **Make learning credible:** real playback minimum enforcement, assessment quality, stable issuer/certificate verification, admin curriculum quality checks.
5. **Pilot revenue carefully:** one paid employer workspace tier with sandbox checkout/ledger/refunds, then real pilot interviews; defer advertising/academy charging until demand is demonstrated.

## Success criteria for launch
- All applicable CI tests pass, migrations show the intended head, and production smoke tests pass on actual user roles.
- 0 known cross-tenant application leaks; CSRF and permissions work on state-changing endpoints.
- Redis backed rate limiting confirmed across multiple instances.
- Certificate issuer and verification match public product claims; no premature promises of skills accreditation.
- Admin reports distinguish settlements from off-platform claims; no imaginary income.
- Games ledger can track points correctly without accepting duplicate member/day contributions.
