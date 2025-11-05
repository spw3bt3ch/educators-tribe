# File Uploads on Vercel - Complete Guide

## Overview

This document explains what file types can be uploaded on Vercel and what alternatives are available if ImageKit cannot handle the upload.

## File Types Supported

Your application currently supports uploading the following file types:

### Documents
- **PDF** (`.pdf`) - Portable Document Format
- **DOC** (`.doc`) - Microsoft Word (legacy)
- **DOCX** (`.docx`) - Microsoft Word (modern)
- **TXT** (`.txt`) - Plain text files

### Spreadsheets
- **CSV** (`.csv`) - Comma-separated values
- **XLS** (`.xls`) - Microsoft Excel (legacy)
- **XLSX** (`.xlsx`) - Microsoft Excel (modern)

### Presentations
- **PPT** (`.ppt`) - Microsoft PowerPoint (legacy)
- **PPTX** (`.pptx`) - Microsoft PowerPoint (modern)

### Images
- **JPG/JPEG** (`.jpg`, `.jpeg`) - JPEG images
- **PNG** (`.png`) - PNG images
- **GIF** (`.gif`) - GIF images

### Archives
- **ZIP** (`.zip`) - ZIP archives
- **RAR** (`.rar`) - RAR archives

## Current Implementation

### How It Works
1. **Serverless Function Receives File**: Vercel serverless functions can accept file uploads via multipart/form-data (up to 4.5MB payload limit)
2. **ImageKit Upload**: File is uploaded from the serverless function to ImageKit cloud storage
3. **Database Storage**: Only the ImageKit URL is stored in PostgreSQL database (Render)
4. **File Delivery**: Files are served via ImageKit's CDN

### Limitations on Vercel

#### 1. **File Size Limits**
- **Vercel Function Payload**: Maximum 4.5MB for serverless functions
- **ImageKit Free Tier**: Maximum 10MB per file
- **Current App Limit**: 10MB (enforced in code)

#### 2. **Ephemeral Filesystem**
- Files saved to `/tmp` are deleted when the function completes
- Local file storage **will not work** on Vercel
- All files must be uploaded to external cloud storage

#### 3. **Function Timeout**
- **Hobby Plan**: 10 seconds
- **Pro Plan**: 60 seconds
- Large files may timeout during upload

## What Happens If ImageKit Fails?

### Current Behavior
If ImageKit fails, the upload will fail with an error message. The admin will see:
- "Failed to upload file to cloud storage. Possible reasons: Network error, file size too large, or ImageKit service issue."

### Alternative Storage Options

If ImageKit cannot handle uploads, you can implement alternative cloud storage services:

#### Option 1: AWS S3 / S3-Compatible Storage ⭐ **Recommended**
**Services**: AWS S3, Cloudflare R2, DigitalOcean Spaces, Wasabi

**Pros**:
- Reliable and scalable
- Low cost (Cloudflare R2 has no egress fees)
- S3-compatible API (works with boto3)
- Supports files up to 5TB

**Implementation**:
```python
import boto3
from botocore.exceptions import ClientError

def upload_to_s3(file_file, bucket_name, folder='materials'):
    s3_client = boto3.client('s3',
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
    )
    
    file_content = file_file.read()
    unique_filename = f"{folder}/{timestamp}_{filename}"
    
    try:
        s3_client.upload_fileobj(file_file, bucket_name, unique_filename)
        return f"https://{bucket_name}.s3.amazonaws.com/{unique_filename}"
    except ClientError as e:
        print(f"S3 upload error: {e}")
        return None
```

**Environment Variables Needed**:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_BUCKET_NAME`
- `AWS_REGION` (optional)

#### Option 2: Google Cloud Storage
**Pros**:
- Integrated with Google Cloud Platform
- Good for existing GCP users
- Reliable and fast

**Implementation**:
```python
from google.cloud import storage

def upload_to_gcs(file_file, bucket_name, folder='materials'):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    
    unique_filename = f"{folder}/{timestamp}_{filename}"
    blob = bucket.blob(unique_filename)
    
    file_content = file_file.read()
    blob.upload_from_string(file_content)
    
    return blob.public_url
```

**Environment Variables Needed**:
- `GOOGLE_APPLICATION_CREDENTIALS` (JSON key file path)
- `GCS_BUCKET_NAME`

#### Option 3: Azure Blob Storage
**Pros**:
- Integrated with Microsoft Azure
- Good for existing Azure users

**Implementation**:
```python
from azure.storage.blob import BlobServiceClient

def upload_to_azure(file_file, container_name, folder='materials'):
    blob_service = BlobServiceClient.from_connection_string(
        os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    )
    
    unique_filename = f"{folder}/{timestamp}_{filename}"
    blob_client = blob_service.get_blob_client(
        container=container_name, 
        blob=unique_filename
    )
    
    file_content = file_file.read()
    blob_client.upload_blob(file_content)
    
    return blob_client.url
```

**Environment Variables Needed**:
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_STORAGE_CONTAINER_NAME`

