# Terraform Patterns

## Public subnet
- aws_internet_gateway
- public route table with 0.0.0.0/0 to IGW

## Private subnet with outbound internet
- aws_eip
- aws_nat_gateway in public subnet
- private route table with 0.0.0.0/0 to NAT

## Peering
- aws_vpc_peering_connection
- per-subnet route entries to peer VPC CIDR

## Transit Gateway
- aws_ec2_transit_gateway
- aws_ec2_transit_gateway_route_table
- VPC attachments
- route table association
- route table propagation
