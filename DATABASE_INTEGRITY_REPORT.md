# DATABASE INTEGRITY & SEEDING AUDIT REPORT
## HireNexa Database Engineering & Cloud Infrastructure

---

### Database Configurations

1. **Production Engine**: Supabase Cloud PostgreSQL (`db.xxxx.supabase.co:5432`)
2. **Local Fallback Engine**: SQLite3 (`db.sqlite3`), automatically activated when network is isolated or `USE_SQLITE=1`.
3. **ORM Compatibility**: All models use standard Django ORM with cross-engine compatible JSON fields, DateTime fields, and ForeignKeys.

### Entity & Schema Verification

| Entity Model | Migrations Applied | Record Integrity | Indexes & Constraints |
| :--- | :---: | :---: | :--- |
| `User` (Multi-Role) | 0001_initial | Verified | Unique `email`, `username`, role-based profiling |
| `Organization` | 0001_initial | Verified | Verification status, approval workflows, slug indexing |
| `Job` | 0001_initial | Verified | Workplace type, course departments, vacancy tracking |
| `Resume` & `Application` | 0001_initial | Verified | Multi-tenant isolation, AI match score caching |
| `Country`, `State`, `District`, `City`, `Area`, `PinCode` | 0001_initial | Verified | 36 States, all Odisha districts, metro cities, PIN lookup |
| `AssessmentTrack`, `Question`, `LearningNote` | 0001_initial | Verified | 197 exam topics, 3,152 verified MCQs, 197 study guides |

### Seeder Status
All seeders execute idempotently:
- `seed_entrance_prep`: 197 exam topics, 3,152 questions, 0 duplicate records.
- `seed_india_locations`: Complete hierarchy for Odisha, Karnataka, Maharashtra, Delhi, and Telangana.
- `seed_jobs`: MCA and MBA curated department roles with verified vacancy quotas.