#### Option 4: Supabase Storage
**Pros**:
- Free tier available
- Easy to set up
- Built-in CDN

**Implementation**:
```python
from supabase import create_client

def upload_to_supabase(file_file, bucket_name, folder='materials'):
    supabase = create_client(
        os.environ.get('SUPABASE_URL'),
        os.environ.get('SUPABASE_KEY')
    )
    
    unique_filename = f"{folder}/{timestamp}_{filename}"
    file_content = file_file.read()
    
    response = supabase.storage.from_(bucket_name).upload(
        unique_filename,
        file_content
    )
    
    # Get public URL
    url = supabase.storage.from_(bucket_name).get_public_url(unique_filename)
    return url
```

**Environment Variables Needed**:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_STORAGE_BUCKET`

#### Option 5: Direct Client-Side Upload to ImageKit ⭐ **Best for Large Files**
**Pros**:
- Bypasses Vercel 4.5MB payload limit
- Files upload directly from browser to ImageKit
- No serverless function timeout issues
- Can handle files up to ImageKit's limit (10MB free tier)

**Implementation**:
1. Get authentication token from server
2. Use ImageKit JavaScript SDK in browser
3. Upload directly from client to ImageKit
4. Send the ImageKit URL back to server to save in database

**Frontend Code**:
```javascript
// Get auth token from server
const response = await fetch('/api/imagekit-auth');
const { token, signature, expire, fileId } = await response.json();

// Use ImageKit JS SDK
const imagekit = new ImageKit({
    publicKey: 'YOUR_PUBLIC_KEY',
    urlEndpoint: 'YOUR_URL_ENDPOINT',
    authenticationEndpoint: '/api/imagekit-auth'
});

// Upload file
const upload = await imagekit.upload({
    file: fileInput.files[0],
    fileName: uniqueFilename,
    folder: 'materials',
    token: token,
    signature: signature,
    expire: expire,
    useUniqueFileName: false
});

// Send URL to server
await fetch('/admin/materials/save', {
    method: 'POST',
    body: JSON.stringify({ file_url: upload.url, ...otherData })
});
```

**Backend Route** (to generate auth token):
```python
@app.route('/api/imagekit-auth')
@admin_required
def imagekit_auth():
    if not imagekit:
        return jsonify({'error': 'ImageKit not configured'}), 500
    
    token = imagekit.get_authentication_parameter()
    return jsonify(token)
```

## Recommendations

### For Current Setup (Small Files < 4.5MB)
✅ **Keep using server-side ImageKit upload** - Works perfectly for files under 4.5MB

### For Large Files (4.5MB - 10MB)
⭐ **Implement client-side ImageKit upload** - Best solution to bypass Vercel limits

### If ImageKit Service is Unavailable
1. **Short-term**: Add AWS S3 or Cloudflare R2 as fallback
2. **Long-term**: Implement multiple storage providers with automatic failover

## File Size Recommendations

| File Type | Recommended Max Size | Reason |
|-----------|---------------------|---------|
| Documents (PDF, DOCX) | 5MB | Maintains good performance |
| Images (JPG, PNG) | 2MB | Optimized for web viewing |
| Spreadsheets (XLSX, CSV) | 3MB | Sufficient for most data |
| Archives (ZIP, RAR) | 10MB | Current limit |
| Presentations (PPTX) | 8MB | May contain embedded media |

## Testing Upload Functionality

1. **Small File Test** (< 1MB): Should work with current setup
2. **Medium File Test** (1-4MB): Should work, may be slow
3. **Large File Test** (4-10MB): May fail - implement client-side upload
4. **Oversized Test** (> 10MB): Will fail - implement chunked upload or alternative storage

## Troubleshooting

### "Failed to upload file" Error

1. **Check ImageKit Configuration**:
   - Verify `IMAGEKIT_PRIVATE_KEY` is set in Vercel
   - Verify `IMAGEKIT_PUBLIC_KEY` is set in Vercel
   - Verify `IMAGEKIT_URL_ENDPOINT` is set in Vercel

2. **Check File Size**:
   - Ensure file is under 10MB
   - For files > 4.5MB, consider client-side upload

3. **Check Network**:
   - ImageKit service may be temporarily unavailable
   - Check ImageKit status page

4. **Check Logs**:
   - View Vercel function logs for detailed error messages
   - Check ImageKit dashboard for upload errors

## Summary

✅ **Vercel CAN accept file uploads** - but with limitations:
- Files must be under 4.5MB to go through serverless functions
- Files are uploaded to external storage (ImageKit, S3, etc.)
- Local file storage does NOT work on Vercel

✅ **ImageKit is currently the best option** for this setup:
- Works well with Vercel
- Handles multiple file types
- Free tier: 10MB per file

✅ **If ImageKit fails**, alternatives include:
- AWS S3 / Cloudflare R2 (recommended)
- Direct client-side upload to ImageKit (for large files)
- Google Cloud Storage
- Azure Blob Storage
- Supabase Storage
