# NAT and Public/Private Split

If a private host needs outbound Internet access:
- place it in a private subnet
- add a NAT Gateway in a public subnet
- route private subnet default traffic to NAT

If one LAN contains both public and private hosts:
- split it into a public subnet and a private subnet
