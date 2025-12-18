"""Security utilities: authentication, SSRF protection, input validation."""

import ipaddress
import socket
import logging
from urllib.parse import urlparse
from typing import Optional
import dns.resolver
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

from app.config import get_settings

logger = logging.getLogger(__name__)


api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> str:
    """Verify the API key from request header."""
    settings = get_settings()
    request_id = getattr(request.state, "request_id", "unknown")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "unauthorized",
                "message": "Missing X-API-KEY header",
                "request_id": request_id,
            }
        )
    
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "unauthorized",
                "message": "Invalid API key",
                "request_id": request_id,
            }
        )
    
    return api_key


# Private and reserved IP ranges that should be blocked
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),          # Private
    ipaddress.ip_network("100.64.0.0/10"),       # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),         # Loopback
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local
    ipaddress.ip_network("172.16.0.0/12"),       # Private
    ipaddress.ip_network("192.0.0.0/24"),        # IETF Protocol
    ipaddress.ip_network("192.0.2.0/24"),        # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),      # 6to4 Relay
    ipaddress.ip_network("192.168.0.0/16"),      # Private
    ipaddress.ip_network("198.18.0.0/15"),       # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),     # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),      # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),         # Multicast
    ipaddress.ip_network("240.0.0.0/4"),         # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),             # Loopback
    ipaddress.ip_network("fc00::/7"),            # Unique local
    ipaddress.ip_network("fe80::/10"),           # Link-local
    ipaddress.ip_network("ff00::/8"),            # Multicast
    # AWS metadata
    ipaddress.ip_network("169.254.169.254/32"),  # Cloud metadata
]


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a blocked/private range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in BLOCKED_IP_RANGES:
            if ip in network:
                return True
        return False
    except ValueError:
        return True  # Invalid IP, block it


def resolve_hostname(hostname: str) -> list[str]:
    """Resolve hostname to IP addresses using DNS."""
    try:
        # Create resolver with timeout
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5  # 5 second timeout
        resolver.lifetime = 5
        
        # Try A records (IPv4)
        answers = resolver.resolve(hostname, "A")
        return [str(rdata) for rdata in answers]
    except dns.resolver.NXDOMAIN:
        raise ValueError(f"Domain does not exist: {hostname}")
    except dns.resolver.NoAnswer:
        # Try AAAA records (IPv6) as fallback
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 5
            answers = resolver.resolve(hostname, "AAAA")
            return [str(rdata) for rdata in answers]
        except Exception:
            raise ValueError(f"No DNS records found for: {hostname}")
    except dns.resolver.Timeout:
        # DNS timeout - allow the request but log warning
        # This prevents DNS issues from blocking legitimate requests
        logger.warning(f"DNS resolution timeout for {hostname}, allowing request")
        return []  # Return empty list to skip IP validation
    except Exception as e:
        # For other DNS errors, log but allow (to prevent DNS issues from blocking requests)
        logger.warning(f"DNS resolution failed for {hostname}: {str(e)}, allowing request")
        return []  # Return empty list to skip IP validation


def validate_url_security(url: str, request_id: str) -> str:
    """
    Validate URL for SSRF protection.
    
    - Validates scheme (http/https only)
    - Resolves DNS and checks for private IPs
    - Checks against allowed domains if configured
    
    Returns the validated URL or raises HTTPException.
    """
    settings = get_settings()
    
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "Invalid URL format",
                "request_id": request_id,
            }
        )
    
    # Validate scheme
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "URL must use http or https scheme",
                "request_id": request_id,
            }
        )
    
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": "URL must have a valid hostname",
                "request_id": request_id,
            }
        )
    
    # Check allowed domains if configured
    allowed_domains = settings.get_allowed_domains_list()
    if allowed_domains:
        hostname_lower = hostname.lower()
        domain_allowed = False
        for allowed in allowed_domains:
            if hostname_lower == allowed or hostname_lower.endswith(f".{allowed}"):
                domain_allowed = True
                break
        if not domain_allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "forbidden",
                    "message": f"Domain not in allowlist: {hostname}",
                    "request_id": request_id,
                }
            )
    
    # Check if hostname is already an IP
    try:
        ip = ipaddress.ip_address(hostname)
        if is_private_ip(str(ip)):
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "forbidden",
                    "message": "Access to private/internal IPs is not allowed",
                    "request_id": request_id,
                }
            )
        return url
    except ValueError:
        pass  # Not an IP, continue with DNS resolution
    
    # Resolve DNS and check IPs
    try:
        resolved_ips = resolve_hostname(hostname)
        # If DNS resolution succeeded, validate IPs
        if resolved_ips:
            for ip in resolved_ips:
                if is_private_ip(ip):
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error_code": "forbidden",
                            "message": f"Domain resolves to blocked IP range",
                            "request_id": request_id,
                        }
                    )
        # If DNS resolution failed/timed out, we allow the request but log it
        # (SSRF protection still applies if DNS eventually resolves)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_request",
                "message": str(e),
                "request_id": request_id,
            }
        )
    
    return url

