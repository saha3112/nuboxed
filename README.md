# Nuboxed

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/python/python-original.svg" width="140" alt="Python Logo" />
</p>

<p align="center">
  <img src="./media/logos/nuboxed-logo.webp" width="220" alt="Nuboxed Logo" />
</p>

<p align="center">
  Europe-focused multi-retailer ecommerce marketplace platform built with Django and Django REST Framework.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django 4.2" />
  <img src="https://img.shields.io/badge/MySQL-Database-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL" />
  <img src="https://img.shields.io/badge/Redis-Queue-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <a href="#jira-workflow"><img src="https://img.shields.io/badge/Jira-Project%20Planning-0052CC?style=for-the-badge&logo=jira&logoColor=white" alt="Jira project planning workflow" /></a>
</p>

## About

Nuboxed brings the storefront, retailer workspace, and marketplace back office into one Django application. Built for a Europe-focused multi-retailer marketplace, it connects product discovery with the operational workflows behind each order: inventory, checkout, fulfillment, and reporting.

**One marketplace. Multiple retailers. Connected commerce operations.**

## Highlights

- **Customer storefront:** browse stores and categories, compare sellers, explore products, and manage a persistent cart.
- **Retailer workspace:** manage store profiles, staff, product listings, variants, media, warehouses, and stock adjustments.
- **Central administration:** oversee retailers, catalog approvals, permissions, content, courier settings, and reports.
- **Order operations:** support checkout, saved addresses, orders split by retailer, stock reservations, and status timelines.
- **Delivery workflows:** estimate delivery by location and route website shipments through internal courier operations.
- **API foundation:** versioned REST endpoints, JWT authentication, role-based permissions, and OpenAPI documentation.

Feature coverage varies by module; see the [backend guide](backend/README.md) for documented routes and operational rules.

## Technology Stack

<table align="center">
  <tr>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/python/python-original.svg" width="52" alt="Python" /><br />
      <strong>Python</strong><br />
      <sub>Backend Language</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/django/django-plain.svg" width="52" alt="Django" /><br />
      <strong>Django</strong><br />
      <sub>Web Framework</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/mysql/mysql-original.svg" width="52" alt="MySQL" /><br />
      <strong>MySQL</strong><br />
      <sub>Relational Database</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/redis/redis-original.svg" width="52" alt="Redis" /><br />
      <strong>Redis</strong><br />
      <sub>Queue & Cache</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/docker/docker-original.svg" width="52" alt="Docker" /><br />
      <strong>Docker</strong><br />
      <sub>Container Platform</sub>
    </td>
  </tr>
</table>

## Core Stack

- Python 3.12
- Django 4.2 LTS
- Django REST Framework
- MySQL
- Redis and Celery
- Docker
- S3-compatible object storage

## Repository Structure

```text
Nuboxed/
├── backend/
│   ├── api/v1/          # Versioned REST API
│   ├── apps/            # Commerce modules and storefront
│   ├── config/          # Django settings and URL configuration
│   └── requirements/    # Python dependencies
├── docs/architecture/   # Architecture and delivery roadmap
├── deploy/             # AWS and cPanel deployment guides
├── docker/             # Container startup and Nginx configuration
├── docker-compose.yml  # Web, database, Redis, workers, and proxy
├── .env.example        # Environment configuration template
└── manage.py           # Root Django management entrypoint
```

## Local Setup

Use Python 3.12, MySQL, and Redis for the main development stack. Run these commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `.env` for your local environment. Create a MySQL database and configure credentials for a user with access to it:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.local
DEBUG=True
SECRET_KEY=replace-with-a-long-random-local-secret
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DB_NAME=nuboxed
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_HOST=127.0.0.1
DB_PORT=3306
REDIS_URL=redis://127.0.0.1:6379/0
```

Apply migrations, seed the default roles, and create an administrator:

```bash
python manage.py migrate
python manage.py seed_rbac
python manage.py createsuperuser
python manage.py runserver
```

The local settings execute Celery tasks eagerly. To run a separate worker for an environment configured to use the queue, run this from `backend/` with the virtual environment activated:

```bash
celery -A config worker -l info
```

### Useful URLs

| Area | Local URL |
| --- | --- |
| Storefront | <http://127.0.0.1:8000/> |
| Administration | <http://127.0.0.1:8000/admin/> |
| Retailer workspace | <http://127.0.0.1:8000/retailer/> |
| API health | <http://127.0.0.1:8000/api/v1/health/> |
| Interactive API docs | <http://127.0.0.1:8000/api/v1/docs/> |
| OpenAPI schema | <http://127.0.0.1:8000/api/v1/schema/> |

Workspace access depends on the account's assigned roles and permissions.

## Jira Workflow

A suggested Jira workflow for organizing Nuboxed development:

**Backlog → To Do → In Progress → In Review → Done**

Group related work into epics such as **Storefront**, **Retailer Operations**, **Catalog & Inventory**, **Orders & Fulfillment**, and **Platform & Deployment**. Give each issue a clear outcome, acceptance criteria, and verification steps.

Include your actual Jira issue key in branch names, commits, and pull requests so reviewers can follow the context. For example, if your project key is `NUB`:

```text
Branch: feature/NUB-123-retailer-stock-alerts
Commit: NUB-123 Add retailer low-stock notifications
PR:     [NUB-123] Add retailer low-stock notifications
```

`NUB-123` is an example. Replace it with an issue key from your team's Jira project. This section describes a proposed workflow; no Jira board or automatic integration is configured here.

## Documentation & Deployment

- [Backend guide and API routes](backend/README.md)
- [Architecture overview](docs/architecture/commerceos-foundation.md)
- [Implementation roadmap](docs/architecture/implementation-roadmap.md)
- [AWS deployment](deploy/aws/README.md)
- [cPanel deployment](deploy/cpanel/README.md)
- [Deployment guide](docs/Deployment_Guide.md)

## Contributing

Keep each change focused on a clear outcome. Describe the problem, the resulting behavior, and how you verified it in your pull request. Include the relevant Jira issue key when your team uses Jira, and update documentation when setup steps or public behavior change.

Use `.env.example` as a configuration template and keep real credentials out of commits and issue descriptions.
