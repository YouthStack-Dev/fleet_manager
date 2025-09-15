from fastapi import Depends, Request, HTTPException, status
from typing import List
import logging

from .middleware import JWTAuthMiddleware
from .token_validation import validate_bearer_token

logger = logging.getLogger("uvicorn")
class PermissionChecker:
    def __init__(
        self,
        required_permissions: List[str],
        check_tenant: bool = True
    ):
        self.required_permissions = required_permissions
        self.check_tenant = check_tenant
    
    async def __call__(self, request: Request, user_data = Depends(validate_bearer_token(use_cache=True))):
        
        
        logger.info(f"PermissionChecker triggered for required_permissions: {self.required_permissions}")
        
        # Check if user has required permissions
        user_permissions = [p["module"] + "." + a 
                          for p in user_data["permissions"]
                          for a in p["action"]]
        
        logger.info(f"User permissions: {user_permissions}")

        if not any(p in user_permissions for p in self.required_permissions):
            logger.warning(f"Permission denied. Required: {self.required_permissions}, User has: {user_permissions}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        logger.info("Permission check passed")

        # Check tenant access if required
        if self.check_tenant:
            tenant_id = request.path_params.get("tenant_id")

            logger.info(f"Tenant Check - Path tenant_id: {tenant_id}, Token tenant_id: {user_data['tenant_id']}")

            if tenant_id and int(tenant_id) != int(user_data["tenant_id"]):
                logger.warning(f"Tenant access forbidden - Path tenant_id: {tenant_id}, Token tenant_id: {user_data['tenant_id']}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access to this tenant is forbidden"
                )

            logger.info("Tenant check passed")

        return user_data