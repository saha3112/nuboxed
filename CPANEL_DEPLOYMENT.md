# cPanel deployment

Upload the complete project to a private application directory on the server,
for example `/home/CPANEL_USER/public_html/nuboxed`. The project root contains
the cPanel entrypoint and `manage.py`; do not enter the `backend/` directory
when configuring the cPanel application. Do not upload `.env` from the
development machine. Create it on the server from `.env.example`.

## 1. Create the Python application

In cPanel **Setup Python App**:

- Python version: 3.10 or newer
- Application root: `public_html/nuboxed`
- Application URL: the required domain/subdomain
- Startup file: `passenger_wsgi.py`
- Entry point: `application`

Make sure the subdomain DNS has an `A` record named `nuboxed` pointing to the
cPanel server IP. If the domain uses Cloudflare, proxying can remain enabled,
but the origin server must still be reachable and the SSL certificate must
cover `nuboxed.mindandmatter.in`.

Use the virtualenv path shown by cPanel for the commands below.

## 2. Install dependencies

```bash
source /home/CPANEL_USER/virtualenv/public_html/nuboxed/3.12/bin/activate
cd /home/CPANEL_USER/public_html/nuboxed
pip install -r requirements.txt
```

If `mysqlclient` cannot compile on the host, ask the hosting provider to
enable the MySQL/MariaDB development package for the Python app.

## 3. Configure the environment

```bash
cp .env.example .env
nano .env
```

Set a unique `SECRET_KEY`, the real domain in `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS`, and the MySQL database credentials created in cPanel
MySQL Databases. Keep `DEBUG=False`.

## 4. Database and static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

Create a writable `media/` directory. The repository includes a root
`.htaccess` that serves `/static/` from `staticfiles/` and `/media/` from
`media/` while Passenger handles Django requests. If the host disables
`.htaccess` rewrites, configure the equivalent Apache aliases instead.

For repeatable deployments, run:

```bash
bash deploy/cpanel/deploy.sh
```

## 5. Restart

Click **Restart** in cPanel Setup Python App after every deployment or change
to `.env`. The app entrypoint is already provided in `passenger_wsgi.py`.

Never commit or publicly upload `.env`, database dumps, virtualenv folders,
`__pycache__`, or development logs.
