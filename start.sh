#!/bin/bash

# OlimpQR Startup Script
# This script will start all services and set up the application

echo "======================================"
echo "  OlimpQR - Starting Application"
echo "======================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker Desktop first."
    exit 1
fi

echo "✓ Docker is running"
echo ""

# Start all services
echo "📦 Starting Docker containers..."
docker-compose up -d

# Wait for services to be healthy
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if backend is up
echo ""
echo "🔍 Checking backend health..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Backend is healthy"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Backend failed to start. Check logs with: docker-compose logs backend"
        exit 1
    fi
    sleep 2
done

# Apply database migrations
echo ""
echo "🗄️  Applying database migrations..."
docker-compose exec -T backend alembic upgrade head

# Check if admin user should be created
echo ""
read -p "Do you want to create an admin user? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    read -p "Enter admin email (default: admin@admin.com): " ADMIN_EMAIL
    ADMIN_EMAIL=${ADMIN_EMAIL:-admin@admin.com}

    echo "Enter admin password: "
    read -s ADMIN_PASSWORD
    echo ""

    if [ -z "$ADMIN_PASSWORD" ]; then
        echo "❌ Password cannot be empty"
        exit 1
    fi

    echo "Creating admin user..."
    ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" docker-compose exec -T backend python scripts/init_admin.py
    ADMIN_CREATE_EXIT=$?

    if [ $ADMIN_CREATE_EXIT -ne 0 ]; then
        echo ""
        echo "======================================"
        echo "  Admin Creation Failed"
        echo "======================================"
        echo "Possible reason:"
        echo "  Database credentials mismatch in .env:"
        echo "  POSTGRES_PASSWORD must match password in DATABASE_URL."
        echo ""
        echo "If DB password was changed after first start, old postgres volume may keep old credentials."
        echo "Reset data (WARNING: removes local DB data):"
        echo "  docker-compose down -v"
        echo "  docker-compose up -d"
        exit 1
    fi

    echo ""
    echo "======================================"
    echo "  Admin Account Created!"
    echo "======================================"
    echo "Email: $ADMIN_EMAIL"
    echo "Password: [hidden]"
    echo ""
fi

echo ""
echo "======================================"
echo "  ✅ Application Started Successfully!"
echo "======================================"
echo ""
echo "Access the application at:"
echo "  Frontend:    http://localhost:5173"
echo "  Backend API: http://localhost:8000/docs"
echo "  MinIO:       http://localhost:9001 (minioadmin/minioadmin)"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f backend"
echo "  docker-compose logs -f frontend"
echo ""
echo "To stop all services:"
echo "  docker-compose down"
echo ""
