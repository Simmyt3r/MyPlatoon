# API / Endpoint Reference

This application is primarily server-rendered (Jinja2 + Bootstrap), not a JSON API.
This document lists the routes as an endpoint reference for anyone integrating or
extending the platform.

## Auth (`/auth`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET/POST | `/auth/register` | guest | Create account (rate-limited) |
| GET/POST | `/auth/login` | guest | Log in (rate-limited) |
| GET | `/auth/logout` | member | Log out |

## Profile (`/profile`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/profile/dashboard` | member | Own dashboard, completion %, status |
| GET/POST | `/profile/edit` | member | Edit own profile (multipart for photo) |
| GET/POST | `/profile/privacy` | member | Edit own privacy settings |
| POST | `/profile/submit` | member | Submit own profile for admin approval |
| GET | `/profile/me` | member | Redirects to own public profile |

## Business (`/business`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/business/mine` | member | List own business(es) |
| GET/POST | `/business/new` | member | Create a business |
| GET/POST | `/business/<id>/edit` | owner or admin | Edit a business |
| POST | `/business/<id>/delete` | owner or admin | Delete a business |

## Directory (`/directory`) — public, privacy-filtered
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/directory/members` | any | Search/filter/paginate approved members |
| GET | `/directory/member/<slug>` | any | Public profile (404 if not visible to viewer) |
| GET | `/directory/businesses` | any | Search/filter/paginate businesses |
| GET | `/directory/business/<id>` | any | Business detail |

## Admin (`/admin`) — admin only (403 otherwise)
| Method | Path | Description |
|---|---|---|
| GET | `/admin/` | Dashboard + stats |
| GET | `/admin/members` | Member list, filter by status/search |
| GET | `/admin/members/<profile_id>` | Review a single profile |
| POST | `/admin/members/<profile_id>/approve` | Approve |
| POST | `/admin/members/<profile_id>/reject` | Reject with reason |
| POST | `/admin/members/<profile_id>/suspend` | Suspend account |
| POST | `/admin/members/<profile_id>/reinstate` | Reinstate account |
| POST | `/admin/members/<profile_id>/delete` | Permanently delete account |
| GET/POST | `/admin/categories` | List/create business categories |
| POST | `/admin/categories/<id>/delete` | Delete an unused category |
| GET/POST | `/admin/announcements` | List/create announcements |
| POST | `/admin/announcements/<id>/toggle` | Show/hide an announcement |
| GET | `/admin/businesses` | All businesses, paginated |
| GET | `/admin/audit-logs` | Audit log, paginated |
| GET | `/admin/export/members.csv` | CSV export of all members |

## Album (`/album`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/album/` | member | Latest album + version history |
| POST | `/album/generate` | admin | Generate a new album version (PDF) |
| GET | `/album/download/<version_id>` | member | Download a specific version |

## Main (`/`)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | any | Landing page |
| GET | `/about` | any | About page |
| GET | `/notifications` | member | Own notifications |

## Error Responses
All unhandled errors render branded HTML pages (never raw JSON or stack traces):
`400`, `403`, `404`, `429` (rate limited), `500`.
