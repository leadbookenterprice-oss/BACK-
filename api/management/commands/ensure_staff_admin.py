import os

from django.core.management.base import BaseCommand, CommandError

from api.models import Agent


DEFAULT_ADMIN_EMAIL = "admin@leadbook.com.ar"
DEFAULT_ADMIN_PASSWORD = "LeadBookAdmin2026!"


class Command(BaseCommand):
    help = "Creates or promotes a staff admin account for the admin dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=os.getenv("ADMIN_BOOTSTRAP_EMAIL", DEFAULT_ADMIN_EMAIL))
        parser.add_argument("--password", default=os.getenv("ADMIN_BOOTSTRAP_PASSWORD", DEFAULT_ADMIN_PASSWORD))
        parser.add_argument("--name", default=os.getenv("ADMIN_BOOTSTRAP_NAME", "LeadBook Admin"))

    def handle(self, *args, **options):
        email = str(options["email"] or "").strip().lower()
        password = str(options["password"] or "")
        name = str(options["name"] or "").strip() or "LeadBook Admin"

        if not email:
            raise CommandError("Admin email is required.")
        if not password:
            raise CommandError("Admin password is required.")

        user = Agent.objects.all_including_deleted().filter(email__iexact=email).first()
        created = False
        if not user:
            user = Agent(email=email, nombre=name, agencia="LeadBook")
            created = True

        user.email = email
        user.nombre = user.nombre or name
        user.agencia = user.agencia or "LeadBook"
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.eliminado_en = None
        user.plan_nombre = user.plan_nombre or "business"
        user.plan_activo = True
        user.set_password(password)
        user.save()

        action = "created" if created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Admin {action}: {user.email} | staff={user.is_staff} | superuser={user.is_superuser}"
            )
        )
