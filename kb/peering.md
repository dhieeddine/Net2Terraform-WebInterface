# Two Router Peering Pattern

A topology with two routers connected together usually maps to two VPCs with VPC peering.

Guidance:
- R1 -> VPC1
- R2 -> VPC2
- Router-to-router link -> VPC Peering
- Each switch behind a router becomes a subnet inside that router's VPC
- VPC peering is appropriate for small two-domain routed designs
- VPC peering is non-transitive
