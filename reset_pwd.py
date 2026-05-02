from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.get(email='charlysanmartin20@gmail.com')
u.set_password('test123')
u.save()
print('OK')
