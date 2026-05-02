# Security Patterns

- Firewall mode defaults to security group if not explicitly changed
- Bastion receives SSH from admin_cidr
- Private instances should not be publicly exposed unless explicitly requested
- SSH to private instances can be restricted to bastion security groups
