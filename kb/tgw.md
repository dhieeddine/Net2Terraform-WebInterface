# Multi Router Transit Gateway Pattern

A topology with three or more routers usually maps better to Transit Gateway.

Guidance:
- Each router -> separate VPC
- Use TGW for 3+ routed domains
- TGW is better than many peering connections for scalability
- Router-only intermediate domains may require transit attachment subnets
