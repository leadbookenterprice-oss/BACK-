import os

from django.core.management.base import BaseCommand, CommandError

from api.models import Agent


DEFAULT_ADMIN_NAME = "LeadBook Admin"


def _env_truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


class Command(BaseCommand):
    help = "Opt-in helper to create/promote a staff account. Not used by the admin dashboard session login."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=os.getenv("ADMIN_BOOTSTRAP_EMAIL", ""))
        parser.add_argument("--password", default=os.getenv("ADMIN_BOOTSTRAP_PASSWORD", ""))
        parser.add_argument("--name", default=os.getenv("ADMIN_BOOTSTRAP_NAME", DEFAULT_ADMIN_NAME))

    def handle(self, *args, **options):
        if not _env_truthy(os.getenv('ALLOW_STAFF_ADMIN_BOOTSTRAP')):
            raise CommandError("Staff admin bootstrap is disabled. Set ALLOW_STAFF_ADMIN_BOOTSTRAP=True to run it explicitly.")

        email = str(options["email"] or "").strip().lower()
        password = str(options["password"] or "")
        name = str(options["name"] or "").strip() or DEFAULT_ADMIN_NAME

        if not email:
            raise CommandError("ADMIN_BOOTSTRAP_EMAIL or --email is required.")
        if not password:
            raise CommandError("ADMIN_BOOTSTRAP_PASSWORD or --password is required.")

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
