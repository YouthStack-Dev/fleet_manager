from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from app.database.session import get_db
from app.models.iam import Policy, Permission
from app.schemas.iam import (
    PolicyCreate, PolicyUpdate, PolicyResponse, PolicyPaginationResponse
)
from app.crud.iam import policy_crud, permission_crud
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/policies",
    tags=["IAM Policies"]
)

def resolve_tenant_id(user_data: dict, tenant_id_from_request: Optional[str] = None) -> str:
    """
    Resolve tenant_id based on user type.
    
    Args:
        user_data: User data from token
        tenant_id_from_request: tenant_id from request body/payload (for admin users)
    
    Returns:
        Resolved tenant_id
        
    Raises:
        HTTPException: If tenant_id cannot be resolved
    """
    logger.info("  → Resolving tenant_id for tenant policy")
    user_type = user_data.get("user_type")
    logger.info(f"  → User type: {user_type}")
    logger.info(f"  → Tenant ID in payload: {tenant_id_from_request if tenant_id_from_request else 'NOT PROVIDED'}")
    
    if user_type in ["employee", "vendor"]:
        logger.info(f"  → Employee/Vendor flow: Using tenant_id from token")
        resolved_tenant_id = user_data.get("tenant_id")
        if not resolved_tenant_id:
            logger.error("  ✗ FAILED: Tenant ID missing in token for employee/vendor")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant ID missing in token",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
        # Employee/vendor can only create for their own tenant
        if tenant_id_from_request and str(tenant_id_from_request) != str(resolved_tenant_id):
            logger.warning(f"  ✗ FAILED: Employee/Vendor attempted to use different tenant_id")
            logger.warning(f"  → Token tenant: {resolved_tenant_id}, Requested tenant: {tenant_id_from_request}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You can only create policies for your own tenant",
                    error_code="UNAUTHORIZED_TENANT_ACCESS"
                )
            )
        logger.info(f"  ✓ Tenant ID resolved from token: {resolved_tenant_id}")
    elif user_type == "admin":
        logger.info("  → Admin flow: tenant_id MUST be provided in payload")
        logger.info("  → Note: Admin users don't carry tenant_id in token")
        if tenant_id_from_request:
            resolved_tenant_id = tenant_id_from_request
            logger.info(f"  ✓ Tenant ID resolved from payload: {resolved_tenant_id}")
        else:
            logger.error("  ✗ FAILED: Admin must provide tenant_id in request payload for tenant policies")
            logger.error("  → For system policies, set 'is_system_policy': true instead")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required in request for admin",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
    else:
        logger.error(f"  ✗ FAILED: Unknown user type '{user_type}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Unauthorized user type for this operation",
                error_code="UNAUTHORIZED_USER_TYPE"
            )
        )
    
    return resolved_tenant_id

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_policy(
    policy: PolicyCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy.create"], check_tenant=True))
):
    """
    Create a new policy with associated permissions.
    
    Rules:
    - Admin: Must provide tenant_id in request body, can create for any tenant
    - Employee/Vendor: tenant_id taken from token, can only create for their tenant
    - System policies (is_system_policy=true) require admin user type
    """
    logger.info("="*50)
    logger.info("STEP 1: Starting policy creation process")
    logger.info(f"Policy name: {policy.name}")
    logger.info(f"Is system policy: {getattr(policy, 'is_system_policy', False)}")
    logger.info(f"Permission IDs count: {len(policy.permission_ids) if policy.permission_ids else 0}")
    
    logger.info("STEP 2: Validating user credentials")
    user_type = user_data.get("user_type")
    user_tenant_id = user_data.get("tenant_id")
    logger.info(f"User type: {user_type}")
    logger.info(f"User tenant ID: {user_tenant_id}")
    
    # Check if trying to create system policy
    logger.info("STEP 3: Checking policy type and authorization")
    is_system_policy = getattr(policy, "is_system_policy", False)
    
    if is_system_policy:
        logger.info("Policy type: SYSTEM POLICY")
        # Only admin can create system policies
        if user_type != "admin":
            logger.warning(f"AUTHORIZATION FAILED: Non-admin user '{user_type}' attempted to create system policy")
            logger.info("="*50)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only admin users can create system policies",
                    error_code="SYSTEM_POLICY_ADMIN_ONLY"
                )
            )
        logger.info("Authorization: PASSED (admin user)")
        # System policies should NOT have a tenant_id
        policy.tenant_id = None
        logger.info("System policy: tenant_id set to NULL")
    else:
        logger.info("Policy type: TENANT POLICY")
        # Non-system policies MUST have a tenant_id
        logger.info("STEP 4: Resolving tenant ID for tenant policy")
        logger.info(f"Tenant ID from request payload: {policy.tenant_id if policy.tenant_id else 'None'}")
        resolved_tenant_id = resolve_tenant_id(user_data, policy.tenant_id)
        policy.tenant_id = resolved_tenant_id
        logger.info(f"✓ Tenant ID resolved and set: {resolved_tenant_id}")
        logger.info(f"Verifying policy object tenant_id: {policy.tenant_id}")
    
    # Verify all permission IDs exist
    logger.info("STEP 5: Validating permission IDs")
    if policy.permission_ids:
        logger.info(f"Checking {len(policy.permission_ids)} permission IDs: {policy.permission_ids}")
        existing_permissions = db.query(Permission).filter(
            Permission.permission_id.in_(policy.permission_ids)
        ).all()
        logger.info(f"Found {len(existing_permissions)} valid permissions in database")
        if len(existing_permissions) != len(policy.permission_ids):
            logger.error(f"VALIDATION FAILED: Invalid permission IDs provided")
            logger.error(f"Requested: {policy.permission_ids}")
            logger.error(f"Valid: {[p.permission_id for p in existing_permissions]}")
            logger.info("="*50)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="One or more permission IDs are invalid",
                    error_code="INVALID_PERMISSION_IDS"
                )
            )
        logger.info("Permission validation: PASSED")
    else:
        logger.info("No permission IDs provided - creating policy without permissions")
    
    try:
        logger.info("STEP 6: Creating policy in database")
        logger.info(f"Final policy object before insert:")
        logger.info(f"  - name: {policy.name}")
        logger.info(f"  - tenant_id: {policy.tenant_id}")
        logger.info(f"  - is_system_policy: {is_system_policy}")
        logger.info(f"  - is_active: {getattr(policy, 'is_active', True)}")
        logger.info(f"  - permission_ids: {policy.permission_ids if policy.permission_ids else []}")
        
        created_policy = policy_crud.create_with_permissions(db=db, obj_in=policy)
        logger.info(f"✓ Policy created successfully")
        logger.info(f"Policy ID: {created_policy.policy_id}")
        logger.info(f"Policy Name: {created_policy.name}")
        logger.info(f"Permissions attached: {len(created_policy.permissions) if created_policy.permissions else 0}")
        logger.info("="*50)
        
        return ResponseWrapper.success(
            data=PolicyResponse.model_validate(created_policy, from_attributes=True),
            message="Policy created successfully"
        )
    except IntegrityError as e:
        db.rollback()
        logger.error("✗ STEP 6: Database operation FAILED - Integrity constraint violation")
        logger.info("="*50)
        
        # Check if it's a duplicate key error
        error_msg = str(e.orig)
        if "uq_policy_tenant_name" in error_msg or "duplicate key" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message="Policy with this name already exists for this tenant",
                    error_code="POLICY_ALREADY_EXISTS",
                    details={
                        "tenant_id": policy.tenant_id or "system",
                        "policy_name": policy.name,
                        "hint": "Use a different policy name or update the existing policy"
                    }
                )
            )
        else:
            # Other integrity errors
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Database integrity constraint violated",
                    error_code="INTEGRITY_ERROR",
                    details={"error": str(e.orig)}
                )
            )
    except Exception as e:
        db.rollback()
        logger.error("✗ STEP 6: Database operation FAILED")
        logger.exception(f"Error details: {str(e)}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ResponseWrapper.error(
                message="Failed to create policy",
                error_code="POLICY_CREATE_FAILED",
                details={"error": str(e)}
            )
        )

