# MyPlatoon Gig Safety: Release Candidate Checklist

**Baseline:** `7125fe8c` (CI hygiene) and the subsequent release-schema
validation addition. This checklist applies to the code on `main`, not a
promise that the production PostgreSQL schema has been upgraded.

## Verified by automated tests

- Gig owner registration and administrator approval
- Member application, explicit offer acceptance and fixed offer terms
- Dual-acknowledged delivery, out-of-platform payment-record boundaries
- Private work journal, corrections and mutual cancellation
- Confidential dispute types, evidence ownership and private downloads
- Moderator evidence review and written non-financial outcomes
- Explicit consent and independent moderation of public employer reviews
- SQL-level evidence row filtering, checksum validation and no-store headers

The regression suite runs on GitHub Actions using isolated test databases.
The migration gate uses a fresh SQLite database and **does not migrate the
real Aiven service**.

## Release gate (before exposing Phase 3)

1. Confirm GitHub Actions **MyPlatoon nationwide regression tests** is
   green on the exact release commit and records the test count.
2. Confirm **NERD feature tests** is green and Vercel reports a successful
   build for the same commit. A build is **not** proof of healthy live
   database operations.
3. Back up Aiven PostgreSQL and confirm the backup is restorable.
4. Verify production DB name and target connection in the Aiven Console.
   Do not print or commit database URLs or credentials.
5. Only during the agreed final database configuration, trigger the
   protected **Apply MyPlatoon production migrations** GitHub workflow.
   It must finish at Alembic revision `c4c0e21ac7b8`.
6. Run `python scripts/check_release_schema.py` with a read-only database
   account where possible. It checks revision, required tables, columns and
   security indexes; **it never applies migrations or stamps revisions**.
7. With dedicated pilot test accounts, manually verify the whole chain:
   register gig owner, admin approve, post reviewed gig, member apply,
   send/accept offer, write note, request completion, request correction,
   reopen work, confidential dispute, participant evidence upload,
   unauthorized account rejection, moderator evidence inspection and
   moderator resolution.
8. Validate an existing account cannot read another member's case or
   evidence, and suspended accounts cannot retrieve protected attachments.
9. Review an evidence download audit log and confirm uploaded text/data
   are absent from the public job board and public reputation profile.
10. Have a named incident owner and an operational process to remove
    dangerous evidence, preserve reported abuse and respond to privacy
    complaints before open pilot enrollment.

## Explicit blockers and limitations

- **Aiven production migration is deferred** at the user's request.
  Do not assume new routes function on an older production database.
- Admin-initiated `/setup` upgrades and integration settings require a strong
  production signing key, a dedicated Aiven URL, and an explicit restorable backup.
- Evidence files are database BLOBs limited to 1 MiB each and 4 MiB per
  case. These limits reduce storage risk but do not provide malware scanning.
- File signatures and checksums verify format hints and stored byte
  integrity, **not document authenticity or freedom from malware**.
- Evidence is private to its submitting party and moderators, not shared
  with the counterparty; this is a moderation workflow, not a legal court.
- Public employer ratings are moderated self-reports, not externally
  verified trust or payment guarantees.
- Production data retention, incident response, operator training and
  whether attachments must be scanned or held for manual review need
  approved operating policies before broad launch.

## Rollback and recovery

Stop exposing evidence submission routes during incidents; do not delete
financial or dispute records. Restore an earlier *application deployment*
if code fails, but retain the current database schema unless a reviewed
data-preserving rollback has been prepared. Running `flask db downgrade`
blindly can drop private evidence tables and permanently lose records.
Maintain access controls on backups. Treat attachment disclosures or
malicious uploads as security incidents with restricted moderator review.

## Current scope

No new payment integration, escrow, government verification or public
member ratings. No secrets, credentials or environment configuration
are included in this checklist or its associated implementation.
