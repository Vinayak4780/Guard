# Guard Management System

A comprehensive FastAPI-based Guard Management System with Email-OTP authentication, role-based access control, QR code patrol tracking, TomTom API integration, and Google Sheets logging.

## 🎯 Key Features

### Email-OTP Authentication System
- **Secure Signup**: Email verification with OTP codes
- **JWT Authentication**: Access and refresh token management
- **Password Reset**: Secure password recovery flow
- **Rate Limiting**: OTP attempt protection
- **Email Verification**: Complete account verification workflow

### Role-Based Access Control
- **ADMIN**: Complete system management and user oversight
- **SUPERVISOR**: Area management and guard coordination  
- **GUARD**: QR scanning and patrol activities
- **Secure Permissions**: Strict role-based endpoint protection
- **Token Management**: JWT with refresh capability

### QR Code Patrol System
- **Permanent QR Locations**: One QR per supervisor area
- **GPS Validation**: Location-based scan verification
- **Mobile Scanning**: Public and authenticated scan endpoints
- **Distance Checking**: Configurable radius validation
- **Real-time Logging**: Instant patrol event recording

### External Integrations
- **TomTom API**: Reverse geocoding and POI search
- **Google Sheets**: Automatic scan event logging
- **Email Service**: SMTP-based OTP and notifications
- **Distance Calculations**: GPS-based validation
- **Address Lookup**: Location verification and formatting

### Advanced Features
- **Multi-area Support**: Supervisor-specific QR management
- **Audit Trails**: Comprehensive activity logging
- **Health Monitoring**: System and service health checks
- **Bulk Operations**: Mass QR generation and management
- **Data Export**: Google Sheets integration for reporting

## 🏗️ System Architecture

### Core Components
- **Authentication Service**: Email-OTP with JWT tokens
- **Authorization System**: Role-based access control
- **QR Management**: Location-based scanning workflow
- **External Services**: TomTom, Google Sheets, Email
- **Database Layer**: MongoDB with optimized indexes
- **API Layer**: FastAPI with comprehensive endpoints

### Database Collections
- **users**: Core user accounts with email verification
- **supervisors**: Area-specific supervisor profiles
- **guards**: Guard profiles with supervisor assignments
- **qr_locations**: Permanent QR code locations with GPS
- **scan_events**: All scanning activities with coordinates
- **otp_tokens**: OTP management (TTL indexed for cleanup)
- **refresh_tokens**: JWT refresh token storage

### Security Features
- **Email Verification**: All accounts require email confirmation
- **OTP Protection**: Rate limiting and expiration controls
- **JWT Security**: Secure token generation and validation
- **Role Enforcement**: Strict permission checking
- **GPS Validation**: Location-based access controls
- **Audit Logging**: Complete activity tracking

## 📱 API Endpoints Overview

### Authentication System (`/auth`)
- `POST /signup` - Email-OTP user registration
- `POST /verify-otp` - OTP code verification
- `POST /login` - JWT token authentication
- `POST /logout` - Secure token invalidation
- `POST /refresh` - Access token renewal
- `POST /reset-password-request` - Password reset initiation
- `POST /reset-password` - Password reset completion
- `GET /profile` - User profile information

### Admin Management (`/admin`)
- `GET /dashboard` - System statistics and overview
- `GET /users` - Complete user management
- `POST /supervisors` - Create supervisor accounts
- `POST /guards` - Create guard accounts
- `GET /supervisors` - List all supervisors
- `GET /guards` - List all guards
- `POST /reports/area` - Generate area-based reports
- `GET /system/health` - System health monitoring
- `POST /system/config` - System configuration management

### Supervisor Operations (`/supervisor`)
- `GET /dashboard` - Area-specific statistics
- `POST /qr-locations` - Create QR code locations
- `GET /qr-locations` - Manage QR locations
- `PUT /qr-locations/{qr_id}` - Update QR locations
- `DELETE /qr-locations/{qr_id}` - Remove QR locations
- `GET /guards` - View assigned guards
- `GET /scan-events` - Monitor area scan activities
- `GET /google-sheets` - Access Google Sheets logs

### Guard Activities (`/guard`)
- `GET /dashboard` - Personal statistics dashboard
- `POST /scan-qr` - QR code scanning with GPS
- `GET /scan-history` - Personal scan history
- `GET /available-qr-locations` - Available QR locations
- `GET /patrol-summary` - Daily patrol summaries
- `GET /profile` - Guard profile management

### QR Code System (`/qr`)
- `POST /public/scan` - Public QR scanning (no auth)
- `GET /public/location/{qr_id}` - Public QR information
- `POST /generate` - Generate QR code images
- `GET /validate/{qr_id}` - Validate QR codes
- `POST /bulk-generate` - Bulk QR generation
- `GET /scan-stats/{qr_id}` - QR scan statistics

## 🛠️ Setup Instructions

### Prerequisites
- **Python 3.8+**: Modern Python runtime
- **MongoDB 4.4+**: Document database
- **SMTP Email Service**: Gmail or similar for OTP delivery
- **TomTom API Key**: Location services access
- **Google Sheets API**: Optional but recommended for logging