@router.get("/")
async def get_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    is_system_policy: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy.read"], check_tenant=True))
):
    """
    Get a list of policies with optional filters.
    
    Rules:
    - Admin: Can provide tenant_id as query parameter to get specific tenant's policies
             If tenant_id provided: system policies + specified tenant policies
             If tenant_id not provided: system policies only
    - Employee/Vendor: tenant_id taken from token, cannot query other tenants
                       Returns: system policies + their tenant policies
    """
    logger.info("="*50)
    logger.info("STEP 1: Starting get policies request")
    logger.info(f"Query params - skip: {skip}, limit: {limit}")
    logger.info(f"Filters - name: {name}, tenant_id: {tenant_id}, is_system_policy: {is_system_policy}")
    
    filters = {}
    if name:
        filters["name"] = name
    if is_system_policy is not None:
        filters["is_system_policy"] = is_system_policy
    
    logger.info("STEP 2: Validating user and determining access scope")
    user_type = user_data.get("user_type")
    logger.info(f"User type: {user_type}")
    resolved_tenant_id = None
    
    # Admin can optionally provide tenant_id
    if user_type == "admin":
        logger.info("User role: ADMIN")
        if tenant_id:
            resolved_tenant_id = tenant_id
            logger.info(f"Admin requested specific tenant: {tenant_id}")
            logger.info("Access scope: System policies + Tenant policies")
        else:
            logger.info("No tenant_id provided by admin")
            logger.info("Access scope: System policies ONLY")
            
    elif user_type in ["employee", "vendor"]:
        logger.info(f"User role: {user_type.upper()}")
        # Employee/vendor use their token tenant_id
        resolved_tenant_id = user_data.get("tenant_id")
        if not resolved_tenant_id:
            logger.error("AUTHORIZATION FAILED: Tenant ID missing in token")
            logger.info("="*50)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant ID missing in token",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
        # Employee/vendor cannot request other tenants
        if tenant_id and str(tenant_id) != str(resolved_tenant_id):
            logger.warning(f"AUTHORIZATION FAILED: {user_type} attempted to access tenant {tenant_id}")
            logger.warning(f"User's tenant: {resolved_tenant_id}")
            logger.info("="*50)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot access policies from other tenants",
                    error_code="UNAUTHORIZED_TENANT_ACCESS"
                )
            )
        logger.info(f"User's tenant: {resolved_tenant_id}")
        logger.info("Access scope: System policies + Own tenant policies")
    else:
        logger.error(f"AUTHORIZATION FAILED: Unknown user type '{user_type}'")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Unauthorized user type for this operation",
                error_code="UNAUTHORIZED_USER_TYPE"
            )
        )
    
    # Build query to include system policies + tenant-specific policies (if applicable)
    logger.info("STEP 3: Building database query")
    if resolved_tenant_id is None:
        logger.info("Query type: System policies ONLY")
        # Only return system policies (admin without tenant_id)
        base_query = db.query(Policy).filter(Policy.is_system_policy == True)
    else:
        logger.info("Query type: System policies + Tenant policies")
        logger.info(f"Tenant filter: {resolved_tenant_id}")
        # Return system policies + tenant-specific policies
        base_query = db.query(Policy).filter(
            or_(
                Policy.is_system_policy == True,
                Policy.tenant_id == resolved_tenant_id
            )
        )
    
    # Apply other filters
    logger.info("STEP 4: Applying additional filters")
    if name:
        base_query = base_query.filter(Policy.name.ilike(f"%{name}%"))
        logger.info(f"Name filter applied: '{name}' (case-insensitive)")
    if is_system_policy is not None:
        base_query = base_query.filter(Policy.is_system_policy == is_system_policy)
        logger.info(f"System policy filter: {is_system_policy}")
    
    # Get total count
    logger.info("STEP 5: Executing query")
    total = base_query.count()
    logger.info(f"Total matching records: {total}")
    
    # Apply pagination
    policies = base_query.offset(skip).limit(limit).all()
    logger.info(f"✓ Retrieved {len(policies)} policies (page: skip={skip}, limit={limit})")
    
    if policies:
        system_count = sum(1 for p in policies if p.is_system_policy)
        tenant_count = len(policies) - system_count
        logger.info(f"Breakdown: {system_count} system policies, {tenant_count} tenant policies")
    logger.info("="*50)
    
    return ResponseWrapper.success(
        data={
            "total": total,
            "items": [PolicyResponse.model_validate(p, from_attributes=True) for p in policies]
        },
        message="Policies retrieved successfully"
    )

