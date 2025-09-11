
### **SuperAdmin Capabilities**

1. **Tenant (Company) Management**

   * Can **create a Tenant**.
   * Automatically creates a **default Team** and a default **Employee record**.

     * The default employee is assigned the **`tenant_admin` role** for that Tenant.
     * Every user in a Tenant is, by default, an **Employee** (role can later be changed).

2. **Vendor Management**

   * Can **create Vendors**.
   * Can **connect Vendors to one or multiple Tenants** (Many-to-Many relationship).
   * Vendors are **shared resources** — they are not isolated per tenant.

3. **Roles, Groups & Permissions**

   * Can **create Groups** of roles and assign permissions (CRUD, module-based, etc.).
   * Roles are **pre-grouped models** for convenience.
   * SuperAdmin has full control over **role & permission templates** across Tenants.

4. **User/Employee Management**

   * Every user in a Tenant is an **Employee by default**.
   * When creating a Tenant, SuperAdmin ensures **tenant\_admin employee** is created.
   * Role changes can be made after creation, but **Employee role always exists**.

---

### **Relationships / DB Considerations**

* `tenant`

  * `tenant_id, name, ...`
* `employee`

  * `employee_id, user_id, tenant_id, role_id, ...`
* `user`

  * `user_id, email, password, etc.`
* `vendor`

  * `vendor_id, name, details`
* `vendor_tenant` (Many-to-Many)

  * `vendor_id, tenant_id`
* `role` / `group` / `permission`

  * Managed by SuperAdmin. Roles can be assigned per employee.
  * Permissions are **pre-grouped** (module/action-based).

---

💡 **Key Notes / MVP Decisions**

1. **Employee as a base role**: Every user in a tenant has this role by default. Makes role management simpler.
2. **Tenant Admin**: A special employee created at tenant creation. Can manage tenant-level resources.
3. **Vendors are shared**: A vendor can be linked to multiple tenants. No need to duplicate vendor data.
4. **Groups & Roles**: SuperAdmin defines them globally; tenants can reuse or extend.

---

