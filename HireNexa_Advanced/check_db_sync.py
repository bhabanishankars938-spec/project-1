import os
import psycopg2
import sqlite3
from dotenv import load_dotenv

load_dotenv('.env', override=True)
db_url = os.environ.get('DATABASE_URL')

sqlite_conn = sqlite3.connect('db.sqlite3')
sq_cur = sqlite_conn.cursor()

pg_conn = psycopg2.connect(db_url, connect_timeout=15)
pg_cur = pg_conn.cursor()

tables_to_check = [
    'accounts_user',
    'recruitment_organization',
    'recruitment_job',
    'recruitment_application',
    'recruitment_interview',
    'assessments_entrancetrack',
    'assessments_subject',
    'assessments_topic',
    'assessments_subtopic',
    'assessments_question',
    'assessments_questionoption',
    'assessments_examination',
    'assessments_examattempt',
    'assessments_result',
    'countries',
    'states',
    'cities',
    'areas',
    'pin_codes'
]

print(f"{'Table':<35} | {'SQLite Count':<15} | {'Supabase Count':<15}")
print("-" * 70)

for t in tables_to_check:
    try:
        sq_cur.execute(f"SELECT COUNT(*) FROM {t}")
        sq_cnt = sq_cur.fetchone()[0]
    except Exception as e:
        sq_cnt = f"Err: {e}"
        
    try:
        pg_cur.execute(f"SELECT COUNT(*) FROM {t}")
        pg_cnt = pg_cur.fetchone()[0]
    except Exception as e:
        pg_cnt = f"Err: {e}"
        
    print(f"{t:<35} | {str(sq_cnt):<15} | {str(pg_cnt):<15}")

sqlite_conn.close()
pg_conn.close()
