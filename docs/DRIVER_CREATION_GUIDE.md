# Driver Creation Guide

## Endpoint

```
POST /api/v1/drivers/create
Content-Type: multipart/form-data
Authorization: Bearer <token>
Permission required: driver.create
```

---

## Form Fields

### Basic Info (all required unless marked optional)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | ✅ | Full name of the driver |
| `code` | string | ✅ | Unique driver code within the vendor |
| `email` | string | ✅ | Must be unique |
| `phone` | string | ✅ | Include country code e.g. `+919876543210` |
| `gender` | enum | ✅ | `Male`, `Female`, `Other` |
| `password` | string | ✅ | Plain text — hashed server-side |
| `vendor_id` | integer | ⚠️ | Required for Admin/Employee users. Vendor users auto-resolved. |
| `date_of_birth` | date | ❌ | Format: `YYYY-MM-DD` |
| `date_of_joining` | date | ❌ | Format: `YYYY-MM-DD` |
| `permanent_address` | string | ✅ | |
| `current_address` | string | ✅ | |

### License Info

| Field | Type | Required |
|-------|------|----------|
| `license_number` | string | ✅ |
| `license_expiry_date` | date | ✅ Must be a future date |

### Badge Info

| Field | Type | Required |
|-------|------|----------|
| `badge_number` | string | ✅ |
| `badge_expiry_date` | date | ✅ Must be a future date |

### Government ID

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `alt_govt_id_number` | string | ✅ | Aadhaar, PAN, Passport, etc. |
| `alt_govt_id_type` | string | ✅ | Type label e.g. `Aadhaar`, `PAN` |

### Verification Expiry Dates (all must be future dates)

| Field | Type | Required |
|-------|------|----------|
| `induction_date` | date | ✅ |
| `bg_expiry_date` | date | ✅ |
| `police_expiry_date` | date | ✅ |
| `medical_expiry_date` | date | ✅ |
| `training_expiry_date` | date | ✅ |
| `eye_expiry_date` | date | ✅ |

### Verification Statuses (optional, default = `PENDING`)

| Field | Allowed Values |
|-------|----------------|
| `bg_verify_status` | `PENDING`, `VERIFIED`, `REJECTED` |
| `police_verify_status` | `PENDING`, `VERIFIED`, `REJECTED` |
| `medical_verify_status` | `PENDING`, `VERIFIED`, `REJECTED` |
| `training_verify_status` | `PENDING`, `VERIFIED`, `REJECTED` |
| `eye_verify_status` | `PENDING`, `VERIFIED`, `REJECTED` |

---

## File Uploads

### Allowed File Types
- `image/jpeg` (`.jpg`, `.jpeg`)
- `image/png` (`.png`)
- `application/pdf` (`.pdf`)

### Max File Size
- **10 MB per file** (validated in `driver_router.py` → `file_size_validator(..., 10)`)

### File Fields

| Field | Required | Description |
|-------|----------|-------------|
| `photo` | ❌ | Driver profile photo |
| `license_file` | ✅ | Driving licence scan |
| `badge_file` | ✅ | Badge scan |
| `alt_govt_id_file` | ✅ | Govt ID scan (Aadhaar/PAN/etc.) |
| `bgv_file` | ✅ | Background verification document |
| `police_file` | ✅ | Police verification document |
| `medical_file` | ✅ | Medical fitness certificate |
| `training_file` | ✅ | Training completion certificate |
| `eye_file` | ✅ | Eye test certificate |
| `induction_file` | ✅ | Induction completion document |

---

## Server Configuration Requirements

### Nginx (`/etc/nginx/sites-enabled/fleet-api`)
The default Nginx body limit is **1 MB** which will cause a `413 Content Too Large` error (which browsers misreport as a CORS error).

**Must set on every VPS:**
```nginx
server {
    server_name api.mltcorporate.com;
    client_max_body_size 20M;   # ← required for driver file uploads
    ...
}
```

Template saved at: [`docs/nginx/api.mltcorporate.com.conf`](nginx/api.mltcorporate.com.conf)

Apply on a new server:
```bash
cp docs/nginx/api.mltcorporate.com.conf /etc/nginx/sites-enabled/fleet-api
nginx -t && systemctl reload nginx
```

---

## Where to Change File Size Limits

### Per-file limit (app-level)
File: [`app/routes/driver_router.py`](../app/routes/driver_router.py)

Search for:
```python
await file_size_validator(file[1], allowed_docs, 10, required=False)
```
The `10` is the max size in **MB**. Change it to whatever you need (e.g. `20` for 20 MB).

### Nginx-level (server-level)
File: `/etc/nginx/sites-enabled/fleet-api` on the server

```nginx
client_max_body_size 20M;
```
This must be **≥ the sum of all files in one request**. Since a driver creation can have up to 10 files × 10 MB each, set this to at least `20M`–`50M` depending on real-world upload sizes.

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `413 Content Too Large` | Nginx body limit too small | Set `client_max_body_size 20M` in nginx config |
| `CORS error` on driver create | Almost always a fake — caused by `413` from Nginx, not a real CORS issue | Fix the `413` first |
| `422 Unprocessable Entity` | Missing required field or invalid enum value | Check all required fields above |
| `400 Bad Request` on dates | Expiry date is in the past | All expiry dates must be future dates |
| `415 Unsupported Media Type` | Wrong file type uploaded | Only JPEG, PNG, PDF allowed |
| `413` from app (not Nginx) | File exceeds 10 MB per-file limit | Compress file or raise limit in `driver_router.py` |
