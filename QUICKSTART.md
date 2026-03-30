# OlimpQR - Quick Start Guide

Everything is already configured! Just follow these simple steps:

## Prerequisites

- **Docker Desktop** must be installed and running
- **4GB+ RAM** available

## Step 1: Start Docker Desktop

Make sure Docker Desktop is running. You can check by looking for the Docker icon in your system tray.

## Step 2: Launch the Application

### On Windows (Easy Way):
Simply double-click `start.bat`

### Or using Command Line:
```bash
# Windows
start.bat

# Linux/Mac
chmod +x start.sh
./start.sh
```

The script will:
- ✅ Check if Docker is running
- ✅ Start all 6 services (PostgreSQL, Redis, MinIO, Backend, Celery, Frontend)
- ✅ Wait for services to be healthy
- ✅ Apply database migrations automatically

This takes about 1-2 minutes on first run (Docker needs to download images).

## Step 3: Create Admin Account

After the containers are running, create an admin user:

### On Windows (Easy Way):
Double-click `create_admin.bat`

### Or using Command Line:
```bash
docker-compose exec backend python scripts/init_admin.py
```

**Default credentials:**
- Email: `admin@admin.com`
- Password: You'll be prompted to set it

**Custom email:**
```bash
# Set environment variables
set ADMIN_EMAIL=your@email.com
set ADMIN_PASSWORD=YourSecurePassword123

# Create admin
docker-compose exec backend python scripts/init_admin.py
```

## Step 4: Access the Application

Open your browser and go to:
- **Frontend**: http://localhost:5173
- **Backend API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)

## Step 5: Login and Test

1. Open http://localhost:5173
2. Click "Login"
3. Enter your admin credentials
4. You're in! You can now:
   - Create competitions
   - Manage users
   - Test the entire workflow

## What's Running?

Your Docker setup includes:

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 5173 | React application |
| Backend | 8000 | FastAPI REST API |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Message broker |
| MinIO | 9000, 9001 | File storage |
| Celery Worker | - | OCR processing |

## Useful Commands

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f celery-worker
```

### Stop Everything
```bash
docker-compose down
```

### Restart a Service
```bash
docker-compose restart backend
```

### Check Service Status
```bash
docker-compose ps
```

### Access Database
```bash
docker-compose exec postgres psql -U olimpqr_user -d olimpqr
```

## Troubleshooting

### Port Already in Use
If you get port conflicts:
```bash
# Stop the conflicting service or change ports in docker-compose.yml
# Common conflicts: 5432 (PostgreSQL), 6379 (Redis), 8000 (Backend)
```

### Containers Won't Start
```bash
# Check Docker is running
docker info

# View detailed logs
docker-compose logs

# Force rebuild
docker-compose up -d --build --force-recreate
```

### `InvalidPasswordError` during admin creation
If you see:
`asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "olimpqr_user"`

Check `.env` consistency:
- `POSTGRES_PASSWORD=...`
- `DATABASE_URL=postgresql+asyncpg://olimpqr_user:<same-password>@postgres:5432/olimpqr`

These passwords must match.

If you changed DB password after the first startup, Postgres volume may still have old credentials.
Reset local data (warning: deletes local DB data):
```bash
docker-compose down -v
docker-compose up -d
```

### Reset Everything (Clean Slate)
```bash
# WARNING: This deletes all data!
docker-compose down -v
docker-compose up -d
```

## Next Steps

After logging in as admin, you can:

1. **Create a Competition**
   - Go to Admin Panel → Competitions → Create New
   - Set name, date, max score

2. **Create Other Users**
   - Admin Panel → Users → Add User
   - Create Admitter, Scanner, or Participant accounts

3. **Test the Full Workflow**
   - Register as participant
   - Get entry QR code
   - Scan QR (as admitter)
   - Generate answer sheet
   - Upload scan (as scanner)
   - View results

## Security Notes

- ✅ Secure keys have been generated automatically in `.env`
- ✅ All passwords are hashed with bcrypt
- ✅ JWT tokens for authentication
- ✅ Rate limiting enabled
- ⚠️ Change passwords before deploying to production
- ⚠️ Enable HTTPS for production deployment

## Configuration

All configuration is in `.env` file:
- Database credentials
- Secret keys (already generated)
- OCR settings
- MinIO settings

You can modify these values and restart containers:
```bash
docker-compose down
docker-compose up -d
```

## Support

- Check `README.md` for detailed documentation
- Check `CLAUDE.md` for architecture details
- View API documentation at http://localhost:8000/docs
- Check logs for errors: `docker-compose logs -f`

---

**That's it! You're ready to use OlimpQR! 🎉**
