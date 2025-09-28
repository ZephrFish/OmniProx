# OmniProx Proxy Features Documentation

## Core Features Implementation Status

### 1. IP Rotation with Every Request

| Provider | True IP Rotation | Header Rotation | Implementation |
|----------|-----------------|-----------------|----------------|
| **Cloudflare** | No  | Yes  | Headers rotate on every request using `generateIP()` function |
| **Azure** | Yes * | Yes  | Each container has unique IP; headers rotate per request |
| **GCP** | No  | Yes  | Single gateway IP; headers can rotate |
| **Alibaba** | No  | Yes  | Single API IP; headers can rotate |

*Azure provides true IP rotation by using multiple containers, each with its own public IP

### 2. Configure Separate Regions

| Provider | Multi-Region Support | How to Configure |
|----------|---------------------|------------------|
| **Cloudflare** | Global | Workers deploy globally automatically |
| **Azure** | Yes  | `--region westus`, `--region eastus`, etc. |
| **GCP** | Yes  | `--region us-central1`, `--region europe-west1` |
| **Alibaba** | Yes  | `--region cn-hangzhou`, `--region cn-shanghai` |

**Usage Examples:**
```bash
# Azure - Deploy in different regions
omniprox --provider azure --command create --url https://yoururlgoeshere.local --region westus
omniprox --provider azure --command create --url https://yoururlgoeshere.local --region eastus2

# GCP - Multiple regions
omniprox --provider gcp --command create --url https://yoururlgoeshere.local --region us-central1
omniprox --provider gcp --command create --url https://yoururlgoeshere.local --region europe-west1

# Alibaba - China regions
omniprox --provider alibaba --command create --url https://yoururlgoeshere.local --region cn-hangzhou
omniprox --provider alibaba --command create --url https://yoururlgoeshere.local --region cn-beijing
```

### 3. All HTTP Methods Supported

All providers support the full range of HTTP methods:
- GET
- POST
- PUT
- DELETE
- PATCH
- HEAD
- OPTIONS

**Implementation:**
- Cloudflare: `request.method` is preserved and forwarded
- Azure: `req.method` is passed through to target
- GCP/Alibaba: API Gateway forwards all methods

### 4. All Parameters and URIs Passed Through

#### URL Format Support

**Query Parameter Format:**
```bash
curl 'https://proxy.example.com?url=https://yoururlgoeshere.local/api/endpoint?param1=value1&param2=value2'
```

**Path-Based Format (with base URL):**
```bash
# If proxy was created with --url https://api.yoururlgoeshere.local
curl 'https://proxy.example.com/v1/users/123'
# Proxies to: https://api.yoururlgoeshere.local/v1/users/123
```

**Full URL in Path:**
```bash
curl 'https://proxy.example.com/https://different-yoururlgoeshere.local/api/endpoint'
```

**Header-Based Format (Cloudflare only):**
```bash
curl -H 'X-Target-URL: https://yoururlgoeshere.local/api' https://proxy.example.com
```

#### Path Preservation

All providers now preserve the full path and query parameters:

**Cloudflare Worker:**
```javascript
// If preserving path, append request path to target URL
if (preservePath && url.pathname !== '/') {
  targetURL.pathname = targetURL.pathname.replace(/\/$/, '') + url.pathname
}
```

**Azure Container:**
```javascript
// Append path to base URL
const baseUrl = new URL(BASE_URL);
baseUrl.pathname = baseUrl.pathname.replace(/\/$/, '') + req.url;
```

### 5. Create, Delete, List, Update Proxies

| Operation | Command | All Providers |
|-----------|---------|---------------|
| **Create** | `--command create --url https://yoururlgoeshere.local` | Yes  |
| **List** | `--command list` | Yes  |
| **Delete** | `--command delete --api_id [id]` | Yes  |
| **Cleanup** | `--command cleanup` | Yes  |
| **Batch Create** | `--command create --number 5` | Yes  |

