"""
OmniProx CLI - Command-line interface for multi-cloud HTTP proxy manager
"""

import argparse
import os
import sys
from typing import Optional

from omniprox.core.utils import setup_logging, check_provider_availability, print_provider_status


def select_provider_interactive():
    """Interactive provider selection"""
    print("\n" + "="*60)
    print("Select Cloud Provider")
    print("="*60)
    print("Which cloud provider would you like to use?")
    print("  1. Cloudflare Workers (cf) - Best for IP rotation, 100k req/day free")
    print("  2. Google Cloud Platform (gcp) - 2M req/month free")
    print("  3. Microsoft Azure (az) - Container Instances with IP rotation")
    print("  4. Exit")

    while True:
        try:
            choice = input("\nSelect option (1-5): ").strip()

            if choice == '1':
                return 'cloudflare'
            elif choice == '2':
                return 'gcp'
            elif choice == '3':
                return 'azure'
            elif choice == '4':
                return None
            else:
                print("Invalid choice. Please select 1-4.")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            return None


def get_provider_class(provider: str):
    if not check_provider_availability(provider):
        return None

    if provider == 'gcp':
        from omniprox.providers.gcp import GCPProvider
        return GCPProvider
    elif provider == 'azure' or provider == 'az':
        from omniprox.providers.azure import AzureProvider
        return AzureProvider
    elif provider == 'cloudflare' or provider == 'cf':
        from omniprox.providers.cloudflare import CloudflareProvider
        return CloudflareProvider
    elif provider == 'alibaba':
        from omniprox.providers.alibaba import AlibabaProvider
        return AlibabaProvider

    return None


