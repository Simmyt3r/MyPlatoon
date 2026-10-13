# Gig owners: registration and reviewed publication

This is a dedicated, easier route through MyPlatoon's existing Jobs & Gigs
marketplace. The public entry point is **`/jobs/gig-owners`**.

## What gig owners can do

1. Visit `/jobs/gig-owners` and learn how the marketplace works.
2. Choose **Register as a gig owner** at `/jobs/gig-owners/register`.
   Individuals, schools, businesses, and NGOs can register, with one account
   and an owner name, operating location, recruiting contact and description.
   This is an **employer-only account**, not a fabricated NYSC platoon record.
3. A signed-in MyPlatoon member can instead use
   `/jobs/gig-owners/claim` to link their first gig-owner profile without
   losing their member identity.
4. After registration the owner is signed in (new accounts) or remains
   signed in (existing members), and taken directly to
   `/jobs/gigs/new`.
5. The owner enters work description, qualifications, work arrangement,
   location, schedule, estimated hours, **positive fixed NGN pay**,
   payment basis and application deadline. At least one of the different
   gig safety agreements must be explicitly checked.
6. On submission, the gig is stored as `job_kind=gig`, with matching
   `pay_min` and `pay_max`, and `status=pending`. There is no immediate
   public release. It appears privately to its owner in the
   `/jobs/gig-owners/dashboard` workspace.
7. Moderators first verify the gig owner under
   `/jobs/admin/employers`, then review the individual gig under
   `/jobs/admin/listings`. **Both approvals** are required for a
   listing to appear on `/jobs/`.
8. MyPlatoon members with approved profiles can apply when the posting
   is live, subject to any serving-only restriction. Owners can view
   applicants and update their status from their dashboard.
9. Owners can edit or close their own gigs. Editing an approved listing
   resets it to pending and triggers re-review.

## Routes

| Path | Access | Role |
| --- | --- | --- |
| `/jobs/gig-owners` | Public | Explain and start |
| `/jobs/gig-owners/register` | Anonymous | Create a dedicated account |
| `/jobs/gig-owners/claim` | Signed-in | Add a profile to an existing account |
| `/jobs/gigs/new` | Linked owner | Submit a paid gig |
| `/jobs/gig-owners/dashboard` | Linked owner | Track review, gig status, applicants |
| `/jobs/admin/employers` | Admin | Verify gig owner |
| `/jobs/admin/listings` | Admin | Approve or reject each opportunity |

## Safety and operational rules

- Registration and applications are free. There is no activation fee,
  candidate application fee or job payment gateway.
- Gig owners cannot publish their own unreviewed listings. Profile
  suspension or rejection blocks new gig submissions; revoked employer
  approval hides previously published listings.
- The signup agreement prohibits fabricated jobs, advance fees,
  banking PIN requests and misleading working conditions.
- Member application contact details remain visible only to the
  corresponding hiring account for that job.
- Work opportunities are **not NYSC-sanctioned deployments**. Applicants
  must follow their NYSC/PPA/CDS responsibilities and validate offers
  independently. A moderator's approval is not a guarantee of job safety.
- Organisations of type `individual` use the existing `kind` string
  column on `job_employers` and do not need a new database migration.
- The existing application, security, and moderation models are reused
  to avoid duplicate sources of truth.

## Testing and deployment

The tests in `tests/test_gig_owner.py` cover onboarding, agreement
validation, member-linked profiles, owner-only access, pay/deadline
validation and two-stage moderator publication. They run with the full
national test suite.

No new production variables or migration are needed specifically for
these routes. The **previously prepared Jobs & Gigs migrations** must
still be applied to the production Aiven database during final
configuration before launching these workflows. The standalone
marketing landing remains independent of database configuration, but
registration and posting necessarily require a functioning database.
