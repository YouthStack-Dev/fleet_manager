# Import all models here for easier access
from app.models.admin import Admin
from app.models.vendor import Vendor
from app.models.driver import Driver, GenderEnum, VerificationStatusEnum
from app.models.vehicle import Vehicle
from app.models.vehicle_type import VehicleType
from app.models.vendor_user import VendorUser
from app.models.team import Team
from app.models.tenant import Tenant
from app.models.employee import Employee
from app.models.shift import Shift
from app.models.booking import Booking
from app.models.weekoff_config import WeekoffConfig
from app.models.cutoff import Cutoff
from app.models.audit_log import AuditLog
from app.models.tenant_config import TenantConfig

# IAM models
from app.models.iam.permission import Permission
from app.models.iam.policy import Policy, policy_permission
from app.models.iam.role import Role, role_policy

# DO NOT IMPORT ANY ROUTE-RELATED MODELS HERE
# The error suggests there's still a conflicting route model being imported
