from api.models import Agent

def create_admin(email, password, nombre, agencia):
    if not Agent.objects.filter(email=email).exists():
        Agent.objects.create_superuser(email, password, nombre=nombre, agencia=agencia)
        print(f'Usuario {email} creado')
    else:
        print(f'Usuario {email} ya existe')

create_admin('Charlyadmin@gmail.com', 'Elcharlesx143', 'Charles', 'SUBZERO-02')
create_admin('Atilioadmin@gmail.com', 'Atiliusx4321', 'Atilio', 'SUBZERO-02')
