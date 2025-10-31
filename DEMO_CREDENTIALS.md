# Demo Credentials for Educators' Tribe

This document contains the demo credentials that are automatically created when you first run the application.

## Admin Account

**Access:** Admin Dashboard at `/admin/login`

- **Username:** `admin`
- **Password:** `admin123`
- **Email:** `admin@teacherstribe.com`

**Permissions:**
- Access to admin dashboard
- Manage users (activate/deactivate)
- Approve/reject advertisements
- Fetch news manually
- View all user activities

---

## Demo User Accounts

All demo users have the same password: `demo123`

### User 1: Teacher John
- **Username:** `teacher_john`
- **Password:** `demo123`
- **Full Name:** John Teacher
- **Email:** `john.teacher@example.com`

### User 2: Educator Mary
- **Username:** `educator_mary`
- **Password:** `demo123`
- **Full Name:** Mary Educator
- **Email:** `mary.educator@example.com`

### User 3: Professor David
- **Username:** `professor_david`
- **Password:** `demo123`
- **Full Name:** Professor David
- **Email:** `david.prof@example.com`

---

## User Permissions

Regular users can:
- View homepage and news
- Submit advertisement requests
- View their submitted advertisements
- Track advertisement status

---

## Security Note

⚠️ **IMPORTANT:** These are demo credentials for development and testing purposes only. **DO NOT use these credentials in production!** Always change all passwords before deploying to a production environment.

---

## How to Access

1. **Admin Login:**
   - Navigate to: `http://localhost:5000/admin/login`
   - Use admin credentials above

2. **User Login:**
   - Navigate to: `http://localhost:5000/login`
   - Use any demo user credentials above

3. **Registration:**
   - New users can register at: `http://localhost:5000/register`
   - Create your own account with a unique username and email

---

## Creating New Demo Users

To add more demo users, edit the `demo_users` list in `app.py` within the `init_db()` function:

```python
demo_users = [
    {'username': 'your_username', 'email': 'email@example.com', 
     'full_name': 'Your Name', 'password': 'your_password'},
    # Add more users...
]
```

The application will automatically create these users on startup if they don't already exist.