def execute_all_providers(args):
    """Execute command for all configured providers"""
    import configparser

    # All available providers (simplified list)
    providers = ['cloudflare', 'gcp', 'azure', 'alibaba']

    # Get configured profiles
    config = configparser.ConfigParser()
    config_path = os.path.expanduser('~/.omniprox/profiles.ini')

    if os.path.exists(config_path):
        config.read(config_path)

    # Track results
    results = []
    successful = 0
    failed = 0

    print("\n" + "="*60)
    print(f"Executing '{args.command}' for all configured providers")
    print("="*60)

    for provider in providers:
        # Use provider name directly as profile section
        profile_section = provider

        # Check if provider has a configured profile
        profile_name = f"{profile_section}:{args.profile}"
        if profile_name not in config.sections():
            # Try default profile
            profile_name = f"{profile_section}:default"

        if profile_name not in config.sections():
            print(f"\n[SKIP] {provider.upper()}: No configuration found")
            continue

        print(f"\n[{provider.upper()}] Executing {args.command}...")
        print("-" * 40)

        # Create a copy of args with the current provider
        provider_args = argparse.Namespace(**vars(args))
        provider_args.provider = provider
        provider_args.all = False  # Prevent recursion

        try:
            # Get the provider class
            provider_class = get_provider_class(provider)
            if not provider_class:
                print(f"  [ERROR] Provider implementation not available")
                failed += 1
                continue

            # Initialize and execute
            provider_instance = provider_class(provider_args)
            success = provider_instance.execute()

            if success:
                print(f"  [OK] {args.command} completed successfully")
                successful += 1
            else:
                print(f"  [FAILED] {args.command} failed")
                failed += 1

        except Exception as e:
            print(f"  [ERROR] {e}")
            failed += 1

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Skipped: {len(providers) - successful - failed}")

    return 0 if failed == 0 else 1


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        prog='omniprox',
        description='OmniProx - Multi-cloud HTTP proxy manager',
        epilog="""
Examples:
  %(prog)s --command create --url https://domaingoeshere.local
  %(prog)s --command create --url https://domaingoeshere.local --provider gcp
  %(prog)s --command list --provider cloudflare
  %(prog)s --command delete --api_id proxy-123 --provider gcp
  %(prog)s --command cleanup --provider cloudflare

Providers:
  cloudflare, cf - Cloudflare Workers (100k free/day, best for IP rotation)
  gcp           - Google Cloud Platform API Gateway (2M free/month)
  azure, az     - Microsoft Azure Container Instances (IP rotation pool)
  alibaba       - Alibaba Cloud API Gateway (China regions)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--provider', '-p',
                       choices=['gcp', 'azure', 'az', 'cloudflare', 'cf', 'alibaba'],
                       help='Cloud provider')

    parser.add_argument('--command', '-c',
                       choices=['create', 'list', 'delete', 'update', 'status', 'usage', 'cleanup', 'proxytest'],
                       help='Command to execute')

    parser.add_argument('--url', '-u',
                       help='Target URL for proxy')

    parser.add_argument('--api_id', '-a',
                       help='API/Proxy ID')

    parser.add_argument('--number', '-n',
                       type=int,
                       default=1,
                       help='Number of proxies to create (default: 1)')

    parser.add_argument('--region', '--location', '-r',
                       dest='region',
                       help='Region/location for proxy deployment (e.g., us-east-1, westus, europe-west1)')

    parser.add_argument('--profile',
                       default='default',
                       help='Configuration profile (default: default)')

    parser.add_argument('--debug', '-d',
                       action='store_true',
                       help='Enable debug output')

    parser.add_argument('--quiet', '-q',
                       action='store_true',
                       help='Suppress non-error output')

    parser.add_argument('--log-level',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')

    parser.add_argument('--log-file',
                       help='Log output file')

    parser.add_argument('--check-providers',
                       action='store_true',
                       help='Check provider availability')

    parser.add_argument('--setup',
                       action='store_true',
                       help='Run interactive setup wizard')

    parser.add_argument('--all',
                       action='store_true',
                       help='Apply command to all configured providers (for cleanup/list commands)')

    return parser.parse_args()


def main():
    """Main entry point for OmniProx"""
    from omniprox.core.setup import check_first_run, OmniProxSetup

    if '--setup' in sys.argv:
        setup = OmniProxSetup()
        setup.run_first_time_setup()
        return 0

    if check_first_run() and '--help' not in sys.argv and '-h' not in sys.argv:
        print("Tip: Run 'omniprox --setup' for guided configuration")

    args = parse_arguments()

    # Handle --all flag for cleanup/list commands
    if args.all:
        if args.command not in ['cleanup', 'list']:
            print("Error: --all flag is only supported for 'cleanup' and 'list' commands")
            return 1

        return execute_all_providers(args)

    # Interactive provider selection if not provided
    if not args.provider and not args.all:
        args.provider = select_provider_interactive()
        if not args.provider:
            print("No provider selected. Exiting.")
            return 1

    # Handle provider aliases
    if args.provider == 'cf':
        args.provider = 'cloudflare'
    elif args.provider == 'az':
        args.provider = 'azure'

    if args.check_providers:
        print_provider_status()
        sys.exit(0)

    if not args.command:
        print("Error: --command is required")
        print("Try: omniprox --help")
        sys.exit(1)

    if args.debug:
        log_level = 'DEBUG'
    elif args.quiet:
        log_level = 'ERROR'
    elif hasattr(args, 'log_level') and args.log_level:
        log_level = args.log_level
    else:
        log_level = 'INFO'

    logger = setup_logging(level=log_level, log_file=args.log_file)
    logger.info(f"OmniProx starting - Provider: {args.provider}, Command: {args.command}")

    provider_class = get_provider_class(args.provider)
    if not provider_class:
        logger.error(f"Provider '{args.provider}' is not available")
        print(f"\nError: {args.provider.upper()} provider is not available.")
        print(f"Please install required packages:")

        if args.provider == 'gcp':
            print("  pip install google-cloud-api-gateway google-cloud-resource-manager")
        elif args.provider == 'azure':
            print("  pip install azure-mgmt-web azure-mgmt-resource azure-mgmt-storage azure-identity")
        elif args.provider in ['cloudflare', 'cf']:
            print("  pip install requests")

        print("\nRun with --check-providers to see all provider statuses")
        sys.exit(1)

    try:
        logger.info(f"Initializing {args.provider} provider")
        provider = provider_class(args)

        logger.info(f"Executing command: {args.command}")
        success = provider.execute()

        if success:
            logger.info(f"Command completed successfully")
            sys.exit(0)
        else:
            logger.error(f"Command failed")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        print("\nOperation cancelled by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        if not args.quiet:
            print(f"\nError: {e}")
            if args.log_level == 'DEBUG':
                import traceback
                traceback.print_exc()
        sys.exit(1)


def quick_cli():
    """Quick CLI wrapper for common OmniProx operations (for 'omni' command)"""

    # If no arguments, show simple help
    if len(sys.argv) == 1:
        print("""OmniProx - Quick multi-cloud proxy manager

Usage:
  omni create <url>           Create proxy (will prompt for provider)
  omni list                   List all proxies
  omni delete <id>            Delete specific proxy
  omni cleanup                Delete all proxies
  omni proxytest              Test IP rotation for provider

Options:
  --provider <name>           Use specific provider:
                               cf/cloudflare, gcp, azure/az, alibaba
  --profile <name>            Use specific profile (default: "default")
  --debug                     Show verbose output

Examples:
  omni create https://api.example.com
  omni create https://api.example.com --provider gcp
  omni list --provider cf
  omni delete proxy-123abc
  omni cleanup --profile work
  omni proxytest --provider cloudflare

For full options: omniprox --help""")
        sys.exit(0)

    # Map simple commands to full syntax
    args = sys.argv[1:]
    new_args = ['omniprox']

    # First argument is likely the command
    if args[0] in ['create', 'list', 'delete', 'update', 'cleanup', 'status', 'proxytest']:
        new_args.extend(['--command', args[0]])
        args = args[1:]

        # For create/update, next arg is likely URL
        if new_args[2] in ['create', 'update'] and args and not args[0].startswith('-'):
            new_args.extend(['--url', args[0]])
            args = args[1:]

        # For delete, next arg is likely the ID
        elif new_args[2] == 'delete' and args and not args[0].startswith('-'):
            new_args.extend(['--api_id', args[0]])
            args = args[1:]

    # Pass through remaining arguments
    new_args.extend(args)

    # Execute with transformed arguments
    sys.argv = new_args
    return main()


if __name__ == '__main__':
    main()
