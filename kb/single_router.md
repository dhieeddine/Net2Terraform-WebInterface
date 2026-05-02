# Single Router Pattern

A topology with one router corresponds to a single VPC.

Guidance:
- One router -> one VPC
- One switch/LAN behind that router -> one subnet
- Multiple switches behind the same router -> multiple subnets in the same VPC
- If there is no public/private requirement, a single private subnet is enough
