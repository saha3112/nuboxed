# Nuboxed

Nuboxed is a Europe-focused multi-retailer ecommerce marketplace platform built with Django and Django REST Framework.

This repository currently contains:

- architecture and delivery planning
- Django backend base project
- phased app/module structure
- environment configuration templates

The implementation is intentionally phased. Core platform foundations come first; marketplace modules are added incrementally.

## Target stack

- Backend: Python 3.12, Django 4.2 LTS, Django REST Framework
- Database: MySQL
- Queue: Redis, Celery
- Storage: S3-compatible object storage
- Frontend: Responsive web frontend
- Mobile readiness: API-first design for future Flutter apps

## Database connection target

- Database: `nuboxed`
- User: `root`
- Password: `Chandan.1`

## Repository structure

- `docs/architecture/` system planning and phased roadmap
- `backend/` Django project, apps, and API base
- `requirements.txt` top-level install passthrough

## Backend quick start

See [backend/README.md](/usr/local/var/www/Nuboxed/backend/README.md:1) for setup, JWT endpoints, Celery, and environment settings.

## Next step

Phase 1 is the platform foundation: environment setup, project bootstrap, authentication, RBAC, catalog primitives, tenant boundaries, and API standards.
# nuboxed
