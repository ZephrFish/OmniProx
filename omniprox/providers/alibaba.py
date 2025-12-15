#!/usr/bin/env python3
"""
Alibaba Cloud API Gateway provider for OmniProx
Provides API proxy capabilities through Alibaba Cloud
"""

import os
import sys
import json
import time
import random
import string
import logging
import configparser
from typing import Dict, List, Optional, Any
from omniprox.core.base import BaseOmniProx

class AlibabaProvider(BaseOmniProx):
    """Alibaba Cloud API Gateway provider"""

    def __init__(self, args: Any):
        """Initialize Alibaba provider"""
        self.access_key_id = None
        self.access_key_secret = None
        self.region_id = 'cn-hangzhou'
        self.api_client = None
        super().__init__('alibaba', args)

    def create_profile(self, config: configparser.ConfigParser, profile_name: str):
        """Create a new Alibaba profile"""
        config[profile_name] = {}

        print("\nAlibaba Cloud API Gateway Configuration")
        print("-" * 40)

        config[profile_name]['access_key_id'] = input("Access Key ID: ").strip()
        config[profile_name]['access_key_secret'] = input("Access Key Secret: ").strip()
        config[profile_name]['region_id'] = input("Region ID [cn-hangzhou]: ").strip() or 'cn-hangzhou'

        self.save_profile(config)
        self.load_profile(config, profile_name)

    def load_profile(self, config: configparser.ConfigParser, profile_name: str):
        """Load Alibaba profile"""
        if profile_name in config:
            profile = config[profile_name]
            self.access_key_id = profile.get('access_key_id')
            self.access_key_secret = profile.get('access_key_secret')
            # Override region with command line argument if provided
            if hasattr(self.args, 'region') and self.args.region:
                self.region_id = self.args.region
            else:
                self.region_id = profile.get('region_id', 'cn-hangzhou')
            self.logger.info(f"Loaded Alibaba profile '{profile_name}'")
            self.logger.debug(f"Alibaba credentials loaded for region: {self.region_id}")

    def init_provider(self) -> bool:
        """Initialize Alibaba Cloud SDK"""
        try:
            from alibabacloud_cloudapi20160714.client import Client
            from alibabacloud_tea_openapi import models as open_api_models

            self.logger.debug("Initializing Alibaba Cloud API client")
            config = open_api_models.Config(
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret,
                region_id=self.region_id
            )
            # Use correct endpoint format
            config.endpoint = f'apigateway.{self.region_id}.aliyuncs.com'

            self.api_client = Client(config)
            return True

        except ImportError:
            print("[ERROR] Alibaba Cloud SDK not installed.")
            print("Run: pip install alibabacloud-cloudapi20160714 alibabacloud-tea-openapi")
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Alibaba API Gateway: {e}")
            return False

    def create(self) -> bool:
        """Create Alibaba API Gateway proxy"""
        if not self.require_url():
            return False

        if not self.init_provider():
            return False

        try:
            from alibabacloud_cloudapi20160714 import models as cloudapi_models
            from alibabacloud_tea_util import models as util_models
            from urllib.parse import urlparse

            parsed_url = urlparse(self.url)
            backend_host = parsed_url.netloc
            backend_path = parsed_url.path if parsed_url.path else "/"
            # Alibaba only supports HTTP protocol in ServiceConfig
            backend_protocol = "HTTP"
            # But the address should include the correct protocol
            backend_address = f"{parsed_url.scheme}://{backend_host}"

            # Generate unique names
            suffix = f"{int(time.time())}-{''.join(random.choices(string.ascii_lowercase, k=6))}"
            group_name = f"omniprox-group-{suffix}"
            api_name = f"omniprox-api-{suffix}"

            print(f"\nCreating Alibaba API Gateway for: {self.url}")
            print(f"Region: {self.region_id}")

            # 1. Create API Group
            print("Creating API Group...")
            create_group_request = cloudapi_models.CreateApiGroupRequest(
                group_name=group_name,
                description=f"OmniProx API Group for {backend_host}"
            )

            runtime = util_models.RuntimeOptions()
            group_response = self.api_client.create_api_group_with_options(
                create_group_request,
                runtime
            )

            group_id = group_response.body.group_id
            subdomain = group_response.body.sub_domain

            # 2. Create API
            print(f"Creating API in group {group_id}...")

            # Enhanced API configuration for better POST and path support
            api_config = {
                "ServiceConfig": {
                    "ServiceProtocol": backend_protocol,
                    "ServiceAddress": backend_address,
                    "ServicePath": backend_path if backend_path else "/",
                    "ServiceHttpMethod": "ANY",  # Support all HTTP methods
                    "ServiceTimeout": 60000,  # Increase timeout for POST operations
                    "ContentTypeCatagory": "DEFAULT",  # Auto-detect content type
                    "ContentTypeValue": "application/json;charset=utf-8"
                },
                "RequestConfig": {
                    "RequestProtocol": "HTTP,HTTPS",
                    "RequestHttpMethod": "ANY",  # Accept all methods
                    "RequestPath": "/*",  # Match all paths
                    "RequestMode": "PASSTHROUGH"  # Pass through all data
                },
                "RequestParameters": [],
                "ServiceParameters": [],
                "ServiceParametersMap": [],
                "ResultType": "PASSTHROUGH",  # Pass through response as-is
                "ResultSample": "{\"status\":\"success\"}",
                "FailResultSample": "{\"error\":\"proxy failed\"}"
            }

            create_api_request = cloudapi_models.CreateApiRequest(
                group_id=group_id,
                api_name=api_name,
                description=f"OmniProx API for {backend_host}",
                visibility="PUBLIC",  # Make it public for immediate use
                auth_type="ANONYMOUS",
                request_config=json.dumps(api_config["RequestConfig"]),
                service_config=json.dumps(api_config["ServiceConfig"]),
                result_type=api_config["ResultType"],
                result_sample=api_config["ResultSample"],
                fail_result_sample=api_config["FailResultSample"]
            )

            api_response = self.api_client.create_api_with_options(
                create_api_request,
                runtime
            )

            api_id = api_response.body.api_id

            # 3. Deploy API
            print(f"Deploying API {api_id}...")
            deploy_request = cloudapi_models.DeployApiRequest(
                api_id=api_id,
                group_id=group_id,
                stage_name="RELEASE",
                description="OmniProx API deployment"
            )

            self.api_client.deploy_api_with_options(
                deploy_request,
                runtime
            )

            proxy_url = f"https://{subdomain}"

            # Store in profile
            if not hasattr(self, 'apis'):
                self.apis = []
            self.apis.append({
                'group_id': group_id,
                'api_id': api_id,
                'proxy_url': proxy_url,
                'target': self.url
            })

            print("\n" + "="*60)
            print("ALIBABA API GATEWAY CREATED SUCCESSFULLY")
            print("="*60)
            print(f"\nAPI Group ID: {group_id}")
            print(f"API ID: {api_id}")
            print(f"Proxy URL: {proxy_url}")
            print(f"Target: {self.url}")
            print(f"Region: {self.region_id}")
            print(f"Visibility: PUBLIC (No authentication required)")
            print("\nUsage:")
            print(f"  curl {proxy_url}/[path]")
            print(f"  curl {proxy_url}/ip  # Example for httpbin.org/ip")

            return True

        except Exception as e:
            self.logger.error(f"Failed to create API Gateway: {e}")
            print(f"[ERROR] Failed to create API Gateway: {e}")
            return False

    def list(self) -> bool:
        """List all Alibaba API Gateways"""
        self.logger.debug("Listing Alibaba API Gateways")
        if not self.init_provider():
            return False

        try:
            from alibabacloud_cloudapi20160714 import models as cloudapi_models
            from alibabacloud_tea_util import models as util_models

            print(f"\nListing Alibaba API Gateways in region {self.region_id}...")
            print("-" * 60)

            # List API Groups
            list_groups_request = cloudapi_models.DescribeApiGroupsRequest(
                page_size=50,
                page_number=1
            )

            runtime = util_models.RuntimeOptions()
            groups_response = self.api_client.describe_api_groups_with_options(
                list_groups_request,
                runtime
            )

            count = 0
            if groups_response.body.api_group_attributes and groups_response.body.api_group_attributes.api_group_attribute:
                for group in groups_response.body.api_group_attributes.api_group_attribute:
                    if 'omniprox' in group.group_name.lower():
                        count += 1
                        print(f"\nAPI Group: {group.group_name}")
                        print(f"  Group ID: {group.group_id}")
                        print(f"  Subdomain: {group.sub_domain}")
                        print(f"  Created: {group.created_time}")
                        print(f"  Region: {group.region_id}")

                        # List APIs in this group
                        try:
                            list_apis_request = cloudapi_models.DescribeApisRequest(
                                group_id=group.group_id,
                                page_size=50,
                                page_number=1
                            )

                            apis_response = self.api_client.describe_apis_with_options(
                                list_apis_request,
                                runtime
                            )

                            if hasattr(apis_response.body, 'api_summarys') and apis_response.body.api_summarys:
                                for api in apis_response.body.api_summarys.api_summary:
                                    print(f"  API: {api.api_name} (ID: {api.api_id})")
                                    print(f"    Stage: {api.stage_name if hasattr(api, 'stage_name') else 'N/A'}")
                                    print(f"    Visibility: {api.visibility}")

                        except Exception as e:
                            self.logger.debug(f"Could not list APIs in group: {e}")

            if count == 0:
                print("\nNo OmniProx API Gateways found")
            else:
                print(f"\n\nTotal OmniProx API Groups: {count}")

            return True

        except Exception as e:
            import traceback
            self.logger.error(f"Failed to list API Gateways: {e}")
            self.logger.debug(f"Stack trace: {traceback.format_exc()}")
            print(f"[ERROR] Failed to list: {e}")
            return False

    def _delete_api_only(self, api_id: str, group_id: str) -> bool:
        """Delete only the API without attempting to delete the group"""
        if not self.init_provider():
            return False

        try:
            from alibabacloud_cloudapi20160714 import models as cloudapi_models
            from alibabacloud_tea_util import models as util_models

            runtime = util_models.RuntimeOptions()

            # 1. Undeploy API from all stages
            try:
                for stage in ['RELEASE', 'TEST', 'PRE']:
                    abolish_request = cloudapi_models.AbolishApiRequest(
                        api_id=api_id,
                        group_id=group_id,
                        stage_name=stage
                    )
                    self.api_client.abolish_api_with_options(
                        abolish_request,
                        runtime
                    )
            except Exception as e:
                # API might not be deployed to all stages
                self.logger.debug(f"Could not undeploy from all stages: {e}")

            # 2. Delete API
            delete_api_request = cloudapi_models.DeleteApiRequest(
                api_id=api_id,
                group_id=group_id
            )

            self.api_client.delete_api_with_options(
                delete_api_request,
                runtime
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to delete API: {e}")
            return False

    def delete(self, api_id: str = None, group_id: Optional[str] = None) -> bool:
        """Delete a specific API Gateway"""
        if not self.init_provider():
            return False

        try:
            from alibabacloud_cloudapi20160714 import models as cloudapi_models
            from alibabacloud_tea_util import models as util_models

            runtime = util_models.RuntimeOptions()

            # If group_id not provided, try to find it
            if not group_id:
                # Get API details to find group
                describe_api_request = cloudapi_models.DescribeApiRequest(
                    api_id=api_id
                )
                api_response = self.api_client.describe_api_with_options(
                    describe_api_request,
                    runtime
                )
                group_id = api_response.body.group_id

            print(f"Deleting API {api_id}...")

            # 1. Undeploy API from all stages
            try:
                for stage in ['RELEASE', 'TEST', 'PRE']:
                    abolish_request = cloudapi_models.AbolishApiRequest(
                        api_id=api_id,
                        group_id=group_id,
                        stage_name=stage
                    )
                    self.api_client.abolish_api_with_options(
                        abolish_request,
                        runtime
                    )
            except Exception as e:
                # API might not be deployed to all stages
                self.logger.debug(f"Could not undeploy from all stages: {e}")

            # 2. Delete API
            delete_api_request = cloudapi_models.DeleteApiRequest(
                api_id=api_id,
                group_id=group_id
            )

            self.api_client.delete_api_with_options(
                delete_api_request,
                runtime
            )

            print(f"  [OK] Deleted API: {api_id}")

            # 3. Try to delete group if empty
            try:
                delete_group_request = cloudapi_models.DeleteApiGroupRequest(
                    group_id=group_id
                )
                self.api_client.delete_api_group_with_options(
                    delete_group_request,
                    runtime
                )
                print(f"  [OK] Deleted API Group: {group_id}")
            except Exception as e:
                self.logger.debug(f"Could not delete group {group_id}: {e}")
                print(f"  [INFO] API Group {group_id} still has other APIs")

            return True

        except Exception as e:
            self.logger.error(f"Failed to delete API Gateway: {e}")
            print(f"[ERROR] Failed to delete: {e}")
            return False

    def cleanup(self) -> bool:
        """Clean up all OmniProx API Gateways"""
        if not self.init_provider():
            return False

        try:
            from alibabacloud_cloudapi20160714 import models as cloudapi_models
            from alibabacloud_tea_util import models as util_models

            print("\nFinding all OmniProx API Gateways...")

            runtime = util_models.RuntimeOptions()

            # List all API Groups
            list_groups_request = cloudapi_models.DescribeApiGroupsRequest(
                page_size=50,
                page_number=1
            )

            groups_response = self.api_client.describe_api_groups_with_options(
                list_groups_request,
                runtime
            )

            omniprox_groups = []
            for group in groups_response.body.api_group_attributes.api_group_attribute:
                if 'omniprox' in group.group_name.lower():
                    omniprox_groups.append({
                        'group_id': group.group_id,
                        'group_name': group.group_name
                    })

            if not omniprox_groups:
                print("No OmniProx API Gateways to clean up")
                return True

            print(f"Found {len(omniprox_groups)} OmniProx API Group(s)")

            # Check if running in non-interactive mode
            import sys
            if not sys.stdin.isatty():
                confirm = "yes"  # Auto-confirm in non-interactive mode
            else:
                confirm = input("Delete all OmniProx API Gateways? (yes/no): ").strip().lower()

            if confirm != 'yes':
                print("Cleanup cancelled")
                return False

            for group in omniprox_groups:
                print(f"\nDeleting group {group['group_name']}...")

                # List all APIs in group
                list_apis_request = cloudapi_models.DescribeApisRequest(
                    group_id=group['group_id'],
                    page_size=50,
                    page_number=1
                )

                apis_response = self.api_client.describe_apis_with_options(
                    list_apis_request,
                    runtime
                )

                # Delete all APIs (without trying to delete group after each one)
                deleted_apis = 0
                if hasattr(apis_response.body, 'api_summarys') and apis_response.body.api_summarys:
                    for api in apis_response.body.api_summarys.api_summary:
                        # Call delete but suppress group deletion attempts
                        if self._delete_api_only(api.api_id, group['group_id']):
                            deleted_apis += 1
                            print(f"  [OK] Deleted API: {api.api_name}")

                # Now delete the group after all APIs are removed
                try:
                    delete_group_request = cloudapi_models.DeleteApiGroupRequest(
                        group_id=group['group_id']
                    )
                    self.api_client.delete_api_group_with_options(
                        delete_group_request,
                        runtime
                    )
                    print(f"  [OK] Deleted group {group['group_name']} (contained {deleted_apis} APIs)")
                except Exception as e:
                    # Group might already be deleted or have dependencies
                    self.logger.debug(f"Could not delete group: {e}")

            print(f"\n[OK] Cleanup completed")
            return True

        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
            print(f"[ERROR] Cleanup failed: {e}")
            return False