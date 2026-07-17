# CommerceOS Deployment Guide

This document outlines the production-ready deployment setup for CommerceOS using Docker, Django, MySQL, Redis, Celery, Gunicorn, and Nginx.

## 1. Server Setup Guide
1. **Provision a Linux Server** (Ubuntu 22.04 LTS recommended) with at least 4GB RAM and 2 vCPUs.
2. **Install Docker & Docker Compose**:
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo apt install docker-compose-plugin
   ```
3. **Clone Repository**:
   ```bash
   git clone <your-repo-url> /opt/commerceos
   cd /opt/commerceos
   ```

## 2. Environment Variables (.env)
Copy the `.env.example` to `backend/.env` and update the keys:
```env
SECRET_KEY=generate_a_very_secure_secret_key_here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_NAME=nuboxed
DB_USER=root
DB_PASSWORD=Chandan.1
DB_HOST=db
DB_PORT=3306
REDIS_URL=redis://redis:6379/0
```

## 3. Deployment & Database Migration
1. **Build and start the containers in detached mode**:
   ```bash
   docker compose up --build -d
   ```
2. **Run Database Migrations**:
   ```bash
   docker compose exec web python manage.py migrate
   ```
3. **Collect Static Files**:
   ```bash
   docker compose exec web python manage.py collectstatic --noinput
   ```
4. **Create Superuser**:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

## 4. Celery Worker & Cron/Scheduler Guide
Celery is configured in `docker-compose.yml` to start automatically alongside the web server.
- **Worker**: Handles background tasks (emails, integrations).
- **Beat**: Triggers recurring crons (sync jobs, notifications).

To view logs for background workers:
```bash
docker compose logs -f celery_worker
docker compose logs -f celery_beat
```

## 5. Backups
A backup command was implemented natively. You can trigger it directly via Docker:
```bash
docker compose exec web python manage.py backup_database
```
**Cron Job Setup** (Run nightly at 2 AM):
```bash
0 2 * * * cd /opt/commerceos && docker compose exec -T web python manage.py backup_database >> /var/log/commerceos_backup.log 2>&1
```

## 6. SSL Configuration
In `docker/nginx/default.conf`, uncomment the SSL block lines and map your Let's Encrypt certificates via a docker volume in `docker-compose.yml`. Certbot can be run on the host machine to handle certificate renewals.

## 7. Production Checklist & Monitoring
- [ ] **DEBUG=False**: Ensure `.env` has DEBUG explicitly disabled.
- [ ] **Change MySQL Password**: Update `MYSQL_ROOT_PASSWORD` and `DB_PASSWORD` in `.env`.
- [ ] **SSL Enabled**: Nginx configured to force HTTPS traffic.
- [ ] **Monitoring**: Monitor `django-error.log` inside the `web` container.
- [ ] **Data Export / GDPR**: Verify `/media/` mounts correctly persist for file-based data exports.
- [ ] **Firewall**: Ensure UFW is active, only exposing ports `80` (HTTP), `443` (HTTPS), and `22` (SSH).