**Examples:**
```bash
# Create multiple proxies
omniprox --provider cf --command create --url https://yoururlgoeshere.local --number 10

# List all proxies
omniprox --provider azure --command list

# Delete specific proxy
omniprox --provider cf --command delete --api_id worker-123

# Cleanup all proxies
omniprox --provider azure --command cleanup
```

### 6. X-My-X-Forwarded-For Header Support

Custom IP spoofing via `X-My-X-Forwarded-For` header is now implemented in all providers:

**How it works:**
1. Client sends request with `X-My-X-Forwarded-For: 1.2.3.4`
2. Proxy reads this header
3. Proxy sets `X-Forwarded-For: 1.2.3.4` in the forwarded request
4. Target server sees the spoofed IP

**Cloudflare Implementation:**
```javascript
const customForwardedFor = request.headers.get('X-My-X-Forwarded-For')
if (customForwardedFor) {
  headers.set('X-Forwarded-For', customForwardedFor)
  headers.set('X-Real-IP', customForwardedFor.split(',')[0].trim())
}
```

**Azure Implementation:**
```javascript
if (headers['x-my-x-forwarded-for']) {
  headers['x-forwarded-for'] = headers['x-my-x-forwarded-for'];
  headers['x-real-ip'] = headers['x-my-x-forwarded-for'].split(',')[0].trim();
}
```

**Usage Example:**
```bash
# Spoof source IP
curl -H 'X-My-X-Forwarded-For: 203.0.113.45' \
     'https://proxy.workers.dev?url=https://httpbin.org/headers'

# Response will show:
# "X-Forwarded-For": "203.0.113.45"
# "X-Real-IP": "203.0.113.45"
```

## IP Rotation Strategies by Provider

### Cloudflare Workers
- **Rotation**: Headers only (X-Forwarded-For, CF-Connecting-IP)
- **Actual IP**: Static Cloudflare edge IPs (104.x.x.x, 172.x.x.x)
- **Best for**: Applications that only check headers
- **Frequency**: Every request gets different header values

### Azure Container Instances
- **Rotation**: TRUE IP rotation + headers
- **Actual IP**: Each container has unique public IP
- **Best for**: Applications that verify actual TCP source IP
- **Strategy**: Create pool of containers, round-robin between them
```bash
# Create pool of 10 containers = 10 different IPs
omniprox --provider azure --command create --url https://yoururlgoeshere.local --number 10
```

### GCP API Gateway
- **Rotation**: Headers only
- **Actual IP**: Single gateway IP per region
- **Strategy**: Deploy in multiple regions for IP diversity
```bash
# Deploy in 3 regions = 3 different IPs
omniprox --provider gcp --command create --url https://yoururlgoeshere.local --region us-central1
omniprox --provider gcp --command create --url https://yoururlgoeshere.local --region europe-west1
omniprox --provider gcp --command create --url https://yoururlgoeshere.local --region asia-east1
```

### Alibaba Cloud
- **Rotation**: Headers only
- **Actual IP**: Single API IP per region
- **Strategy**: Similar to GCP, use multiple regions

## Testing IP Rotation

### Test Headers Rotation
```bash
# Create proxy
omniprox --provider cf --command create --url https://httpbin.org

# Test rotation (run multiple times)
for i in {1..5}; do
  echo "Request $i:"
  curl -s 'https://[worker].workers.dev/headers' | grep -E "X-Forwarded-For|X-Real-IP"
  echo "---"
done
```

### Test True IP Rotation (Azure)
```bash
# Create container pool
omniprox --provider azure --command create --url https://ipinfo.io --number 5

# Each container has unique IP
omniprox --provider azure --command list
# Shows 5 containers with 5 different IPs
```

### Test Custom IP Spoofing
```bash
# Send custom X-My-X-Forwarded-For
curl -H 'X-My-X-Forwarded-For: 192.0.2.123, 198.51.100.45' \
     'https://proxy.example.com?url=https://httpbin.org/headers'

# Target sees: X-Forwarded-For: 192.0.2.123, 198.51.100.45
```

