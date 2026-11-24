import psycopg2

url = 'postgresql://postgres.lnvmixljyhujzkoxlfvw:ceaJaMms8ka8DOsc@aws-0-ap-south-1.pooler.supabase.com:5432/postgres'
try:
    conn = psycopg2.connect(url, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Total public tables in Supabase: {len(tables)}")
    print("Sample tables:", tables[:30])
    
    # Check if django_migrations exists
    if "django_migrations" in tables:
        cur.execute("SELECT app, name, applied FROM django_migrations ORDER BY applied DESC LIMIT 10;")
        migrations = cur.fetchall()
        print("\nLatest applied migrations in Supabase:")
        for app, name, applied in migrations:
            print(f"  {app}.{name} at {applied}")
    conn.close()
except Exception as e:
    print(f"Error connecting to Supabase: {e}")