@router.get("/{policy_id}")
async def get_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy.read"], check_tenant=True))
):
    """Get a specific policy by ID"""
    logger.info("="*50)
    logger.info("STEP 1: Starting get policy by ID request")
    logger.info(f"Policy ID: {policy_id}")
    logger.info(f"User type: {user_data.get('user_type')}")
    
    logger.info("STEP 2: Fetching policy from database")
    policy = policy_crud.get(db, id=policy_id)
    if not policy:
        logger.warning(f"POLICY NOT FOUND: policy_id={policy_id}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Policy not found",
                error_code="POLICY_NOT_FOUND"
            )
        )
    
    logger.info(f"✓ Policy found: {policy.name}")
    logger.info(f"Policy type: {'SYSTEM' if policy.is_system_policy else 'TENANT'}")
    logger.info(f"Tenant ID: {policy.tenant_id if policy.tenant_id else 'NULL'}")
    
    # Check tenant access for non-system policies
    logger.info("STEP 3: Validating access permissions")
    if policy.tenant_id and not policy.is_system_policy:
        logger.info("Access check required: Tenant policy")
        user_type = user_data.get("user_type")
        user_tenant_id = user_data.get("tenant_id")
        
        # Admin can access any tenant's policies
        if user_type != "admin":
            logger.info(f"Checking tenant match: Policy tenant={policy.tenant_id}, User tenant={user_tenant_id}")
            # Employee/vendor can only access their own tenant's policies
            if str(policy.tenant_id) != str(user_tenant_id):
                logger.warning(f"AUTHORIZATION FAILED: Cross-tenant access denied")
                logger.warning(f"Policy tenant: {policy.tenant_id}, User tenant: {user_tenant_id}")
                logger.info("="*50)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Cannot access policy from different tenant",
                        error_code="UNAUTHORIZED_TENANT_ACCESS"
                    )
                )
            logger.info("✓ Tenant match verified")
        else:
            logger.info("✓ Access granted: Admin user")
    else:
        logger.info("✓ Access granted: System policy (accessible to all)")
    
    logger.info(f"✓ Policy retrieved successfully: {policy.name}")
    logger.info(f"Permissions attached: {len(policy.permissions) if policy.permissions else 0}")
    logger.info("="*50)
    
    return ResponseWrapper.success(
        data=PolicyResponse.model_validate(policy, from_attributes=True),
        message="Policy retrieved successfully"
    )

