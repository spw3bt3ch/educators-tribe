# Testing Guide for Educators' Tribe

## MongoDB Migration Testing

### Prerequisites
1. ✅ MongoDB dependencies installed (pymongo, dnspython)
2. ✅ MongoDB connection configured (sample_mflix database)

### Startup Testing

1. **Start the application:**
   ```bash
   python app.py
   ```

2. **Expected Console Output:**
   - MongoDB connection confirmation
   - Demo credentials printed
   - Admin credentials printed

3. **Check for errors:**
   - MongoDB connection errors
   - Collection creation errors
   - Demo user creation errors

### Demo Credentials Testing

#### Admin Login Test
1. Navigate to: `http://localhost:5000/admin/login`
2. **Credentials:**
   - Username: `admin`
   - Password: `admin123`
3. **Expected:** Redirect to admin dashboard
4. **Test:**
   - View statistics
   - Access user management
   - Access advert management

#### User Login Tests
1. Navigate to: `http://localhost:5000/login`

**Test User 1: Teacher John**
- Username: `teacher_john`
- Password: `demo123`
- Expected: Login successful, access to user features

**Test User 2: Educator Mary**
- Username: `educator_mary`
- Password: `demo123`
- Expected: Login successful, access to user features

**Test User 3: Professor David**
- Username: `professor_david`
- Password: `demo123`
- Expected: Login successful, access to user features

### Feature Testing Checklist

#### ✅ User Features
- [ ] Registration (create new account)
- [ ] Login/Logout
- [ ] Submit advertisement
- [ ] View own advertisements
- [ ] View news articles
- [ ] View homepage

#### ✅ Admin Features
- [ ] Admin login
- [ ] View dashboard statistics
- [ ] View all users
- [ ] Toggle user active/inactive status
- [ ] View all advertisements
- [ ] Approve advertisements
- [ ] Reject advertisements
- [ ] Manually fetch news

#### ✅ Database Operations
- [ ] User creation in MongoDB
- [ ] Admin creation in MongoDB
- [ ] News article storage
- [ ] Advertisement storage
- [ ] Activity logging

### MongoDB Verification

To verify data in MongoDB:

1. **Connect to MongoDB:**
   - Database: `sample_mflix`
   - Collections: `users`, `admins`, `news_articles`, `adverts`, `blog_posts`, `user_activities`

2. **Check collections:**
   ```javascript
   // In MongoDB shell or Compass
   use sample_mflix
   db.users.find()
   db.admins.find()
   db.news_articles.find()
   db.adverts.find()
   ```

### Known Issues to Check

1. **Date formatting:** Some templates check for string vs datetime
2. **ObjectId handling:** All IDs converted to strings for compatibility
3. **User relationships:** Adverts linked via ObjectId references

### Troubleshooting

**If MongoDB connection fails:**
- Check connection string
- Verify network access to Atlas
- Check authentication credentials
- Application will fallback to local MongoDB

**If demo users not created:**
- Check console output for errors
- Verify MongoDB connection
- Check collection permissions

**If login fails:**
- Verify password hashing works
- Check user exists in MongoDB
- Verify ObjectId conversion

