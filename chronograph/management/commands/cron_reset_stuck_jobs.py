from ...models import Job
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Marks all long-running jobs as no longer running.'
    
    def handle(self, *args, **options):
        count = Job.objects.reset_stuck_jobs()
        self.stdout.write(u"Killed %s stuck job(s)." % count)
