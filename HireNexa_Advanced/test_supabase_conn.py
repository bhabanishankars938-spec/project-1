import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('.env', override=True)
db_url = os.environ.get('DATABASE_URL')
print('Host target:', db_url.split('@')[-1] if db_url else 'None')
try:
    conn = psycopg2.connect(db_url, connect_timeout=15)
    cur = conn.cursor()
    cur.execute('SELECT version();')
    ver = cur.fetchone()
    print('PostgreSQL Version:', ver[0])
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    tables = [r[0] for r in cur.fetchall()]
    print('Public Tables count:', len(tables))
    print('Public Tables:', sorted(tables))
    cur.close()
    conn.close()
    print('SUPABASE_CONNECTION_SUCCESS')
except Exception as e:
    print('Connection error:', type(e).__name__, e)