### Installation Steps

1. **Navigate to project directory**:
```bash
cd "c:\Users\vinay\OneDrive\Desktop\Gaurd"
```

2. **Activate virtual environment**:
```bash
# Windows PowerShell
myenv\Scripts\Activate.ps1

# Windows Command Prompt
myenv\Scripts\activate.bat
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Environment Configuration**:
```bash
# Copy the environment template
copy .env.example .env

# Edit .env with your actual values:
# - Database connection string
# - JWT secret key (generate a secure one)
# - SMTP email configuration
# - TomTom API key
# - Google Sheets credentials (optional)
```

5. **Start the application**:
```bash
# Development mode
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or use the start script
start.bat
```

## 🔧 Configuration

### Required Environment Variables

```env
# Database
DATABASE_URL=mongodb://localhost:27017/guard_management
DATABASE_NAME=guard_management

# JWT Security
JWT_SECRET_KEY=your-super-secure-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Email SMTP
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com

# TomTom API
TOMTOM_API_KEY=your-tomtom-api-key

# System
WITHIN_RADIUS_METERS=100.0
OTP_EXPIRE_MINUTES=10
```

### Optional Configuration

```env
# Google Sheets (for automatic logging)
GOOGLE_SHEETS_CREDENTIALS_JSON={"type": "service_account", ...}

# Admin User (created on first run)
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=secure-password
DEFAULT_ADMIN_NAME=System Administrator
```

## 📱 Usage Guide

### For Administrators

1. **System Setup**:
   - Access the admin panel at `/docs` (Swagger UI)
   - Create supervisors for different areas
   - Assign guards to supervisors
   - Configure system settings

2. **User Management**:
   - View all users and their status
   - Generate area-wise reports
   - Monitor system health and statistics

### For Supervisors

1. **QR Location Management**:
   - Create permanent QR locations for patrol points
   - Generate QR code images for physical placement
   - Update location details and coordinates

2. **Guard Oversight**:
   - Monitor assigned guards' activities
   - View scan events and patrol coverage
   - Access Google Sheets for detailed logs

### For Guards

1. **QR Scanning**:
   - Use mobile app to scan QR codes at patrol points
   - GPS validation ensures accurate location reporting
   - Add notes and additional information

2. **Activity Tracking**:
   - View personal scan history
   - Check daily patrol summaries
   - Monitor performance statistics

## 🔌 API Integration

### Authentication Flow

```python
# 1. Signup with email
POST /auth/signup
{
    "email": "guard@example.com",
    "password": "securepass123",
    "name": "John Guard",
    "role": "GUARD"
}

# 2. Verify OTP
POST /auth/verify-otp
{
    "email": "guard@example.com",
    "otp": "123456"
}

# 3. Login
POST /auth/login
{
    "email": "guard@example.com",
    "password": "securepass123"
}
```

### QR Scanning Integration

```python
# Public scan endpoint for mobile apps
POST /qr/public/scan
{
    "qrId": "QR123456",
    "guardEmail": "guard@example.com",
    "coordinates": {
        "latitude": 40.7128,
        "longitude": -74.0060
    },
    "notes": "All clear"
}
```

## 🗄️ Database Schema

### Key Collections

- **users**: Core user accounts with email verification
- **supervisors**: Area-specific supervisor data
- **guards**: Guard profiles with supervisor assignments
- **qr_locations**: Permanent QR code locations
- **scan_events**: All scanning activities with GPS data
- **otp_tokens**: Temporary OTP storage (TTL indexed)

### Indexes for Performance

- TTL indexes on `otp_tokens` and `refresh_tokens`
- Compound indexes on scan queries
- Text indexes for search functionality

## 🔒 Security Features

- **Email Verification**: All accounts require email confirmation
- **JWT Tokens**: Secure access with refresh capability
- **Role-based Access**: Strict permission controls
- **Rate Limiting**: OTP attempt limitations
- **GPS Validation**: Location-based scan verification
- **Audit Trails**: Comprehensive activity logging

## 📊 Monitoring & Logging

### Health Checks
- Database connectivity
- External API status
- Service health endpoints
- Configuration validation

### Logging
- Structured JSON logs
- User activity tracking
- Error monitoring
- Performance metrics

## 🚀 Deployment

### Production Checklist

1. **Security**:
   - Generate strong JWT secret
   - Configure HTTPS
   - Set secure SMTP credentials
   - Validate all environment variables

2. **Database**:
   - MongoDB with authentication
   - Backup strategy
   - Index optimization
   - Connection pooling

3. **Services**:
   - TomTom API rate limits
   - Google Sheets permissions
   - Email service quotas
   - Health monitoring

### Docker Deployment (Optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Check the API documentation at `/docs`
- Review environment configuration
- Verify database connectivity
- Check service logs for errors

## 🔄 Version History

### v1.0.0 (Current)
- Email-OTP authentication system
- JWT token management
- Role-based access control
- QR code scanning with GPS validation
- TomTom API integration
- Google Sheets logging
- Comprehensive admin panel
- Multi-area support
