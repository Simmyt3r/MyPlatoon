# Gig Safety and Dispute Resolution: Phase 3

This phase enhances the existing gig agreement workflow, not a new parallel
complaints platform. It keeps **claims, supporting materials and personal
identifiers confidential**.

## Member workflow

1. In an accepted, active/completion-pending/completed gig, use
   **Submit confidential dispute**, select the appropriate category and
   describe the problem in 20–1,500 characters.
2. The gig moves to `disputed`, pausing completion, further payment
   acknowledgements and public reputation use. Existing pending mutual
   cancellation proposals are superseded. Both participants receive
   notices, but the report's narrative remains private to its filer
   and moderators.
3. Open **Private case** at `/jobs/deals/case/<id>`.
4. Either participant can submit their own private evidence: a
   20–1,800-character statement, optionally paired with a small
   PDF, PNG, JPEG or UTF-8 text attachment. The counterparty cannot
   view the other participant's attachment or statement.
5. Evidence entries are **append-only**, with submission timestamps.
   A SHA-256 checksum for an attached file detects byte changes but
   does **not** verify whether the uploaded material is true.
6. The moderator reviews the case, the existing job agreement,
   relevant work updates and separate participant evidence, then
   records one outcome and an explanation shared with both:
   **resume work** or **close the gig**. No action can fabricate
   completed work or payment.
7. Participants can revisit the case timeline and their own evidence
   after a decision. Evidence submission closes once the moderator
   resolves the case.

## Confidentiality and storage

- Evidence is stored in the application database using binary fields.
  The files are **not** uploaded to public Cloudinary URLs.
- The evidence list is filtered in SQL so non-admins do not load the
  other participant's evidence records. Case lists defer binary blobs.
- Only the uploader and an administrator can download an attachment.
  The case route is visible only to its participants and administrators.
  Headers force downloads instead of inline browser rendering and
  disable caching. Case pages and moderator queues use no-store headers
  and request that search engines not index their contents.
- Maximum **1 MiB per file**, **4 MiB total binary payload per case**,
  and **8 evidence records per case**.
- File types are restricted by extension and checked against PDF,
  PNG and JPEG signatures or valid UTF-8 text. SVG, scripts, ZIP and
  Office documents are rejected.
- A matching SHA-256 checksum and file length are rechecked before
  download; mismatches fail closed. Downloads use generic binary MIME
  and forced attachment disposition, rather than inline document previews.
  Evidence downloads are logged without copying the contents into audits.
- A safe file signature is not a malware scan. Platform admins should
  handle downloads cautiously; a dedicated private object store and
  antivirus scanner are prerequisites before allowing larger files.
- Uploaded evidence is not shown to the public, applicant pool, or
  public employer reputation pages.
- Avoid NIN documents, raw bank statements, credentials, private
  addresses or third-party identities not essential for the case.

## Administration and audit

Admins can access cases from `/jobs/deals/admin/disputes`,
review evidence, and record an outcome. The timeline includes
case creation, evidence submissions and resolution. Security-sensitive
case actions are also recorded using the existing audit log.
Moderators cannot submit evidence as another participant.

This is not a legal adjudication, verified payroll, government/NYSC
decision or payout guarantee. Outstanding debts and safety issues can
require independent remedies, regulatory reporting or emergency services.

## Deployment

Migration `b73d61c28a50` follows `a14b82a0d7e6`, adding the
`gig_dispute_evidence` and `gig_dispute_events` tables and two
metadata columns to the existing `gig_disputes` table.
Existing disputes are retained with category `other`.

Run regression tests and a fresh Alembic upgrade before the
production migration. **Production Aiven migration remains deferred**
until the agreed final configuration phase. Back up the database and
configure a stricter retention policy before going beyond pilot scale.
