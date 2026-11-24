-- ==============================================================================
-- HIRENEXA ENTERPRISE SUPABASE UPGRADE MIGRATION
-- 1. India Location Management (countries, states, districts, cities, areas, pin_codes)
-- 2. Candidate Project Portfolio & Supabase Storage Files
-- 3. PostgreSQL Row Level Security (RLS) Policies
-- ==============================================================================

-- 1. COUNTRIES
CREATE TABLE IF NOT EXISTS countries (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    iso2 VARCHAR(2) NOT NULL UNIQUE,
    iso3 VARCHAR(3) NOT NULL,
    phone_code VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. STATES
CREATE TABLE IF NOT EXISTS states (
    id BIGSERIAL PRIMARY KEY,
    country_id BIGINT NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(10) NOT NULL,
    type VARCHAR(30) NOT NULL DEFAULT 'state',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_states_country_name UNIQUE (country_id, name)
);
CREATE INDEX IF NOT EXISTS idx_states_name ON states(name);
CREATE INDEX IF NOT EXISTS idx_states_code ON states(code);

-- 3. DISTRICTS
CREATE TABLE IF NOT EXISTS districts (
    id BIGSERIAL PRIMARY KEY,
    state_id BIGINT NOT NULL REFERENCES states(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    headquarters VARCHAR(120) DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_districts_state_name UNIQUE (state_id, name)
);
CREATE INDEX IF NOT EXISTS idx_districts_state_name ON districts(state_id, name);

-- 4. CITIES
CREATE TABLE IF NOT EXISTS cities (
    id BIGSERIAL PRIMARY KEY,
    state_id BIGINT NOT NULL REFERENCES states(id) ON DELETE CASCADE,
    district_id BIGINT REFERENCES districts(id) ON DELETE SET NULL,
    name VARCHAR(120) NOT NULL,
    is_metro BOOLEAN NOT NULL DEFAULT FALSE,
    tier INT NOT NULL DEFAULT 2,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cities_state_name ON cities(state_id, name);
CREATE INDEX IF NOT EXISTS idx_cities_name ON cities(name);
CREATE INDEX IF NOT EXISTS idx_cities_is_metro ON cities(is_metro);

-- 5. AREAS
CREATE TABLE IF NOT EXISTS areas (
    id BIGSERIAL PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_areas_city_name ON areas(city_id, name);
CREATE INDEX IF NOT EXISTS idx_areas_name ON areas(name);

-- 6. PIN CODES
CREATE TABLE IF NOT EXISTS pin_codes (
    id BIGSERIAL PRIMARY KEY,
    pin_code VARCHAR(10) NOT NULL,
    state_id BIGINT NOT NULL REFERENCES states(id) ON DELETE CASCADE,
    district_id BIGINT REFERENCES districts(id) ON DELETE SET NULL,
    city_id BIGINT REFERENCES cities(id) ON DELETE SET NULL,
    area_id BIGINT REFERENCES areas(id) ON DELETE SET NULL,
    office_name VARCHAR(150) DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pin_codes_code ON pin_codes(pin_code);
CREATE INDEX IF NOT EXISTS idx_pin_codes_state_code ON pin_codes(state_id, pin_code);

-- 7. CANDIDATE PROJECT PORTFOLIO
CREATE TABLE IF NOT EXISTS project_portfolio (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    project_name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(100) NOT NULL DEFAULT 'Web Development',
    technologies VARCHAR(500) NOT NULL,
    github_url VARCHAR(500) DEFAULT '',
    live_demo_url VARCHAR(500) DEFAULT '',
    video_url VARCHAR(500) DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_portfolio_candidate_created ON project_portfolio(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_category ON project_portfolio(category);

-- 8. PROJECT FILES (Supabase Storage Reference)
CREATE TABLE IF NOT EXISTS project_files (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES project_portfolio(id) ON DELETE CASCADE,
    candidate_id BIGINT NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files(project_id);
CREATE INDEX IF NOT EXISTS idx_project_files_candidate ON project_files(candidate_id);

-- Add preferred_locations and preferred_work_mode to recruitment_candidateprofile if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'recruitment_candidateprofile' AND column_name = 'preferred_locations'
    ) THEN
        ALTER TABLE recruitment_candidateprofile ADD COLUMN preferred_locations JSONB NOT NULL DEFAULT '[]'::jsonb;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'recruitment_candidateprofile' AND column_name = 'preferred_work_mode'
    ) THEN
        ALTER TABLE recruitment_candidateprofile ADD COLUMN preferred_work_mode VARCHAR(40) NOT NULL DEFAULT 'ALL';
    END IF;
END $$;

-- ==============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

-- Enable RLS on Location Tables (Public Read)
ALTER TABLE countries ENABLE ROW LEVEL SECURITY;
ALTER TABLE states ENABLE ROW LEVEL SECURITY;
ALTER TABLE districts ENABLE ROW LEVEL SECURITY;
ALTER TABLE cities ENABLE ROW LEVEL SECURITY;
ALTER TABLE areas ENABLE ROW LEVEL SECURITY;
ALTER TABLE pin_codes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read countries" ON countries;
CREATE POLICY "Public read countries" ON countries FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read states" ON states;
CREATE POLICY "Public read states" ON states FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read districts" ON districts;
CREATE POLICY "Public read districts" ON districts FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read cities" ON cities;
CREATE POLICY "Public read cities" ON cities FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read areas" ON areas;
CREATE POLICY "Public read areas" ON areas FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read pin_codes" ON pin_codes;
CREATE POLICY "Public read pin_codes" ON pin_codes FOR SELECT USING (true);

-- Enable RLS on project_portfolio
ALTER TABLE project_portfolio ENABLE ROW LEVEL SECURITY;

-- 1. Candidates can insert their own projects
DROP POLICY IF EXISTS "Candidates can insert own projects" ON project_portfolio;
CREATE POLICY "Candidates can insert own projects" ON project_portfolio
    FOR INSERT WITH CHECK (
        current_user = 'postgres' OR
        auth.uid()::text = candidate_id::text OR
        current_setting('request.jwt.claim.sub', true) = candidate_id::text
    );

-- 2. Candidates can select their own projects (and HR / Admins can view authorized projects)
DROP POLICY IF EXISTS "Candidates and authorized HR can view projects" ON project_portfolio;
CREATE POLICY "Candidates and authorized HR can view projects" ON project_portfolio
    FOR SELECT USING (
        current_user = 'postgres' OR
        auth.uid()::text = candidate_id::text OR
        current_setting('request.jwt.claim.sub', true) = candidate_id::text OR
        EXISTS (
            SELECT 1 FROM accounts_user u 
            WHERE u.id::text = auth.uid()::text 
            AND u.role IN ('RECRUITER', 'COMPANY_ADMIN', 'OWNER')
        )
    );

-- 3. Candidates can update their own projects
DROP POLICY IF EXISTS "Candidates can update own projects" ON project_portfolio;
CREATE POLICY "Candidates can update own projects" ON project_portfolio
    FOR UPDATE USING (
        current_user = 'postgres' OR
        auth.uid()::text = candidate_id::text OR
        current_setting('request.jwt.claim.sub', true) = candidate_id::text
    );

-- 4. Candidates can delete their own projects
DROP POLICY IF EXISTS "Candidates can delete own projects" ON project_portfolio;
CREATE POLICY "Candidates can delete own projects" ON project_portfolio
    FOR DELETE USING (
        current_user = 'postgres' OR
        auth.uid()::text = candidate_id::text OR
        current_setting('request.jwt.claim.sub', true) = candidate_id::text
    );

-- Enable RLS on project_files
ALTER TABLE project_files ENABLE ROW LEVEL SECURITY;

-- 5. Candidates can insert their own files
DROP POLICY IF EXISTS "Candidates can insert own project files" ON project_files;
CREATE POLICY "Candidates can insert own project files" ON project_files
    FOR INSERT WITH CHECK (
        current_user = 'postgres' OR
        auth.uid()::text = candidate_id::text OR
        current_setting('request.jwt.claim.sub', true) = candidate_id::text
    );

-- 6. Candidates and authorized HR can select project files
DROP POLICY IF EXISTS "Candidates and authorized HR can select files" ON project_files;
CREATE POLICY "Candidates and authorized HR can select files" ON project_files
    FOR SELECT USING (
        current_user = 'postgres' OR
        auth.uid()::text = candidate_id::text OR
        current_setting('request.jwt.claim.sub', true) = candidate_id::text OR
        EXISTS (
            SELECT 1 FROM accounts_user u 
            WHERE u.id::text = auth.uid()::text 
            AND u.role IN ('RECRUITER', 'COMPANY_ADMIN', 'OWNER')
        )
    );

-- 7. Candidates can delete their own project files
DROP POLICY IF EXISTS "Candidates can delete own project files" ON project_files;
CREATE POLICY "Candidates can delete own project files" ON project_files
    FOR DELETE USING (
        current_user = 'postgres' OR
        auth.uid()::text = candidate_id::text OR
        current_setting('request.jwt.claim.sub', true) = candidate_id::text
    );
