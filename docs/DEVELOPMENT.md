# Development

Back to the [README](../README.md).


## Adding New Provider with IP Rotation

```python
from ..core.base import BaseOmniProx
import random

class NewProvider(BaseOmniProx):
    def create(self) -> bool:
        # Create multiple instances for rotation
        num_proxies = getattr(self.args, 'number', 1)

        for i in range(num_proxies):
            # Deploy in different regions if possible
            region = self.get_random_region()
            proxy_url = self.deploy_to_region(region)

            # Configure header rotation
            self.setup_header_rotation(proxy_url)

    def setup_header_rotation(self, proxy_url):
        # Implement X-Forwarded-For rotation
        headers = {
            'X-Forwarded-For': self.generate_ip_chain(),
            'X-Real-IP': self.generate_random_ip(),
            'X-Original-IP': self.generate_random_ip()
        }
        # Apply to proxy configuration

    def generate_random_ip(self):
        # Use realistic IP ranges
        ranges = [
            (73, 255),   # Comcast
            (24, 255),   # Charter
            (71, 255),   # Verizon
            (35, 255),   # GCP
        ]
        base = random.choice(ranges)[0]
        return f"{base}.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}"
```


**Note**: IP rotation features are designed for legitimate use cases like web scraping with permission, API testing, and geographic testing. Do not use for malicious purposes.