## Complete Usage Examples

### 1. Create Multi-Region Proxy Pool with IP Rotation
```bash
# Azure - True IP rotation across regions
omniprox --provider azure --command create --url https://api.yoururlgoeshere.local --region westus --number 3
omniprox --provider azure --command create --url https://api.yoururlgoeshere.local --region eastus --number 3
# Total: 6 unique IPs across 2 regions

# Cloudflare - Global edge with header rotation
omniprox --provider cf --command create --url https://api.yoururlgoeshere.local --number 5
# 5 workers, all rotating headers on each request
```

### 2. Path-Based Proxying
```bash
# Create proxy with base URL
omniprox --provider cf --command create --url https://api.github.com

# Access different endpoints - paths are preserved
curl 'https://worker.workers.dev/users/octocat'
# Proxies to: https://api.github.com/users/octocat

curl 'https://worker.workers.dev/repos/nodejs/node/issues?state=open'
# Proxies to: https://api.github.com/repos/nodejs/node/issues?state=open
```

### 3. Complete CRUD Operations
```bash
# CREATE
omniprox --provider azure --command create --url https://api.example.com --number 5 --region westus

# LIST
omniprox --provider azure --command list

# DELETE specific
omniprox --provider azure --command delete --api_id container-123

# CLEANUP all
omniprox --provider azure --command cleanup
```

### 4. Custom Headers and IP Spoofing
```bash
# Create proxy
omniprox --provider cf --command create --url https://httpbin.org

# Send request with custom IP and headers
curl -X POST \
     -H 'X-My-X-Forwarded-For: 203.0.113.99' \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer token123' \
     -d '{"key": "value"}' \
     'https://worker.workers.dev/post'
```

## Performance Characteristics

| Provider | Latency | Throughput | Cost | Best Use Case |
|----------|---------|------------|------|---------------|
| **Cloudflare** | Low (edge) | High | Free tier generous | High-volume, header-based rotation |
| **Azure** | Medium | Medium | Pay per hour | True IP rotation required |
| **GCP** | Low-Medium | High | Pay per request | Enterprise APIs |
| **Alibaba** | Low (in Asia) | High | Pay per request | China/Asia traffic |

## Security Considerations

1. **IP Rotation Limitations:**
   - Only Azure provides true TCP-level IP rotation
   - Other providers only rotate headers (application layer)
   - Smart firewalls can detect header-only rotation

2. **X-My-X-Forwarded-For Usage:**
   - Only affects `X-Forwarded-For` header
   - Does not change actual source IP
   - Some servers validate and may reject spoofed headers

3. **Rate Limiting:**
   - Rotating IPs may help with rate limits
   - But providers' IPs might be in known ranges
   - Azure containers provide most diverse IPs

4. **HTTPS Support:**
   - All providers support HTTPS targets
   - SSL/TLS is terminated at proxy and re-established
   - Certificate validation is performed

## Troubleshooting

### Path not being preserved
- Ensure you're using the latest version
- Check if base URL was set during creation: `--url https://base.url`
- Try explicit path format: `/path/to/resource`

### IP not rotating
- Cloudflare/GCP/Alibaba: Only headers rotate, not actual IP
- Azure: Ensure multiple containers are created with `--number`
- Check response headers for `X-Forwarded-For` changes

### X-My-X-Forwarded-For not working
- Ensure header name is exactly `X-My-X-Forwarded-For`
- Check if target server accepts `X-Forwarded-For`
- Some servers have IP validation that may reject spoofed IPs

### Regional deployment issues
- Azure: Check region name (use `az account list-locations`)
- GCP: Ensure region is valid (use `gcloud compute regions list`)
- Alibaba: Use China regions (cn-hangzhou, cn-shanghai, etc.)
