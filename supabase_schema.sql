-- 블로그 생성 프로젝트 테이블
CREATE TABLE IF NOT EXISTS blog_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,

    -- 레퍼런스 정보
    reference_url TEXT,
    reference_text TEXT NOT NULL,

    -- 분석 결과
    analysis_result TEXT,

    -- 생성 정보
    topic TEXT NOT NULL,
    keywords TEXT,
    requirements TEXT,
    generated_content TEXT,

    -- 메타데이터
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'analyzing', 'generating', 'completed')),
    tags TEXT[]
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_blog_projects_created_at ON blog_projects(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_blog_projects_status ON blog_projects(status);
CREATE INDEX IF NOT EXISTS idx_blog_projects_topic ON blog_projects USING gin(to_tsvector('korean', topic));

-- 업데이트 시간 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_blog_projects_updated_at BEFORE UPDATE ON blog_projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security (RLS) 활성화
ALTER TABLE blog_projects ENABLE ROW LEVEL SECURITY;

-- 모든 사용자가 읽기 가능 (익명 사용자 포함)
CREATE POLICY "Enable read access for all users" ON blog_projects
    FOR SELECT USING (true);

-- 모든 사용자가 생성 가능
CREATE POLICY "Enable insert access for all users" ON blog_projects
    FOR INSERT WITH CHECK (true);

-- 모든 사용자가 수정 가능
CREATE POLICY "Enable update access for all users" ON blog_projects
    FOR UPDATE USING (true);

-- 모든 사용자가 삭제 가능
CREATE POLICY "Enable delete access for all users" ON blog_projects
    FOR DELETE USING (true);
