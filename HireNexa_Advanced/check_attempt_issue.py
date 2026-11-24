import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from assessments.models import Examination, ExamAttempt
from accounts.models import User

print("DATABASE ENGINE:", settings.DATABASES['default']['ENGINE'])
print("DATABASE NAME/HOST:", settings.DATABASES['default'].get('NAME'), settings.DATABASES['default'].get('HOST'))

try:
    user = User.objects.filter(id=68).first()
    print("User 68:", user)
    exam = Examination.objects.filter(id=60).first()
    print("Exam 60:", exam)
    if exam:
        print("Exam title:", exam.title, "slug:", exam.slug)
    
    attempts = ExamAttempt.objects.filter(examination_id=60, user_id=68)
    print("Total attempts for (user=68, exam=60):", attempts.count())
    for att in attempts:
        print(f"Attempt id={att.id}, attempt_number={att.attempt_number}, status={att.status}, started_at={att.started_at}, score={att.score}")

    all_att_60 = ExamAttempt.objects.filter(examination_id=60)
    print("All attempts for exam 60:", all_att_60.count())

    # Let's also check all attempts with attempt_number duplicates or any exam attempts for user 68
    user_68_attempts = ExamAttempt.objects.filter(user_id=68)
    print("All attempts for user 68:", user_68_attempts.count())
    for att in user_68_attempts:
        print(f"Exam id={att.examination_id}, attempt_number={att.attempt_number}, status={att.status}")

except Exception as e:
    import traceback
    traceback.print_exc()
