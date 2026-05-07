release: python manage.py migrate --noinput || true
web: python manage.py migrate --noinput && daphne -b 0.0.0.0 -p $PORT --http-timeout 300 --ping-timeout 300 subzero_core.asgi:application
worker: celery -A subzero_core worker --loglevel=info --concurrency=1
