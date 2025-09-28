# Provider Feature Comparison

## Feature Support Matrix

| Feature | Cloudflare | Azure | GCP | Alibaba |
|---------|------------|-------|-----|---------|
| **IP Rotation Every Request** | Yes Headers only | Yes TRUE IP (multiple containers) | Warning Limited* | Warning Limited* |
| **Configure Regions** | Yes Global edge | Yes `--region` flag | Yes `--region` flag | Yes `--region` flag |
| **All HTTP Methods** | Yes Full support | Yes Full support | Warning API Gateway limited** | Warning API Gateway limited** |
| **Path Preservation** | Yes Implemented | Yes Implemented | No Not implemented*** | No Not implemented*** |
| **Query Param Passthrough** | Yes Yes | Yes Yes | Warning Limited | Warning Limited |
| **X-My-X-Forwarded-For** | Yes Implemented | Yes Implemented | No Not implemented | No Not implemented |
| **Dynamic URL Routing** | Yes Yes | Yes Yes | No No (static backend) | No No (static backend) |
| **Create/Delete/List** | Yes Yes | Yes Yes | Yes Yes | Yes Yes |
| **Batch Creation** | Yes Yes | Yes Yes | Yes Yes | Yes Yes |

### Legend:
- Yes **Fully Implemented and Working**
- Warning **Partially Supported**
- No **Not Implemented/Not Possible**

## Detailed Provider Analysis

### Yes Cloudflare Workers - FULLY FUNCTIONAL
**Status**: All features implemented and tested

**Working Features:**
- IP header rotation on every request
- Path preservation (`/path` → `baseurl/path`)
- All URL formats (query, path, header-based)
- X-My-X-Forwarded-For custom headers
- All HTTP methods
- Dynamic URL routing

**Implementation Details:**
```javascript
// Path preservation
if (preservePath && url.pathname !== '/') {
  targetURL.pathname = targetURL.pathname.replace(/\/$/, '') + url.pathname
}

// Custom IP headers
const customForwardedFor = request.headers.get('X-My-X-Forwarded-For')
if (customForwardedFor) {
  headers.set('X-Forwarded-For', customForwardedFor)
}
```

### Yes Azure Container Instances - FULLY FUNCTIONAL
**Status**: All features implemented and tested

**Working Features:**
- TRUE IP rotation (each container has unique public IP)
- Path preservation
- All URL formats
- X-My-X-Forwarded-For custom headers
- All HTTP methods
- Regional deployment with `--region`

**Implementation Details:**
```javascript
// Running Node.js proxy in containers
// Path preservation
const baseUrl = new URL(BASE_URL);
baseUrl.pathname = baseUrl.pathname.replace(/\/$/, '') + req.url;

// Custom headers
if (headers['x-my-x-forwarded-for']) {
  headers['x-forwarded-for'] = headers['x-my-x-forwarded-for'];
}
```

### Warning GCP API Gateway - LIMITED FUNCTIONALITY
**Status**: Basic proxy works but with significant limitations

**Limitations:**
- *Static backend URL defined in OpenAPI spec
- **API Gateway supports methods defined in OpenAPI spec only
- ***No dynamic path routing (paths must be predefined)
- No X-My-X-Forwarded-For support
- Cannot dynamically change target URLs

**Current Implementation:**
```yaml
# OpenAPI spec with static backend
x-google-backend:
  address: https://yoururlgoeshere.local  # Static, cannot change per request
paths:
  /**:  # Limited wildcard support
    get:
      operationId: proxy_get
```

**Why Limited:**
- GCP API Gateway is designed for API management, not general proxying
- Requires OpenAPI specification with predefined routes
- Backend URL is fixed at deployment time
- No request modification capabilities

### Warning Alibaba Cloud API Gateway - LIMITED FUNCTIONALITY
**Status**: Basic proxy works but with significant limitations

**Limitations:**
- Similar to GCP - static backend configuration
- API-based routing, not true proxying
- No dynamic URL routing
- No custom header manipulation
- Regional limitations (mainly China)

**Current Implementation:**
- Creates API Gateway instances
- Routes to predefined backend
- Limited path flexibility

## Recommendations by Use Case

### For Full Feature Support (All Requirements Met):
**Use: Cloudflare Workers or Azure Containers**

```bash
# Cloudflare - Best for header rotation, global edge
omniprox --provider cf --command create --url https://yoururlgoeshere.local --number 5

# Azure - Best for TRUE IP rotation
omniprox --provider azure --command create --url https://yoururlgoeshere.local --number 5 --region westus
```

### For True IP Rotation:
**Use: Azure Containers Only**

```bash
# Create pool with unique IPs
omniprox --provider azure --command create --url https://yoururlgoeshere.local --number 10
```

### For Global Edge Network:
**Use: Cloudflare Workers**

```bash
# Deploys globally automatically
omniprox --provider cf --command create --url https://yoururlgoeshere.local
```

### For China/Asia Traffic:
**Use: Alibaba (with limitations)**

```bash
# Basic API Gateway proxy (no dynamic routing)
omniprox --provider alibaba --command create --url https://yoururlgoeshere.local --region cn-hangzhou
```

## Implementation Status Summary

### Fully Working Providers (All Features):
1. **Cloudflare Workers** - 100% feature complete
2. **Azure Container Instances** - 100% feature complete

### Limited Providers (Basic Proxy Only):
3. **GCP API Gateway** - ~40% features (static routing only)
4. **Alibaba Cloud** - ~40% features (static routing only)

## Why GCP and Alibaba Are Limited

Both GCP and Alibaba use **API Gateway** services which are fundamentally different from compute-based proxies:

### API Gateway Limitations:
1. **Static Configuration**: Backend URLs defined at deployment
2. **No Request Modification**: Cannot modify headers dynamically
3. **Path Restrictions**: Routes must be predefined in API spec
4. **No True Proxying**: Designed for API management, not proxying

### Compute-Based Advantages (Cloudflare/Azure):
1. **Dynamic Routing**: Can change target URL per request
2. **Full Request Control**: Modify any headers/body
3. **Path Flexibility**: Any path can be forwarded
4. **True Proxying**: Acts as transparent HTTP proxy

## Migration Path for GCP/Alibaba

To achieve full feature parity, GCP and Alibaba would need to use compute services instead:

### GCP Alternative:
- Use **Cloud Run** or **Cloud Functions** instead of API Gateway
- Deploy Node.js/Python proxy application
- Similar to Azure container approach

### Alibaba Alternative:
- Use **Function Compute** or **ECS** instead of API Gateway
- Deploy proxy application
- Would provide full feature support

## Conclusion

**Only Cloudflare Workers and Azure Container Instances** currently support all requested features:
- Yes IP rotation every request
- Yes Configure separate regions
- Yes All HTTP methods supported
- Yes All parameters and URIs passed through
- Yes X-My-X-Forwarded-For header support
- Yes Dynamic URL routing

**GCP and Alibaba** are limited to basic static proxy functionality due to API Gateway architecture constraints. For full feature support, use Cloudflare or Azure.
