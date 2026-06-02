import os

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from api.models import Agent, UserAPIAssignment


LEGACY_BOOTSTRAP_EMAIL = 'admin@leadbook.com.ar'
LEGACY_BOOTSTRAP_NAME = 'LeadBook Admin'


def _split_emails(value):
    return [part.strip().lower() for part in str(value or '').split(',') if part.strip()]


class Command(BaseCommand):
    help = 'Liberates APIs and soft-deletes the legacy real admin Agent created by the old bootstrap.'

    def add_arguments(self, parser):
        parser.add_argument('--email', action='append', default=[])

    def handle(self, *args, **options):
        emails = set()
        for value in options.get('email') or []:
            emails.update(_split_emails(value))
        emails.update(_split_emails(os.getenv('ADMIN_BOOTSTRAP_EMAIL')))
        emails.update(_split_emails(os.getenv('ADMIN_DASH_EMAIL')))
        emails.add(LEGACY_BOOTSTRAP_EMAIL)

        users = Agent.objects.all_including_deleted().filter(
            email__in=emails,
            eliminado_en__isnull=True,
        ).filter(
            Q(is_staff=True) | Q(is_superuser=True) | Q(nombre__iexact=LEGACY_BOOTSTRAP_NAME)
        )

        cleaned = 0
        released = 0
        for user in users:
            with transaction.atomic():
                released += UserAPIAssignment.objects.filter(user=user, activo=True).count()
                user.is_staff = False
                user.is_superuser = False
                user.plan_activo = False
                user.soft_delete()
                cleaned += 1

        if cleaned:
            self.stdout.write(self.style.SUCCESS(
                f'Legacy admin cleanup complete: users={cleaned}, released_assignments={released}'
            ))
        else:
            self.stdout.write('Legacy admin cleanup complete: nothing to clean.')
