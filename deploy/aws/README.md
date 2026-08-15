# AWS deployment

This project is a Django application rendered with server-side templates. It
does not need a separate frontend build step. The Docker image installs the
Python dependencies, runs migrations, collects static files, and starts
Gunicorn.

## Recommended AWS layout

- EC2 (Ubuntu 22.04 or 24.04) for Docker, Gunicorn, and Nginx
- RDS MySQL 8 for the database
- ElastiCache Redis for Celery and background jobs
- S3 for media files when running more than one web instance
- Route 53 + an ACM certificate or an Nginx/Certbot certificate for HTTPS

Keep RDS and Redis private. Only ports 22 (restricted to the operator), 80,
and 443 should be exposed publicly.

## One-server Docker deployment

1. Install Docker and the Compose plugin on the EC2 instance.
2. Copy the repository to the server, for example `/opt/nuboxed`.
3. Create `backend/.env` from the root `.env.example` and set at least:

```env
DJANGO_SETTINGS_MODULE=config.settings.production
DEBUG=False
SECRET_KEY=<long-random-secret>
ALLOWED_HOSTS=example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com

DB_NAME=nuboxed
DB_USER=<rds-user>
DB_PASSWORD=<rds-password>
DB_HOST=<rds-endpoint>
DB_PORT=3306

REDIS_URL=redis://<elasticache-endpoint>:6379/0
USE_S3=True
AWS_ACCESS_KEY_ID=<least-privilege-iam-key>
AWS_SECRET_ACCESS_KEY=<secret>
AWS_STORAGE_BUCKET_NAME=<bucket>
AWS_S3_REGION_NAME=<region>
```

4. Set the production hostname in `docker/nginx/default.conf`, configure TLS,
   then build and start the stack:

```bash
docker compose up --build -d
```

The web container automatically runs `migrate` and `collectstatic` before
Gunicorn. Celery worker and beat are started by Compose as well.

5. Create the first administrator:

```bash
docker compose exec web python manage.py createsuperuser
```

6. Verify the deployment:

```bash
docker compose ps
docker compose logs --tail=100 web
curl -f https://example.com/api/v1/health/
```

## Release checklist

- Take a database backup before each release.
- Confirm `DEBUG=False` and never commit `.env` or AWS keys.
- Confirm RDS security-group access from the EC2 security group.
- Confirm S3 bucket CORS/permissions and media persistence.
- Run `docker compose up --build -d` after pulling new code.
- Check `docker compose logs web celery_worker celery_beat` after deployment.
- Configure nightly RDS backups and application/media backups.

For a single EC2 server using the included MySQL and Redis containers, the
existing `docker-compose.yml` can be used as-is for a first deployment. For a
production setup, use RDS and ElastiCache instead of exposing the bundled
database and Redis services publicly.