@router.put("/{policy_id}")
async def update_policy(
    policy_id: int,
    policy_update: PolicyUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy.update"], check_tenant=True))
):
    """Update a policy and its permissions"""
    logger.info("="*50)
    logger.info("STEP 1: Starting policy update request")
    logger.info(f"Policy ID: {policy_id}")
    logger.info(f"User type: {user_data.get('user_type')}")
    logger.info(f"Update fields: {policy_update.model_dump(exclude_unset=True).keys()}")
    
    logger.info("STEP 2: Fetching existing policy")
    policy = policy_crud.get(db, id=policy_id)
    if not policy:
        logger.warning(f"POLICY NOT FOUND: policy_id={policy_id}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Policy not found",
                error_code="POLICY_NOT_FOUND"
            )
        )
    
    logger.info(f"✓ Policy found: {policy.name}")
    logger.info(f"Policy type: {'SYSTEM' if policy.is_system_policy else 'TENANT'}")
    logger.info(f"Current tenant ID: {policy.tenant_id if policy.tenant_id else 'NULL'}")
    
    logger.info("STEP 3: Validating update permissions")
    user_type = user_data.get("user_type")
    
    # System policies can only be updated by admin users
    if policy.is_system_policy and user_type != "admin":
        logger.warning(f"AUTHORIZATION FAILED: Non-admin attempted to update system policy")
        logger.warning(f"User type: {user_type}, Policy ID: {policy_id}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Only admin users can update system policies",
                error_code="SYSTEM_POLICY_ADMIN_ONLY"
            )
        )
    
    if policy.is_system_policy:
        logger.info("✓ System policy update authorized: Admin user")
    
    # Check tenant access for non-system policies
    if policy.tenant_id and not policy.is_system_policy:
        user_tenant_id = user_data.get("tenant_id")
        
        # Admin can update any tenant's policies
        if user_type != "admin":
            logger.info(f"Verifying tenant access: Policy tenant={policy.tenant_id}, User tenant={user_tenant_id}")
            # Employee/vendor can only update their own tenant's policies
            if str(policy.tenant_id) != str(user_tenant_id):
                logger.warning(f"AUTHORIZATION FAILED: Cross-tenant update denied")
                logger.warning(f"Policy tenant: {policy.tenant_id}, User tenant: {user_tenant_id}")
                logger.info("="*50)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Cannot update policy from different tenant",
                        error_code="UNAUTHORIZED_TENANT_ACCESS"
                    )
                )
            logger.info("✓ Tenant access verified")
        else:
            logger.info("✓ Tenant policy update authorized: Admin user")
    
    # Verify permission IDs if provided
    logger.info("STEP 4: Validating permission IDs (if updated)")
    if policy_update.permission_ids is not None:
        if policy_update.permission_ids:
            logger.info(f"Validating {len(policy_update.permission_ids)} new permission IDs")
            existing_permissions = db.query(Permission).filter(
                Permission.permission_id.in_(policy_update.permission_ids)
            ).all()
            logger.info(f"Found {len(existing_permissions)} valid permissions")
            if len(existing_permissions) != len(policy_update.permission_ids):
                logger.error(f"VALIDATION FAILED: Invalid permission IDs")
                logger.error(f"Requested: {policy_update.permission_ids}")
                logger.error(f"Valid: {[p.permission_id for p in existing_permissions]}")
                logger.info("="*50)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="One or more permission IDs are invalid",
                        error_code="INVALID_PERMISSION_IDS"
                    )
                )
            logger.info("✓ Permission IDs validated")
        else:
            logger.info("Clearing all permissions (empty array provided)")
    else:
        logger.info("No permission update requested")
    
    try:
        logger.info("STEP 5: Updating policy in database")
        updated_policy = policy_crud.update_with_permissions(db, db_obj=policy, obj_in=policy_update)
        logger.info(f"✓ Policy updated successfully")
        logger.info(f"Policy ID: {updated_policy.policy_id}")
        logger.info(f"Policy Name: {updated_policy.name}")
        logger.info(f"Current permissions: {len(updated_policy.permissions) if updated_policy.permissions else 0}")
        logger.info("="*50)
        
        return ResponseWrapper.success(
            data=PolicyResponse.model_validate(updated_policy, from_attributes=True),
            message="Policy updated successfully"
        )
    except Exception as e:
        db.rollback()
        logger.error("STEP 5: Database operation FAILED")
        logger.exception(f"Error details: {str(e)}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Failed to update policy",
                error_code="POLICY_UPDATE_FAILED",
                details={"error": str(e)}
            )
        )

