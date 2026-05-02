# Core Interpretation and Mapping Rules

- Router -> VPC
- Switch / LAN / VLAN -> Subnet
- PC / Server -> EC2
- Firewall -> Security Group by default unless explicitly overridden
- Different routers imply different VPCs
- Router-to-router links imply explicit inter-VPC connectivity
- If there is no route, there is no end-to-end connectivity
- Do not invent devices, edges, or public exposure
- Automatic addressing is allowed only when explicitly authorized
