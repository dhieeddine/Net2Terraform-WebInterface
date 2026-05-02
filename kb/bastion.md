# Bastion Host Pattern

If a bastion host is requested:
- bastion should be public
- private hosts stay private
- SSH to private hosts should come from the bastion security group
- bastion receives SSH from admin_cidr