@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["policy.delete"], check_tenant=True))
):
    """Delete a policy"""
    logger.info("="*50)
    logger.info("STEP 1: Starting policy deletion request")
    logger.info(f"Policy ID: {policy_id}")
    logger.info(f"User type: {user_data.get('user_type')}")
    
    logger.info("STEP 2: Fetching policy to delete")
    policy = policy_crud.get(db, id=policy_id)
    if not policy:
        logger.warning(f"POLICY NOT FOUND: policy_id={policy_id}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Policy not found",
                error_code="POLICY_NOT_FOUND"
            )
        )
    
    logger.info(f"✓ Policy found: {policy.name}")
    logger.info(f"Policy type: {'SYSTEM' if policy.is_system_policy else 'TENANT'}")
    logger.info(f"Tenant ID: {policy.tenant_id if policy.tenant_id else 'NULL'}")
    logger.info(f"Associated permissions: {len(policy.permissions) if policy.permissions else 0}")
    
    logger.info("STEP 3: Validating delete permissions")
    user_type = user_data.get("user_type")
    
    # System policies can only be deleted by admin users
    if policy.is_system_policy and user_type != "admin":
        logger.warning(f"AUTHORIZATION FAILED: Non-admin attempted to delete system policy")
        logger.warning(f"User type: {user_type}, Policy ID: {policy_id}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Only admin users can delete system policies",
                error_code="SYSTEM_POLICY_ADMIN_ONLY"
            )
        )
    
    if policy.is_system_policy:
        logger.info("✓ System policy deletion authorized: Admin user")
    
    # Check tenant access for non-system policies
    if policy.tenant_id and not policy.is_system_policy:
        user_tenant_id = user_data.get("tenant_id")
        
        # Admin can delete any tenant's policies
        if user_type != "admin":
            logger.info(f"Verifying tenant access: Policy tenant={policy.tenant_id}, User tenant={user_tenant_id}")
            # Employee/vendor can only delete their own tenant's policies
            if str(policy.tenant_id) != str(user_tenant_id):
                logger.warning(f"AUTHORIZATION FAILED: Cross-tenant deletion denied")
                logger.warning(f"Policy tenant: {policy.tenant_id}, User tenant: {user_tenant_id}")
                logger.info("="*50)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Cannot delete policy from different tenant",
                        error_code="UNAUTHORIZED_TENANT_ACCESS"
                    )
                )
            logger.info("✓ Tenant access verified")
        else:
            logger.info("✓ Tenant policy deletion authorized: Admin user")
    
    try:
        logger.info("STEP 4: Deleting policy from database")
        logger.info(f"Note: Associated policy-permission links will be CASCADE deleted")
        policy_crud.remove(db, id=policy_id)
        logger.info(f"✓ Policy deleted successfully: {policy.name} (ID: {policy_id})")
        logger.info("="*50)
        
        return ResponseWrapper.success(
            data=None,
            message="Policy deleted successfully"
        )
    except Exception as e:
        db.rollback()
        logger.error("STEP 4: Database operation FAILED")
        logger.exception(f"Error details: {str(e)}")
        logger.info("="*50)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Failed to delete policy",
                error_code="POLICY_DELETE_FAILED",
                details={"error": str(e)}
            )
        )
