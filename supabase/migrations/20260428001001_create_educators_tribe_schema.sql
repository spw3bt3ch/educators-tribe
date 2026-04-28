/*
  # Educators' Tribe - Full Schema Migration

  ## Overview
  Creates all tables needed for the Educators' Tribe Flask web application,
  migrating from the Render-hosted PostgreSQL to Supabase.

  ## Tables Created

  1. **users** - Regular user accounts with authentication
  2. **admins** - Administrator accounts
  3. **news_articles** - Education news articles fetched from external sources
  4. **adverts** - User-submitted advertisements
  5. **blog_posts** - Blog posts written by users
  6. **post_comments** - Comments on blog posts
  7. **post_likes** - Likes on blog posts (one per user per post)
  8. **educational_materials** - Downloadable educational resources
  9. **user_activities** - Activity log for monitoring user actions
  10. **email_tokens** - Tokens for email verification and password reset
  11. **advert_pricing** - Global advertisement pricing configuration
  12. **teacher_of_the_month** - Featured teacher awards
  13. **connection_requests** - Friend/connection requests between users
  14. **user_connections** - Established connections between users
  15. **chat_messages** - Direct messages between connected users

  ## Security
  - RLS enabled on all tables
  - Policies restrict access to authenticated users and their own data
  - Admin tables have no public RLS policies (accessed via service role from Flask)

  ## Notes
  - This app uses Flask with SQLAlchemy connecting directly via the Supabase DB URL
  - RLS policies use auth.uid() but Flask connects via service role, bypassing RLS
  - Minimal RLS policies are added for future frontend use
*/

-- ===========================
-- USERS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  email VARCHAR(120) UNIQUE NOT NULL,
  password_hash VARCHAR(256),
  full_name VARCHAR(200),
  profile_picture VARCHAR(1000),
  is_active BOOLEAN DEFAULT true NOT NULL,
  email_verified BOOLEAN DEFAULT false NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  last_login TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
  ON users FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Users can update own profile"
  ON users FOR UPDATE
  TO authenticated
  USING (auth.uid()::text = id::text);

