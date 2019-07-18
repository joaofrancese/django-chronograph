from ...models import Job
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Runs all jobs that are due.'
    
    def handle(self, *args, **options):
        Job.objects.reset_stuck_jobs()
        for job in Job.objects.due():
            if Job.objects.is_job_due(job):
                job.run()
