# OmniProx

OmniProx is a multi-cloud HTTP proxy manager. It deploys throwaway proxies on cloud
provider free tiers and gives you one CLI to create, list and tear them down, with IP or
header rotation depending on what the provider allows.

> [!IMPORTANT]
> Tested on Linux and macOS. **Windows users should use WSL** with Ubuntu 22.04 or later.
> Native Windows installs hit encoding issues, particularly in the Azure provider. See
> [docs/INSTALL.md](docs/INSTALL.md).

## Modules

| Module | `--provider` | Rotation | Free tier | Setup |
|--------|--------------|----------|-----------|-------|
| Cloudflare Workers | `cloudflare`, `cf` | Headers only, rotates per request | 100,000 req/day, permanent | [guide](docs/PROVIDERS.md#1-cloudflare-workers-setup) |
| Azure Container Instances | `azure`, `az` | True, one public IP per container | $200 credit, 30 days | [guide](docs/PROVIDERS.md#2-azure-container-instances-setup) |
| GCP API Gateway | `gcp` | Headers, plus multiple regions | $300 credit, 90 days | [guide](docs/PROVIDERS.md#3-google-cloud-platform-setup) |
| Alibaba API Gateway | `alibaba` | Headers, plus multiple regions | None | [guide](docs/PROVIDERS.md#4-alibaba-cloud-setup) |

Cloudflare is the default provider, so `--provider` is optional when that is what you want.
Azure is the only module that gives the target a genuinely different source IP.

## Quick start

```bash
pipx install git+https://github.com/ZephrFish/OmniProx.git
```

Then authenticate one module. For Cloudflare that is Cloudflare's own CLI, which OmniProx
reads at runtime so no token is stored anywhere:

```bash
npm install -g cf
cf auth login
```

Other modules, and the API token route for Cloudflare, are in
[docs/PROVIDERS.md](docs/PROVIDERS.md). Other install options are in
[docs/INSTALL.md](docs/INSTALL.md).

## Usage

```bash
omni create https://api.example.com                      # one Cloudflare worker
omni create https://api.example.com --number 10          # ten, for header rotation
omni create https://api.example.com -p azure -n 5        # five containers, five IPs
omni list                                                # list this provider's proxies
omni list --all                                          # every configured provider
omni delete api-1792955597-gzpfkx                        # delete one
omni cleanup --all                                       # delete everything
omni proxytest                                           # check rotation end to end
```

`omni` is the short form. `omniprox` takes the same work as explicit flags
(`omniprox --command create --url ... --provider cf`) and `omniprox --help` lists them all.

Requests go through a created proxy in any of three ways:

```bash
curl 'https://<worker>.workers.dev?url=https://api.example.com'
curl -H 'X-Target-URL: https://api.example.com' https://<worker>.workers.dev
curl https://<worker>.workers.dev/https://api.example.com
```

Clean up when you are done. Azure containers bill by the second.

## Configuration

Credentials are read in this order, so nothing has to be written to disk:

1. Environment variables, for example `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`
2. `~/.omniprox/profiles.ini`, written by `omniprox --setup`
3. The provider's own CLI login (`cf` for Cloudflare, `az` for Azure, `gcloud` for GCP)

`--profile <name>` selects a profile for multiple accounts of the same provider.

## Documentation

| Document | Contents |
|----------|----------|
| [docs/INSTALL.md](docs/INSTALL.md) | pipx, clone, virtualenv, updating, WSL, troubleshooting |
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Per-module setup, credentials, costs, what the target sees |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Rotation strategies, testing rotation, OPSEC, cost control |
| [docs/PROXY_FEATURES.md](docs/PROXY_FEATURES.md) | Proxy behaviour and header handling in detail |
| [docs/PROVIDER_FEATURE_COMPARISON.md](docs/PROVIDER_FEATURE_COMPARISON.md) | Feature matrix across modules |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Adding a provider module |

## Example output

<img width="646" height="520" alt="Creating proxies" src="https://github.com/user-attachments/assets/79320c7c-9aeb-455f-930d-a4e822f9e965" />

<img width="750" height="643" alt="Listing proxies" src="https://github.com/user-attachments/assets/f8288e89-51c3-4731-b052-a196086e7377" />

<img width="534" height="679" alt="Rotation test" src="https://github.com/user-attachments/assets/e39959ef-dbd3-40e2-8712-1106ab66f8b2" />

## Licence

GPL-3.0, see [LICENSE](LICENSE).

Rotation features are for work you are authorised to do: scraping with permission, API
testing, geographic testing. Not for malicious use.
