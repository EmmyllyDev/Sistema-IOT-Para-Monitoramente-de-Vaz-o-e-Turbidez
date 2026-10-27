release: python manage.py migrate --noinput
web: gunicorn setup.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 60
