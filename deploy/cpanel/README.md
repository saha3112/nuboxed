# Nuboxed on cPanel

The repository root is the cPanel application root. Do not configure cPanel
to use the `backend/` directory.

## cPanel Python App

Use these values in **Setup Python App**:

- Application root: `public_html/nuboxed`
- Startup file: `passenger_wsgi.py`
- Entry point: `application`
- Python: 3.10 or newer

Upload these directories/files together:

```text
manage.py
passenger_wsgi.py
backend/
staticfiles/
media/
requirements.txt
.htaccess
```

Create `.env` in the application root from `.env.example`. Set the cPanel
MySQL database name, user, password, host, allowed host, and CSRF origin.

## First deployment

Activate the virtualenv shown by cPanel, then run from the application root:

```bash
pip install -r requirements.txt
bash deploy/cpanel/deploy.sh
```

Create an admin account if needed:

```bash
python manage.py createsuperuser
```

Finally click **Restart** in cPanel. The included `.htaccess` serves
`/static/` and `/media/` directly and sends application requests to Passenger.
