# AWS Network Patterns

## Peering
- Good for two VPCs
- Non-transitive

## Transit Gateway
- Better for 3+ routed domains
- Scales better than many peering links

## Public and Private Subnets
- Public subnet: route to Internet Gateway
- Private subnet with outbound Internet: route to NAT Gateway
