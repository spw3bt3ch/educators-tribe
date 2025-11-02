# Nigerian Teachers Blog

A real-time Flask-based blog platform for Nigerian teachers featuring education news from PunchNG, user authentication, and an admin dashboard for monitoring user activities.

## Features

- 🎓 **Professional Homepage** - Beautiful, modern design with Tailwind CSS
- 🔐 **User Authentication** - Secure registration and login system
- 📰 **Education News** - Automatic fetching of Nigerian education news from PunchNG
- 👨‍💼 **Admin Dashboard** - Comprehensive admin panel to monitor users and activities
- 🔄 **Real-time Features** - WebSocket support using Flask-SocketIO
- 📊 **User Management** - Admin can activate/deactivate users
- 📈 **Activity Tracking** - Monitor user activities and statistics

## Installation

1. **Clone the repository** (or navigate to the project directory)

2. **Create a virtual environment** (recommended):
```bash
python -m venv venv
```

3. **Activate the virtual environment**:
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**:
```bash
pip install -r requirements.txt
```

## Configuration

The application uses PostgreSQL by default (configured for production). For production, you should set environment variables:

### Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - Flask secret key for sessions

**Optional:**
- `IMAGEKIT_PRIVATE_KEY` - ImageKit private key for image uploads (defaults to hardcoded value)
- `IMAGEKIT_PUBLIC_KEY` - ImageKit public key
- `IMAGEKIT_URL_ENDPOINT` - ImageKit URL endpoint

Example (local development):
```bash
export SECRET_KEY='your-secret-key-here'
export DATABASE_URL='postgresql://user:pass@host:port/db'
```

### Vercel Deployment

The application is configured to deploy on Vercel. After deploying, set these environment variables in the Vercel dashboard:

1. Go to your project in Vercel
2. Navigate to Settings > Environment Variables
3. Add the following variables:
   - `DATABASE_URL` - Your PostgreSQL connection string
   - `SECRET_KEY` - A secure random string
   - `IMAGEKIT_PRIVATE_KEY` - Your ImageKit private key (if different from default)
   - `IMAGEKIT_PUBLIC_KEY` - Your ImageKit public key (if different from default)
   - `IMAGEKIT_URL_ENDPOINT` - Your ImageKit URL endpoint (if different from default)

**Note:** The ImageKit credentials are already configured in the code. If you want to use your own ImageKit account, update the environment variables.

## Running the Application

1. **Run the Flask application**:
```bash
python app.py
```

2. **Access the application**:
   - Homepage: http://localhost:5000
   - Admin Login: http://localhost:5000/admin/login

## Default Admin Credentials

- **Username**: `admin`
- **Password**: `admin123`

⚠️ **IMPORTANT**: Change the admin password immediately after first login in production!

## Usage

### For Regular Users

1. **Register**: Click "Register" to create a new account
2. **Login**: Use your credentials to log in
3. **Browse News**: View the latest education news from PunchNG
4. **Stay Updated**: News is automatically fetched from PunchNG

### For Administrators

1. **Login**: Use the admin login page at `/admin/login`
2. **Dashboard**: Access statistics and recent activities
3. **Manage Users**: View all users and activate/deactivate accounts
4. **Fetch News**: Manually trigger news fetching from the dashboard
5. **Monitor Activities**: Track user registrations, logins, and other activities

## Project Structure

```
TtribeII/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── templates/            # HTML templates
│   ├── base.html         # Base template with navigation
│   ├── index.html        # Homepage
│   ├── register.html     # User registration
│   ├── login.html        # User login
│   ├── admin_login.html  # Admin login
│   ├── admin_dashboard.html  # Admin dashboard
│   ├── admin_users.html  # User management
│   └── news.html         # News page
└── static/               # Static files (CSS, JS, images)
```

## Database Models

- **User**: Regular user accounts with authentication
- **Admin**: Administrator accounts
- **NewsArticle**: Education news articles from PunchNG
- **BlogPost**: User blog posts
- **UserActivity**: Activity logs for monitoring

## News Fetching

The application automatically fetches education-related news from PunchNG every hour. The system:
- Searches for articles containing education-related keywords
- Filters and stores relevant news articles
- Displays them on the homepage and news page

## Technologies Used

- **Flask**: Web framework
- **SQLAlchemy**: Database ORM
- **Flask-Login**: User authentication
- **Flask-SocketIO**: Real-time WebSocket support
- **BeautifulSoup4**: Web scraping for news
- **Tailwind CSS**: Professional styling
- **Socket.IO**: Real-time client-server communication

## Security Notes

- Passwords are hashed using Werkzeug's security functions
- Admin routes are protected with decorators
- User authentication is handled securely
- Always use strong passwords in production

## Troubleshooting

### Database Issues
If you encounter database errors, delete the database file and restart the application to create a fresh database.

### News Not Fetching
- Check your internet connection
- Verify that PunchNG is accessible
- Check the console for error messages

### Port Already in Use
If port 5000 is already in use, modify the port in `app.py`:
```python
socketio.run(app, debug=True, host='0.0.0.0', port=5001)
```

## License

This project is open source and available for educational purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues or questions, please check the code comments or create an issue in the repository.

