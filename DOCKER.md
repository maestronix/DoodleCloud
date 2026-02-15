# Docker Deployment Guide

This guide will help you deploy DoodleCloud using Docker and Docker Compose.

## Prerequisites

- Docker installed ([Get Docker](https://docs.docker.com/get-docker/))
- Docker Compose installed (included with Docker Desktop)

## Quick Start

1. **Clone and navigate to the repository:**
   ```bash
   git clone https://github.com/depreciating/DoodleCloud.git
   cd DoodleCloud
   ```

2. **Create environment configuration:**
   ```bash
   cp .env.example .env
   ```

3. **Edit the `.env` file with your credentials:**
   ```env
   INSTA_USER=your_instagram_username
   INSTA_PASS=your_instagram_password
   DB_NAME=doodlecloud
   DB_USER=doodlecloud
   DB_PASS=change_this_to_a_secure_password
   ```

   **Important:** Use a burner Instagram account, not your personal account!

4. **Start the services:**
   ```bash
   docker-compose up -d
   ```

5. **Access the application:**
   Open your browser to: http://localhost:5000

## Docker Commands

### View logs
```bash
# View all logs
docker-compose logs -f

# View only app logs
docker-compose logs -f app

# View only database logs
docker-compose logs -f postgres
```

### Stop services
```bash
docker-compose down
```

### Stop and remove all data (including database)
```bash
docker-compose down -v
```

### Restart services
```bash
docker-compose restart
```

### Rebuild after code changes
```bash
docker-compose up -d --build
```

### Access the CLI
```bash
docker-compose exec app python cli.py
```

### Access a shell in the container
```bash
docker-compose exec app /bin/sh
```

## Troubleshooting

### Database connection errors
If the app can't connect to the database, check:
1. PostgreSQL is running: `docker-compose ps`
2. View database logs: `docker-compose logs postgres`
3. Restart services: `docker-compose restart`

### Port already in use
If port 5000 is already in use, edit `docker-compose.yml` and change:
```yaml
ports:
  - "5000:5000"  # Change first number, e.g., "8080:5000"
```

### Files not persisting
The `upload/`, `download/`, and `auth_cache/` directories are mounted as volumes. Ensure they exist in your project directory.

### Rebuilding from scratch
```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

## Architecture

The Docker setup includes:
- **App Container**: Python Flask application (DoodleCloud)
- **PostgreSQL Container**: Database for file metadata
- **Volumes**: Persistent storage for uploads, downloads, and authentication cache
- **Network**: Private network for communication between containers

## Security Notes

- Never commit your `.env` file to version control
- Use strong passwords for `DB_PASS`
- The PostgreSQL database is only accessible within the Docker network
- Always use a burner Instagram account for testing

## Production Deployment

For production deployment, consider:
1. Using an external PostgreSQL service (like Neon.tech)
2. Setting up SSL/TLS certificates
3. Using a reverse proxy (Nginx, Traefik)
4. Implementing proper backup strategies
5. Setting `debug=False` in `gui/app.py`

## External Database

To use an external PostgreSQL database instead of the Docker container:

1. Edit `docker-compose.yml` and remove the `postgres` service
2. Update your `.env` file with external database credentials:
   ```env
   DB_HOST=your-external-db-host.com
   DB_NAME=your_db_name
   DB_USER=your_db_user
   DB_PASS=your_db_password
   DB_PORT=5432
   ```
3. Start only the app: `docker-compose up -d app`
