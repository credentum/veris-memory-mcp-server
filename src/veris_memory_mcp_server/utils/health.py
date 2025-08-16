"""
Health monitoring utilities for Veris Memory MCP Server.

Provides health checks and monitoring capabilities for
production deployment and observability.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog


logger = structlog.get_logger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    
    name: str
    status: str  # "healthy", "unhealthy", "degraded"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_healthy(self) -> bool:
        """Check if result indicates healthy status."""
        return self.status == "healthy"


@dataclass
class HealthStatus:
    """Overall health status aggregation."""
    
    status: str  # "healthy", "unhealthy", "degraded"
    checks: List[HealthCheckResult]
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_healthy(self) -> bool:
        """Check if overall status is healthy."""
        return self.status == "healthy"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "message": check.message,
                    "duration_ms": check.duration_ms,
                    "details": check.details,
                }
                for check in self.checks
            ],
        }


class HealthChecker:
    """
    Health monitoring system for MCP server components.
    
    Provides configurable health checks for various server
    components with different criticality levels.
    """
    
    def __init__(self):
        self._checks: Dict[str, callable] = {}
        self._check_configs: Dict[str, Dict[str, Any]] = {}
    
    def register_check(
        self,
        name: str,
        check_func: callable,
        timeout_seconds: float = 5.0,
        critical: bool = True,
        interval_seconds: Optional[float] = None,
    ) -> None:
        """
        Register a health check function.
        
        Args:
            name: Unique name for the health check
            check_func: Async function that returns HealthCheckResult
            timeout_seconds: Timeout for the check
            critical: Whether this check affects overall health
            interval_seconds: Automatic check interval (if None, manual only)
        """
        self._checks[name] = check_func
        self._check_configs[name] = {
            "timeout_seconds": timeout_seconds,
            "critical": critical,
            "interval_seconds": interval_seconds,
        }
        
        logger.debug(
            "Registered health check",
            name=name,
            critical=critical,
            timeout=timeout_seconds,
        )
    
    def unregister_check(self, name: str) -> None:
        """Unregister a health check."""
        self._checks.pop(name, None)
        self._check_configs.pop(name, None)
        logger.debug("Unregistered health check", name=name)
    
    async def run_check(self, name: str) -> HealthCheckResult:
        """
        Run a specific health check.
        
        Args:
            name: Name of the check to run
            
        Returns:
            Health check result
        """
        if name not in self._checks:
            return HealthCheckResult(
                name=name,
                status="unhealthy",
                message=f"Unknown health check: {name}",
            )
        
        check_func = self._checks[name]
        config = self._check_configs[name]
        
        start_time = time.time()
        
        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                check_func(),
                timeout=config["timeout_seconds"]
            )
            
            result.duration_ms = (time.time() - start_time) * 1000
            
            logger.debug(
                "Health check completed",
                name=name,
                status=result.status,
                duration_ms=result.duration_ms,
            )
            
            return result
            
        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            logger.warning(
                "Health check timed out",
                name=name,
                timeout=config["timeout_seconds"],
                duration_ms=duration_ms,
            )
            
            return HealthCheckResult(
                name=name,
                status="unhealthy",
                message=f"Health check timed out after {config['timeout_seconds']}s",
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Health check failed",
                name=name,
                error=str(e),
                duration_ms=duration_ms,
                exc_info=True,
            )
            
            return HealthCheckResult(
                name=name,
                status="unhealthy",
                message=f"Health check failed: {str(e)}",
                duration_ms=duration_ms,
                details={"exception": str(e)},
            )
    
    async def run_all_checks(self) -> HealthStatus:
        """
        Run all registered health checks.
        
        Returns:
            Aggregated health status
        """
        if not self._checks:
            return HealthStatus(
                status="healthy",
                checks=[],
            )
        
        # Run all checks concurrently
        tasks = [
            self.run_check(name) for name in self._checks.keys()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to unhealthy results
        check_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                name = list(self._checks.keys())[i]
                check_results.append(HealthCheckResult(
                    name=name,
                    status="unhealthy",
                    message=f"Health check exception: {str(result)}",
                    details={"exception": str(result)},
                ))
            else:
                check_results.append(result)
        
        # Determine overall status
        overall_status = self._determine_overall_status(check_results)
        
        logger.info(
            "Health checks completed",
            overall_status=overall_status,
            total_checks=len(check_results),
            healthy_checks=sum(1 for r in check_results if r.is_healthy),
        )
        
        return HealthStatus(
            status=overall_status,
            checks=check_results,
        )
    
    def _determine_overall_status(self, results: List[HealthCheckResult]) -> str:
        """Determine overall health status from individual check results."""
        if not results:
            return "healthy"
        
        # Check critical failures
        critical_failures = []
        non_critical_failures = []
        
        for result in results:
            if not result.is_healthy:
                config = self._check_configs.get(result.name, {})
                if config.get("critical", True):
                    critical_failures.append(result)
                else:
                    non_critical_failures.append(result)
        
        # Overall status logic
        if critical_failures:
            return "unhealthy"
        elif non_critical_failures:
            return "degraded"
        else:
            return "healthy"
    
    def get_registered_checks(self) -> List[str]:
        """Get list of registered health check names."""
        return list(self._checks.keys())


def create_veris_memory_health_checks() -> HealthChecker:
    """
    Create standard health checks for Veris Memory MCP Server.
    
    Returns:
        Configured HealthChecker instance
    """
    health_checker = HealthChecker()
    
    # Basic server health check
    async def server_health() -> HealthCheckResult:
        """Basic server health check."""
        return HealthCheckResult(
            name="server",
            status="healthy",
            message="MCP server is running",
            details={"uptime_seconds": time.time()},
        )
    
    health_checker.register_check(
        "server",
        server_health,
        timeout_seconds=1.0,
        critical=True,
    )
    
    return health_checker


def create_veris_client_health_check(veris_client) -> callable:
    """
    Create health check for Veris Memory client connection.
    
    Args:
        veris_client: VerisMemoryClient instance
        
    Returns:
        Health check function
    """
    async def veris_connection_health() -> HealthCheckResult:
        """Check Veris Memory connection health."""
        try:
            if not veris_client.connected:
                return HealthCheckResult(
                    name="veris_connection",
                    status="unhealthy",
                    message="Not connected to Veris Memory API",
                )
            
            # Try a simple operation to test connectivity
            context_types = await veris_client.list_context_types()
            
            return HealthCheckResult(
                name="veris_connection",
                status="healthy",
                message="Veris Memory API connection is healthy",
                details={
                    "connected": True,
                    "context_types_count": len(context_types),
                },
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="veris_connection",
                status="unhealthy",
                message=f"Veris Memory API connection failed: {str(e)}",
                details={"exception": str(e)},
            )
    
    return veris_connection_health


def create_cache_health_check(cache) -> callable:
    """
    Create health check for cache system.
    
    Args:
        cache: Cache instance
        
    Returns:
        Health check function
    """
    async def cache_health() -> HealthCheckResult:
        """Check cache system health."""
        try:
            stats = await cache.get_stats()
            
            # Check if cache is working properly
            utilization = stats["active_items"] / stats["max_size"] if stats["max_size"] > 0 else 0
            
            status = "healthy"
            message = "Cache system is healthy"
            
            if utilization > 0.9:
                status = "degraded"
                message = "Cache utilization is high"
            
            return HealthCheckResult(
                name="cache",
                status=status,
                message=message,
                details={
                    "utilization": utilization,
                    **stats,
                },
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="cache",
                status="unhealthy",
                message=f"Cache system check failed: {str(e)}",
                details={"exception": str(e)},
            )
    
    return cache_health