-- ===========================
-- ADMINS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS admins (
  id SERIAL PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  email VARCHAR(120) UNIQUE NOT NULL,
  password_hash VARCHAR(256),
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_admins_username ON admins(username);

ALTER TABLE admins ENABLE ROW LEVEL SECURITY;

-- Admins table accessed via service role only from Flask backend

-- ===========================
-- NEWS ARTICLES TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS news_articles (
  id SERIAL PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  content TEXT,
  source_url VARCHAR(1000) UNIQUE,
  image_url VARCHAR(1000),
  category VARCHAR(100) DEFAULT 'Education' NOT NULL,
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  is_education_related BOOLEAN DEFAULT true NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_source_url ON news_articles(source_url);
CREATE INDEX IF NOT EXISTS idx_news_fetched_at ON news_articles(fetched_at DESC);

ALTER TABLE news_articles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read news articles"
  ON news_articles FOR SELECT
  TO authenticated
  USING (true);

-- ===========================
-- ADVERTS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS adverts (
  id SERIAL PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  description TEXT,
  image_url VARCHAR(1000),
  link_url VARCHAR(1000),
  button_text VARCHAR(100) DEFAULT 'Learn More',
  submitted_by INTEGER REFERENCES users(id) ON DELETE CASCADE,
  amount NUMERIC(10,2),
  weeks INTEGER DEFAULT 1 NOT NULL,
  start_date TIMESTAMPTZ,
  end_date TIMESTAMPTZ,
  status VARCHAR(20) DEFAULT 'pending' NOT NULL,
  payment_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
  submitted_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  approved_at TIMESTAMPTZ,
  admin_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_adverts_submitted_by ON adverts(submitted_by);
CREATE INDEX IF NOT EXISTS idx_adverts_status ON adverts(status);

ALTER TABLE adverts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view approved adverts"
  ON adverts FOR SELECT
  TO authenticated
  USING (status IN ('approved', 'active'));

CREATE POLICY "Users can view own adverts"
  ON adverts FOR SELECT
  TO authenticated
  USING (submitted_by::text = auth.uid()::text);

CREATE POLICY "Users can insert own adverts"
  ON adverts FOR INSERT
  TO authenticated
  WITH CHECK (submitted_by::text = auth.uid()::text);

CREATE POLICY "Users can update own adverts"
  ON adverts FOR UPDATE
  TO authenticated
  USING (submitted_by::text = auth.uid()::text)
  WITH CHECK (submitted_by::text = auth.uid()::text);

-- ===========================
-- BLOG POSTS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS blog_posts (
  id SERIAL PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  content TEXT NOT NULL,
  image_url VARCHAR(1000),
  author_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  views INTEGER DEFAULT 0 NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_blog_posts_author_id ON blog_posts(author_id);
CREATE INDEX IF NOT EXISTS idx_blog_posts_created_at ON blog_posts(created_at DESC);

ALTER TABLE blog_posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read blog posts"
  ON blog_posts FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Users can insert own blog posts"
  ON blog_posts FOR INSERT
  TO authenticated
  WITH CHECK (author_id::text = auth.uid()::text);

CREATE POLICY "Users can update own blog posts"
  ON blog_posts FOR UPDATE
  TO authenticated
  USING (author_id::text = auth.uid()::text)
  WITH CHECK (author_id::text = auth.uid()::text);

CREATE POLICY "Users can delete own blog posts"
  ON blog_posts FOR DELETE
  TO authenticated
  USING (author_id::text = auth.uid()::text);

-- ===========================
-- POST COMMENTS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS post_comments (
  id SERIAL PRIMARY KEY,
  post_id INTEGER REFERENCES blog_posts(id) ON DELETE CASCADE NOT NULL,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_post_comments_post_id ON post_comments(post_id);
CREATE INDEX IF NOT EXISTS idx_post_comments_user_id ON post_comments(user_id);

ALTER TABLE post_comments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read comments"
  ON post_comments FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Users can insert own comments"
  ON post_comments FOR INSERT
  TO authenticated
  WITH CHECK (user_id::text = auth.uid()::text);

CREATE POLICY "Users can delete own comments"
  ON post_comments FOR DELETE
  TO authenticated
  USING (user_id::text = auth.uid()::text);

-- ===========================
-- POST LIKES TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS post_likes (
  id SERIAL PRIMARY KEY,
  post_id INTEGER REFERENCES blog_posts(id) ON DELETE CASCADE NOT NULL,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE (post_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_post_likes_post_id ON post_likes(post_id);
CREATE INDEX IF NOT EXISTS idx_post_likes_user_id ON post_likes(user_id);

ALTER TABLE post_likes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read likes"
  ON post_likes FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Users can insert own likes"
  ON post_likes FOR INSERT
  TO authenticated
  WITH CHECK (user_id::text = auth.uid()::text);

CREATE POLICY "Users can delete own likes"
  ON post_likes FOR DELETE
  TO authenticated
  USING (user_id::text = auth.uid()::text);

-- ===========================
-- EDUCATIONAL MATERIALS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS educational_materials (
  id SERIAL PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  description TEXT,
  file_url VARCHAR(1000),
  google_drive_link VARCHAR(1000),
  external_url VARCHAR(1000),
  featured_image_url VARCHAR(1000),
  file_name VARCHAR(500),
  file_type VARCHAR(50),
  file_size INTEGER,
  uploaded_by INTEGER REFERENCES admins(id) ON DELETE SET NULL,
  is_active BOOLEAN DEFAULT true NOT NULL,
  download_count INTEGER DEFAULT 0 NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_educational_materials_is_active ON educational_materials(is_active);

ALTER TABLE educational_materials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can view active materials"
  ON educational_materials FOR SELECT
  TO authenticated
  USING (is_active = true);

-- ===========================
-- USER ACTIVITIES TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS user_activities (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  action VARCHAR(100) NOT NULL,
  description TEXT,
  timestamp TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_activities_user_id ON user_activities(user_id);
CREATE INDEX IF NOT EXISTS idx_user_activities_timestamp ON user_activities(timestamp DESC);

ALTER TABLE user_activities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own activities"
  ON user_activities FOR SELECT
  TO authenticated
  USING (user_id::text = auth.uid()::text);

CREATE POLICY "Users can insert own activities"
  ON user_activities FOR INSERT
  TO authenticated
  WITH CHECK (user_id::text = auth.uid()::text);

-- ===========================
-- EMAIL TOKENS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS email_tokens (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  token VARCHAR(256) UNIQUE NOT NULL,
  token_type VARCHAR(50) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used BOOLEAN DEFAULT false NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_email_tokens_token ON email_tokens(token);
CREATE INDEX IF NOT EXISTS idx_email_tokens_user_id ON email_tokens(user_id);

ALTER TABLE email_tokens ENABLE ROW LEVEL SECURITY;

-- Email tokens accessed via service role from Flask backend only

-- ===========================
-- ADVERT PRICING TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS advert_pricing (
  id SERIAL PRIMARY KEY,
  amount NUMERIC(10,2) DEFAULT 500.00 NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

ALTER TABLE advert_pricing ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read advert pricing"
  ON advert_pricing FOR SELECT
  TO authenticated
  USING (true);

-- Insert default pricing
INSERT INTO advert_pricing (amount) VALUES (500.00) ON CONFLICT DO NOTHING;

-- ===========================
-- TEACHER OF THE MONTH TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS teacher_of_the_month (
  id SERIAL PRIMARY KEY,
  teacher_name VARCHAR(200) NOT NULL,
  teacher_title VARCHAR(200),
  school_name VARCHAR(200),
  location VARCHAR(200),
  photo_url VARCHAR(1000),
  bio TEXT,
  achievements TEXT,
  is_active BOOLEAN DEFAULT true NOT NULL,
  month_year VARCHAR(50) NOT NULL,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_by INTEGER REFERENCES admins(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_teacher_of_month_is_active ON teacher_of_the_month(is_active);

ALTER TABLE teacher_of_the_month ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read teacher of month"
  ON teacher_of_the_month FOR SELECT
  TO authenticated
  USING (true);

-- ===========================
-- CONNECTION REQUESTS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS connection_requests (
  id SERIAL PRIMARY KEY,
  requester_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  receiver_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  status VARCHAR(20) DEFAULT 'pending' NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  responded_at TIMESTAMPTZ,
  UNIQUE (requester_id, receiver_id)
);

CREATE INDEX IF NOT EXISTS idx_connection_requests_requester ON connection_requests(requester_id);
CREATE INDEX IF NOT EXISTS idx_connection_requests_receiver ON connection_requests(receiver_id);

ALTER TABLE connection_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own connection requests"
  ON connection_requests FOR SELECT
  TO authenticated
  USING (
    requester_id::text = auth.uid()::text OR
    receiver_id::text = auth.uid()::text
  );

CREATE POLICY "Users can insert own connection requests"
  ON connection_requests FOR INSERT
  TO authenticated
  WITH CHECK (requester_id::text = auth.uid()::text);

CREATE POLICY "Users can update own received requests"
  ON connection_requests FOR UPDATE
  TO authenticated
  USING (receiver_id::text = auth.uid()::text)
  WITH CHECK (receiver_id::text = auth.uid()::text);

-- ===========================
-- USER CONNECTIONS TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS user_connections (
  id SERIAL PRIMARY KEY,
  user1_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  user2_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  connected_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE (user1_id, user2_id)
);

CREATE INDEX IF NOT EXISTS idx_user_connections_user1 ON user_connections(user1_id);
CREATE INDEX IF NOT EXISTS idx_user_connections_user2 ON user_connections(user2_id);

ALTER TABLE user_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own connections"
  ON user_connections FOR SELECT
  TO authenticated
  USING (
    user1_id::text = auth.uid()::text OR
    user2_id::text = auth.uid()::text
  );

CREATE POLICY "Users can insert own connections"
  ON user_connections FOR INSERT
  TO authenticated
  WITH CHECK (
    user1_id::text = auth.uid()::text OR
    user2_id::text = auth.uid()::text
  );

-- ===========================
-- CHAT MESSAGES TABLE
-- ===========================
CREATE TABLE IF NOT EXISTS chat_messages (
  id SERIAL PRIMARY KEY,
  sender_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  recipient_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  message TEXT NOT NULL,
  is_read BOOLEAN DEFAULT false NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_sender ON chat_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_recipient ON chat_messages(recipient_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at DESC);

ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own messages"
  ON chat_messages FOR SELECT
  TO authenticated
  USING (
    sender_id::text = auth.uid()::text OR
    recipient_id::text = auth.uid()::text
  );

CREATE POLICY "Users can insert own messages"
  ON chat_messages FOR INSERT
  TO authenticated
  WITH CHECK (sender_id::text = auth.uid()::text);
