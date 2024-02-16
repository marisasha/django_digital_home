cd ..

python -m venv env
call env/scripts/activate
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

cmd