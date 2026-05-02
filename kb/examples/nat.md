# Example: Public and Private with NAT

Topology:
PC1 public, S1 private but needs internet

Interpretation:
- split into public/private subnets
- IGW for public subnet
- NAT in public subnet
- private subnet default route to NAT
