# Fleet Manager Deployment Guide

## Environment Setup

### 1. Local Development (Your Machine)
```bash
# Set environment variables
export ENV=development
export STORAGE_TYPE=filesystem
export LOCAL_DEV_STORAGE_PATH=./local_storage

# Run locally
uvicorn app.main:app --reload --port 8000
```

### 2. Dev Server Deployment (Linux Server)
```bash
# Create storage directory on dev server
sudo mkdir -p /var/lib/fleet/dev-storage
sudo chown -R your-user:your-group /var/lib/fleet/dev-storage
sudo chmod 750 /var/lib/fleet/dev-storage

# Deploy using Docker Compose
docker-compose -f docker-compose_dev.yaml up -d

# Check storage info endpoint
curl -H "Authorization: Bearer <admin-token>" \
  http://your-dev-server:8100/api/v1/vehicles/storage/info
```

### 3. Production Deployment (Current - Filesystem)
```bash
# Create storage directory on production server
sudo mkdir -p /var/lib/fleet/storage
sudo chown -R fleet-user:fleet-group /var/lib/fleet/storage
sudo chmod 750 /var/lib/fleet/storage

# Deploy using Docker Compose
docker-compose -f docker-compose_prod.yaml up -d
```

### 4. Production Migration to AWS S3 (Future)
```bash
# Update environment variables
export ENV=production
export STORAGE_TYPE=s3
export S3_STORAGE_URL=s3://your-fleet-bucket/documents
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret

# Redeploy - no volume mapping needed for cloud storage
docker-compose -f docker-compose_prod.yaml up -d
```

## Storage Migration Path

1. **Current**: Local Dev → Dev Server Filesystem → Prod Filesystem
2. **Future**: Local Dev → Dev Server Filesystem → AWS S3

## File Organization
```
Storage Root/
├── vendor_1/
│   ├── vehicle_ABC123/
│   │   ├── puc/
│   │   ├── fitness/
│   │   ├── insurance/
│   │   ├── permit/
│   │   └── tax_receipt/
│   └── vehicle_XYZ789/
└── vendor_2/
    └── vehicle_DEF456/
```
