# MyPlatoon gig reputation, public employer history

**Route:** `/jobs/employers/<id>/reputation` (public, approved employers only)

The jobs board and listing details expose a reputation link. Employer accounts
can see their own profile from the hiring dashboard. Contact addresses,
email addresses, and member identities are not exposed.

**Trusted signals:** Platform-confirmed completion uses two distinct
participants: worker requests completion, employer confirms delivery.
Only completed deals with active, approved member workers and a reviewed
active employer contribute. Worker acknowledgments of payment are described
as voluntary reports, not bank verification.

**Review visibility:** Existing private star ratings remain private after
database upgrade. A new rating is private unless the worker checks a separate
explicit consent checkbox. Previous reviews can be opted in later via
`/jobs/deals/<id>/review/publish`. This sends them to moderation, it does
not immediately publish. Workers can withdraw permission at any time using
`/jobs/deals/<id>/review/withdraw`. Employers' ratings of workers do not
become public in this phase. No reviewer names or individual profiles appear
on the public profile.

**Moderation:** The admin queue `/jobs/deals/admin/reviews` supports
pending, approved and rejected feedback and revocation after approval.
Approvals require worker consent, genuine completed work, an approved active
employer and active approved worker. A disputed or cancelled deal is excluded
from public reputation, even when an older rating was once approved. Reviews
are not displayed until the employer meets the minimum sample threshold.

**Reputation scoring:** At least THREE distinct completed-gig workers and
TWO separate approved worker ratings are required before a score appears.
One rating per unique worker is counted, even across repeat gigs. A Bayesian
prior of five 3.5-star reference ratings stabilizes the displayed score.
No score or decorative five-star badge is manufactured for new employers.
Employer status is **platform reviewed**, not externally government verified.

**Safety:** Do not use reputation to judge workers' private characteristics.
Keep complaints and dispute reporter identities confidential. Never treat
MyPlatoon as an escrow, verified payroll, regulatory approval or NYSC
placement service. The score is only one input to due diligence.

**DB:** `g93d0f6e2a41` adds only columns to `gig_reviews` and its
moderation-status index. No historic rating becomes public by migration.
Back up and run production migration only during the planned final Aiven
setup. No live production schema was changed as part of this implementation.
